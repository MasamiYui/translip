"""DeepSeek (OpenAI-compatible) calls for the commentary-script chain.

Reuses the shared ``translation.llm_utils`` HTTP + parsing helpers and the same
``DEEPSEEK_*`` config the translation backend / arbitrator use, so there is one
LLM transport in the tree. ``call_text`` is for the grounded analysis stage;
``call_json`` forces a JSON object for the planning / writing stages.
"""

from __future__ import annotations

import os
from typing import Any

from ..config import DEFAULT_DEEPSEEK_MODEL, resolve_deepseek_base_url
from ..exceptions import BackendUnavailableError
from ..translation.llm_utils import (
    extract_message_content,
    parse_json_payload,
    post_chat_completion,
)

DEFAULT_TIMEOUT_SEC = 180


def _resolve(model: str | None) -> tuple[str, str, str]:
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise BackendUnavailableError(
            "Missing DeepSeek API key. Set DEEPSEEK_API_KEY to generate commentary scripts."
        )
    base_url = (resolve_deepseek_base_url() or "").rstrip("/")
    return f"{base_url}/chat/completions", api_key, (model or DEFAULT_DEEPSEEK_MODEL)


def call_text(
    *,
    system: str,
    user: str,
    model: str | None = None,
    temperature: float = 0.4,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> str:
    url, api_key, model_name = _resolve(model)
    payload: dict[str, Any] = {
        "model": model_name,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    response = post_chat_completion(url=url, api_key=api_key, payload=payload, timeout_sec=timeout_sec)
    return extract_message_content(response).strip()


def call_json(
    *,
    system: str,
    user: str,
    model: str | None = None,
    temperature: float = 0.7,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> dict[str, Any]:
    url, api_key, model_name = _resolve(model)
    payload: dict[str, Any] = {
        "model": model_name,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        # parse_json_payload still strips ```json fences if a model ignores this.
        "response_format": {"type": "json_object"},
    }
    response = post_chat_completion(url=url, api_key=api_key, payload=payload, timeout_sec=timeout_sec)
    return parse_json_payload(extract_message_content(response))
