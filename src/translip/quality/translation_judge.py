"""LLM-as-judge translation quality scoring.

This is the only *paid* step in the dub QA pipeline. It reuses the same
OpenAI-compatible HTTP plumbing as the DeepSeek translation backend
(:mod:`translip.translation.llm_utils`) to score each translated segment for
adequacy (does the target preserve the source meaning?) and fluency (is the
target natural in the target language?).

If ``DEEPSEEK_API_KEY`` is missing or the API call fails, judging degrades
gracefully: :func:`build_translation_judge` returns ``None`` and the rest of the
QA report is produced without translation scores.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import DEFAULT_DEEPSEEK_MODEL, resolve_deepseek_base_url
from ..exceptions import BackendUnavailableError
from ..pipeline.manifest import now_iso
from ..translation.backend import canonical_language_code
from ..translation.llm_utils import (
    extract_message_content,
    parse_json_payload,
    post_chat_completion,
)

JUDGE_VERSION = "translation-judge-v0"
# Overall score (1-5) below this counts as a translation problem worth surfacing.
JUDGE_FAIL_THRESHOLD = 3.0
_SCORE_MIN = 1.0
_SCORE_MAX = 5.0


@dataclass(slots=True)
class JudgeInput:
    segment_id: str
    source_text: str
    target_text: str
    speaker_label: str | None = None


@dataclass(slots=True)
class JudgeOutput:
    segment_id: str
    score: float
    adequacy: float
    fluency: float
    reason: str


class TranslationJudge:
    """Scores translated segments with an OpenAI-compatible chat model."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model_name: str | None = None,
        timeout_sec: int = 60,
        max_retries: int = 2,
        batch_size: int = 20,
        temperature: float = 0.0,
    ) -> None:
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise BackendUnavailableError(
                "Missing DeepSeek API key. Set DEEPSEEK_API_KEY to enable translation judging."
            )
        self.base_url = (base_url or resolve_deepseek_base_url()).rstrip("/")
        self.model_name = model_name or DEFAULT_DEEPSEEK_MODEL
        self.timeout_sec = timeout_sec
        self.max_retries = max_retries
        self.batch_size = max(1, batch_size)
        self.temperature = temperature
        self.resolved_model = self.model_name

    def judge(
        self,
        *,
        items: list[JudgeInput],
        source_lang: str,
        target_lang: str,
    ) -> list[JudgeOutput]:
        outputs: list[JudgeOutput] = []
        for start in range(0, len(items), self.batch_size):
            batch = items[start : start + self.batch_size]
            outputs.extend(self._judge_batch(items=batch, source_lang=source_lang, target_lang=target_lang))
        return outputs

    def _judge_batch(
        self,
        *,
        items: list[JudgeInput],
        source_lang: str,
        target_lang: str,
    ) -> list[JudgeOutput]:
        if not items:
            return []
        last_error: Exception | None = None
        for _attempt in range(self.max_retries + 1):
            try:
                return self._judge_once(items=items, source_lang=source_lang, target_lang=target_lang)
            except Exception as exc:  # noqa: BLE001 - retried then re-raised below
                last_error = exc
        raise BackendUnavailableError(f"Translation judging failed: {last_error}") from last_error

    def _judge_once(
        self,
        *,
        items: list[JudgeInput],
        source_lang: str,
        target_lang: str,
    ) -> list[JudgeOutput]:
        payload = {
            "model": self.model_name,
            "temperature": self.temperature,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a bilingual translation quality evaluator for video dubbing. "
                        "For each segment you are given the source text and its translation. "
                        "Rate two axes on an integer scale of 1 (terrible) to 5 (perfect):\n"
                        "- adequacy: does the target preserve the meaning of the source, without "
                        "additions, omissions, or mistranslations?\n"
                        "- fluency: is the target natural and grammatical in the target language?\n"
                        "Penalise empty translations, wrong language, and untranslated source. "
                        "Give a one-sentence reason naming the concrete problem (or 'ok'). "
                        "Return valid JSON with a top-level key named segments."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "task": "judge_translation_quality",
                            "source_lang": canonical_language_code(source_lang),
                            "target_lang": canonical_language_code(target_lang),
                            "segments": [
                                {
                                    "segment_id": item.segment_id,
                                    "source_text": item.source_text,
                                    "target_text": item.target_text,
                                }
                                for item in items
                            ],
                            "output_schema": {
                                "segments": [
                                    {
                                        "segment_id": "string",
                                        "adequacy": "integer 1-5",
                                        "fluency": "integer 1-5",
                                        "reason": "string",
                                    }
                                ]
                            },
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            "response_format": {"type": "json_object"},
        }
        response = post_chat_completion(
            url=f"{self.base_url}/chat/completions",
            api_key=self.api_key,
            payload=payload,
            timeout_sec=self.timeout_sec,
        )
        parsed = parse_json_payload(extract_message_content(response))
        raw_segments = parsed.get("segments")
        if not isinstance(raw_segments, list):
            raise BackendUnavailableError("Judge response missing segments array")
        mapping: dict[str, dict[str, Any]] = {
            str(row["segment_id"]): row
            for row in raw_segments
            if isinstance(row, dict) and "segment_id" in row
        }
        outputs: list[JudgeOutput] = []
        for item in items:
            row = mapping.get(item.segment_id)
            if row is None:
                raise BackendUnavailableError(f"Missing judgement for segment {item.segment_id}")
            adequacy = _clamp_score(row.get("adequacy"))
            fluency = _clamp_score(row.get("fluency"))
            # Overall score weights meaning slightly above fluency for dubbing.
            score = round((adequacy * 0.6 + fluency * 0.4), 2)
            outputs.append(
                JudgeOutput(
                    segment_id=item.segment_id,
                    score=score,
                    adequacy=adequacy,
                    fluency=fluency,
                    reason=str(row.get("reason") or "").strip(),
                )
            )
        return outputs


