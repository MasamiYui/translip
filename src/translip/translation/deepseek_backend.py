from __future__ import annotations

import json
import os
from typing import Any

from ..config import DEFAULT_DEEPSEEK_BASE_URL, DEFAULT_DEEPSEEK_MODEL
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
        self.base_url = (base_url or DEFAULT_DEEPSEEK_BASE_URL).rstrip("/")
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
                        "You are a translation engine. Translate each segment faithfully. "
                        "Do not add information. Do not infer missing context. "
                        "If the source looks ambiguous or ASR-corrupted, translate conservatively instead of guessing. "
                        "Keep named entities stable. "
                        "Return valid JSON with a top-level key named segments."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "task": "translate_segments",
                            "source_lang": canonical_language_code(source_lang),
                            "target_lang": canonical_language_code(target_lang),
                            "segments": [
                                {
                                    "segment_id": item.segment_id,
                                    "text": item.source_text,
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
