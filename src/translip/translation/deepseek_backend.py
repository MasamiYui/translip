from __future__ import annotations

import json
import os
from typing import Any

from ..config import DEFAULT_DEEPSEEK_MODEL, resolve_deepseek_base_url
from ..exceptions import BackendUnavailableError
from .backend import (
    BackendSegmentInput,
    BackendSegmentOutput,
    CondenseInput,
    CondenseOutput,
    canonical_language_code,
)
from .llm_utils import extract_message_content, parse_json_payload, post_chat_completion


class DeepSeekBackend:
    backend_name = "deepseek"
    supports_condensation = True

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model_name: str | None = None,
        timeout_sec: int = 60,
        max_retries: int = 2,
    ) -> None:
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise BackendUnavailableError("Missing DeepSeek API key. Set DEEPSEEK_API_KEY.")
        self.base_url = (base_url or resolve_deepseek_base_url()).rstrip("/")
        self.model_name = model_name or DEFAULT_DEEPSEEK_MODEL
        self.timeout_sec = timeout_sec
        self.max_retries = max_retries
        self.resolved_model = self.model_name
        self.resolved_device = None

    def translate_batch(
        self,
        *,
        items: list[BackendSegmentInput],
        source_lang: str,
        target_lang: str,
    ) -> list[BackendSegmentOutput]:
        if not items:
            return []
        last_error: Exception | None = None
        for _attempt in range(self.max_retries + 1):
            try:
                return self._translate_once(items=items, source_lang=source_lang, target_lang=target_lang)
            except Exception as exc:
                last_error = exc
        raise BackendUnavailableError(f"DeepSeek translation failed: {last_error}") from last_error

    def condense_batch(
        self,
        *,
        items: list[CondenseInput],
        target_lang: str,
    ) -> list[CondenseOutput]:
        if not items:
            return []
        last_error: Exception | None = None
        for _attempt in range(self.max_retries + 1):
            try:
                return self._condense_once(items=items, target_lang=target_lang)
            except Exception as exc:
                last_error = exc
        raise BackendUnavailableError(f"DeepSeek condensation failed: {last_error}") from last_error

    def _translate_once(
        self,
        *,
        items: list[BackendSegmentInput],
        source_lang: str,
        target_lang: str,
    ) -> list[BackendSegmentOutput]:
        payload = {
            "model": self.model_name,
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are an expert audiovisual DUBBING translator. Each segment is a "
                        "spoken line that will be voiced over the original timing. "
                        "Translate the `text` into natural, idiomatic, CONVERSATIONAL spoken "
                        "{target} — the way a voice actor would actually say it: use "
                        "contractions and natural spoken rhythm, not literal or written phrasing. "
                        "Because the line is spoken over fixed timing, prefer the most concise "
                        "faithful phrasing (avoid padding) so it fits comfortably. "
                        "When a segment carries a `max_chars` budget (and `target_duration_sec`), "
                        "keep the translation within max_chars so it can be spoken naturally in that "
                        "time — tighten wording rather than exceed it. "
                        "Preserve meaning, named entities, numbers and the emotional tone; do not "
                        "add or omit information. "
                        "Use each segment's `context` (the surrounding lines) ONLY to resolve "
                        "pronouns/references and keep continuity — translate the `text` field only, "
                        "never the context. "
                        "If the source looks ASR-corrupted or ambiguous, translate conservatively "
                        "instead of guessing. "
                        "Return valid JSON with a top-level key named segments."
                    ).replace("{target}", canonical_language_code(target_lang)),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "task": "translate_segments",
                            "source_lang": canonical_language_code(source_lang),
                            "target_lang": canonical_language_code(target_lang),
                            "register": "spoken_dialogue_for_dubbing",
                            "segments": [
                                {
                                    "segment_id": item.segment_id,
                                    "text": item.source_text,
                                    # Surrounding same-speaker lines for coherence; the model is
                                    # told to translate `text` only, not the context.
                                    "context": item.context_text or "",
                                    **(
                                        {"max_chars": item.metadata["max_chars"]}
                                        if item.metadata.get("max_chars")
                                        else {}
                                    ),
                                    **(
                                        {"target_duration_sec": item.metadata["target_duration_sec"]}
                                        if item.metadata.get("target_duration_sec")
                                        else {}
                                    ),
                                }
                                for item in items
                            ],
                            "output_schema": {
                                "segments": [{"segment_id": "string", "target_text": "string"}]
                            },
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            "response_format": {"type": "json_object"},
        }
        response = self._post_json(f"{self.base_url}/chat/completions", payload)
        content = extract_message_content(response)
        parsed = parse_json_payload(content)
        raw_segments = parsed.get("segments")
        if not isinstance(raw_segments, list):
            raise BackendUnavailableError("DeepSeek response missing segments array")
        mapping = {
            str(item["segment_id"]): str(item["target_text"]).strip()
            for item in raw_segments
            if isinstance(item, dict) and "segment_id" in item and "target_text" in item
        }
        outputs: list[BackendSegmentOutput] = []
        for item in items:
            target_text = mapping.get(item.segment_id)
            if not target_text:
                raise BackendUnavailableError(f"Missing translation for segment {item.segment_id}")
            outputs.append(BackendSegmentOutput(segment_id=item.segment_id, target_text=target_text))
        return outputs

    def _condense_once(
        self,
        *,
        items: list[CondenseInput],
        target_lang: str,
    ) -> list[CondenseOutput]:
        payload = {
            "model": self.model_name,
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You condense dubbing translations so they fit an audio duration budget. "
                        "You MUST preserve: proper nouns, named entities, numerical values, dates, "
                        "protected glossary terms (listed per segment), and emotional tone. "
                        "Only remove filler words, redundant modifiers, or restructure for brevity. "
                        "Never add information that was not in current_target_text. "
                        "Never translate from scratch — only tighten the given target text. "
                        "Aim for the character budget (max_chars) but prioritize naturalness. "
                        "Return valid JSON with a top-level key named segments."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "task": "condense_segments",
                            "target_lang": canonical_language_code(target_lang),
                            "segments": [
                                {
                                    "segment_id": item.segment_id,
                                    "source_text": item.source_text,
                                    "current_target_text": item.current_target_text,
                                    "target_duration_sec": round(item.target_duration_sec, 2),
                                    "current_estimated_duration_sec": round(item.current_estimated_sec, 2),
                                    "max_chars": item.max_chars,
                                    "protected_terms": item.protected_terms,
                                }
                                for item in items
                            ],
                            "output_schema": {
                                "segments": [{"segment_id": "string", "target_text": "string"}]
                            },
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            "response_format": {"type": "json_object"},
        }
        response = self._post_json(f"{self.base_url}/chat/completions", payload)
        content = extract_message_content(response)
        parsed = parse_json_payload(content)
        raw_segments = parsed.get("segments")
        if not isinstance(raw_segments, list):
            raise BackendUnavailableError("DeepSeek condense response missing segments array")
        mapping = {
            str(item["segment_id"]): str(item["target_text"]).strip()
            for item in raw_segments
            if isinstance(item, dict) and "segment_id" in item and "target_text" in item
        }
        outputs: list[CondenseOutput] = []
        for item in items:
            target_text = mapping.get(item.segment_id)
            if not target_text:
                raise BackendUnavailableError(f"Missing condensation for segment {item.segment_id}")
            outputs.append(CondenseOutput(segment_id=item.segment_id, target_text=target_text))
        return outputs

    def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        return post_chat_completion(
            url=url,
            api_key=self.api_key,
            payload=payload,
            timeout_sec=self.timeout_sec,
        )