def build_translation_judge(
    *,
    translation_path: Path | str,
    output_dir: Path | str,
    target_lang: str,
    source_lang: str = "zh",
    batch_size: int = 20,
) -> Path | None:
    """Score a ``translation.{tag}.json`` payload and write ``judge_scores.{lang}.json``.

    Returns the written path, or ``None`` if no API key / no translated segments.
    """
    translation_path = Path(translation_path).expanduser()
    segments = _load_translation_segments(translation_path)
    if not segments:
        return None

    started_at = now_iso()
    started_monotonic = time.monotonic()
    judge = TranslationJudge(batch_size=batch_size)
    items = [
        JudgeInput(
            segment_id=str(seg.get("segment_id") or ""),
            source_text=str(seg.get("source_text") or ""),
            target_text=str(seg.get("target_text") or ""),
            speaker_label=seg.get("speaker_label"),
        )
        for seg in segments
        if seg.get("segment_id")
    ]
    results = judge.judge(items=items, source_lang=source_lang, target_lang=target_lang)

    scores = [
        {
            "segment_id": out.segment_id,
            "score": out.score,
            "adequacy": out.adequacy,
            "fluency": out.fluency,
            "reason": out.reason,
        }
        for out in results
    ]
    score_values = [out.score for out in results]
    failed = [out for out in results if out.score < JUDGE_FAIL_THRESHOLD]
    payload = {
        "version": JUDGE_VERSION,
        "created_at": now_iso(),
        "source_lang": source_lang,
        "target_lang": target_lang,
        "model": judge.resolved_model,
        "stats": {
            "segment_count": len(items),
            "judged_count": len(results),
            "failed_count": len(failed),
            "fail_threshold": JUDGE_FAIL_THRESHOLD,
            "average_score": round(sum(score_values) / len(score_values), 3) if score_values else None,
            "min_score": min(score_values) if score_values else None,
        },
        "scores": scores,
        "timing": {
            "started_at": started_at,
            "elapsed_sec": round(time.monotonic() - started_monotonic, 3),
        },
    }

    output_dir = Path(output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"judge_scores.{target_lang}.json"
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output_path


def _load_translation_segments(translation_path: Path) -> list[dict[str, Any]]:
    if not translation_path.exists() or not translation_path.is_file():
        return []
    try:
        payload = json.loads(translation_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    segments = payload.get("segments") if isinstance(payload, dict) else None
    return segments if isinstance(segments, list) else []


def _clamp_score(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return _SCORE_MIN
    return max(_SCORE_MIN, min(_SCORE_MAX, score))


__all__ = [
    "JUDGE_FAIL_THRESHOLD",
    "JUDGE_VERSION",
    "JudgeInput",
    "JudgeOutput",
    "TranslationJudge",
    "build_translation_judge",
]
