from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from ..config import DEFAULT_SILICONFLOW_BASE_URL, DEFAULT_SILICONFLOW_MODEL
from ..exceptions import BackendUnavailableError
from .backend import BackendSegmentInput, BackendSegmentOutput, canonical_language_code


class SiliconFlowBackend:
    backend_name = "siliconflow"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model_name: str | None = None,
        timeout_sec: int = 60,
        max_retries: int = 2,
    ) -> None:
        self.api_key = api_key or os.environ.get("SILICONFLOW_API_KEY")
        if not self.api_key:
            raise BackendUnavailableError("Missing SiliconFlow API key. Set SILICONFLOW_API_KEY.")
        self.base_url = (base_url or DEFAULT_SILICONFLOW_BASE_URL).rstrip("/")
        self.model_name = model_name or DEFAULT_SILICONFLOW_MODEL
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
        raise BackendUnavailableError(f"SiliconFlow translation failed: {last_error}") from last_error

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
        content = _extract_message_content(response)
        parsed = _parse_json_payload(content)
        raw_segments = parsed.get("segments")
        if not isinstance(raw_segments, list):
            raise BackendUnavailableError("SiliconFlow response missing segments array")
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

    def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_sec) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise BackendUnavailableError(f"SiliconFlow HTTP {exc.code}: {body[:500]}") from exc
        except urllib.error.URLError as exc:
            raise BackendUnavailableError(f"SiliconFlow request failed: {exc}") from exc


def _extract_message_content(response: dict[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise BackendUnavailableError("SiliconFlow response missing choices")
    message = choices[0].get("message", {})
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = [str(item.get("text", "")) for item in content if isinstance(item, dict)]
        return "".join(text_parts)
    raise BackendUnavailableError("SiliconFlow response content is empty")


def _parse_json_payload(content: str) -> dict[str, Any]:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()
    return json.loads(stripped)
