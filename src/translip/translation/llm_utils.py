"""Shared helpers for OpenAI-compatible chat-completion backends.

Shared by the DeepSeek translation backend, the transcript-correction
arbitrator, and the translation quality judge so they reuse the exact same
HTTP + response-parsing behaviour without duplicating it.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from ..exceptions import BackendUnavailableError


def post_chat_completion(
    *,
    url: str,
    api_key: str,
    payload: dict[str, Any],
    timeout_sec: int,
) -> dict[str, Any]:
    """POST ``payload`` to an OpenAI-compatible endpoint and return the parsed JSON.

    Raises :class:`BackendUnavailableError` on any HTTP/transport failure so
    callers can implement their own retry/degrade policy uniformly.
    """
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise BackendUnavailableError(f"LLM HTTP {exc.code}: {body[:500]}") from exc
    except urllib.error.URLError as exc:
        raise BackendUnavailableError(f"LLM request failed: {exc}") from exc


def extract_message_content(response: dict[str, Any]) -> str:
    """Pull the assistant message text out of a chat-completion response."""
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise BackendUnavailableError("LLM response missing choices")
    message = choices[0].get("message", {})
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = [str(item.get("text", "")) for item in content if isinstance(item, dict)]
        return "".join(text_parts)
    raise BackendUnavailableError("LLM response content is empty")


def parse_json_payload(content: str) -> dict[str, Any]:
    """Parse a JSON object from model output, tolerating ```json fences."""
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()
    return json.loads(stripped)


__all__ = ["extract_message_content", "parse_json_payload", "post_chat_completion"]
