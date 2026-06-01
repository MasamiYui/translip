"""LLM arbitration backend for ambiguous transcript-correction segments.

Used only for the ``review`` bucket (high-confidence OCR that failed the deterministic
alignment/length gates). The model picks ASR vs OCR or proposes a character-level merge;
faithfulness is enforced by the caller (``ocr_correction._apply_arbitration``). Any failure
returns ``None`` so the algorithm falls back to its deterministic review behavior.

Providers are OpenAI-compatible chat completions endpoints (DeepSeek, SiliconFlow).
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import urllib.error
import urllib.request
from typing import Any

from ..config import (
    DEFAULT_DEEPSEEK_BASE_URL,
    DEFAULT_DEEPSEEK_MODEL,
    DEFAULT_SILICONFLOW_BASE_URL,
    DEFAULT_SILICONFLOW_MODEL,
)
from ..exceptions import BackendUnavailableError
from ..translation.siliconflow_backend import _extract_message_content, _parse_json_payload
from .ocr_correction import ArbitrationRequest, ArbitrationVerdict

_VALID_DECISIONS = {"use_asr", "use_ocr", "merge"}

_SYSTEM_PROMPT = (
    "You arbitrate ambiguous Chinese subtitle lines. You receive, for one time span, the ASR "
    "text (from audio — may contain homophone errors) and the OCR text (from the on-screen "
    "subtitle — may contain visually-similar-character errors). Decide which is correct, or "
    "produce a character-level merge that fixes each side using the other. Hard rules: use ONLY "
    "characters that already appear in the ASR or OCR text; never introduce new words or content; "
    "if genuinely unsure, prefer the OCR text. "
    'Return valid JSON: {"decision": "use_asr"|"use_ocr"|"merge", "text": string, "reason": short string}.'
)


@dataclass(frozen=True, slots=True)
class _Provider:
    name: str
    api_key_env: str
    base_url: str
    model_name: str


_PROVIDERS: dict[str, _Provider] = {
    "deepseek": _Provider("DeepSeek", "DEEPSEEK_API_KEY", DEFAULT_DEEPSEEK_BASE_URL, DEFAULT_DEEPSEEK_MODEL),
    "siliconflow": _Provider(
        "SiliconFlow", "SILICONFLOW_API_KEY", DEFAULT_SILICONFLOW_BASE_URL, DEFAULT_SILICONFLOW_MODEL
    ),
}


class ChatArbitrator:
    """Arbitrator backed by an OpenAI-compatible chat completions endpoint."""

    def __init__(
        self,
        provider: _Provider,
        *,
        api_key: str | None = None,
        timeout_sec: int = 60,
        max_retries: int = 2,
    ) -> None:
        self.provider = provider
        self.api_key = api_key or os.environ.get(provider.api_key_env)
        if not self.api_key:
            raise BackendUnavailableError(
                f"Missing {provider.name} API key. Set {provider.api_key_env}."
            )
        self.base_url = provider.base_url.rstrip("/")
        self.model_name = provider.model_name
        self.timeout_sec = timeout_sec
        self.max_retries = max_retries
        self._cache: dict[tuple[str, str], ArbitrationVerdict | None] = {}

    def __call__(self, request: ArbitrationRequest) -> ArbitrationVerdict | None:
        key = (request.asr_text, request.ocr_text)
        if key not in self._cache:
            self._cache[key] = self._arbitrate(request)
        return self._cache[key]

    def _arbitrate(self, request: ArbitrationRequest) -> ArbitrationVerdict | None:
        payload = {
            "model": self.model_name,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "asr_text": request.asr_text,
                            "ocr_text": request.ocr_text,
                            "output_schema": {"decision": "string", "text": "string", "reason": "string"},
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            "response_format": {"type": "json_object"},
        }
        for _attempt in range(self.max_retries + 1):
            try:
                response = self._post_json(f"{self.base_url}/chat/completions", payload)
                return _verdict_from_response(response)
            except Exception:
                continue
        # Any failure defers to the deterministic review path — never raise from here.
        return None

    def ping(self) -> None:
        """Minimal auth/connectivity check against the chat endpoint.

        Sends a one-token request and raises on any HTTP/network error so a
        caller can surface a precise failure. Does not retry.
        """
        payload = {
            "model": self.model_name,
            "temperature": 0,
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "ping"}],
        }
        self._post_json(f"{self.base_url}/chat/completions", payload)

    def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_sec) as response:
            return json.loads(response.read().decode("utf-8"))


def make_arbitrator(mode: str, **kwargs: Any) -> ChatArbitrator:
    """Build an arbitrator for the given mode ("deepseek" | "siliconflow"). Raises if unknown."""
    provider = _PROVIDERS.get(mode)
    if provider is None:
        raise ValueError(f"Unknown arbitration mode: {mode}")
    return ChatArbitrator(provider, **kwargs)


def test_provider(mode: str, *, api_key: str | None = None, timeout_sec: int = 20) -> dict[str, Any]:
    """Lightweight connectivity/auth check for an arbitration provider.

    Returns ``{"ok": bool, "model": str, "message": str}``. Never raises for
    expected failures (unknown provider, missing key, bad key, network) — the
    failure is encoded in ``ok``/``message`` so the route can return it cleanly.
    """
    provider = _PROVIDERS.get(mode)
    if provider is None:
        return {"ok": False, "model": "", "message": f"Unknown provider: {mode}"}
    key = api_key or os.environ.get(provider.api_key_env)
    if not key:
        return {
            "ok": False,
            "model": provider.model_name,
            "message": f"Missing API key. Set {provider.api_key_env}.",
        }
    try:
        ChatArbitrator(provider, api_key=key, timeout_sec=timeout_sec, max_retries=0).ping()
        return {"ok": True, "model": provider.model_name, "message": "OK"}
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", "replace").strip()
        except Exception:
            body = ""
        message = f"HTTP {exc.code}"
        if body:
            message += f": {body[:300]}"
        return {"ok": False, "model": provider.model_name, "message": message}
    except Exception as exc:  # network errors, timeouts, malformed responses
        return {"ok": False, "model": provider.model_name, "message": str(exc) or type(exc).__name__}


def _verdict_from_response(response: dict[str, Any]) -> ArbitrationVerdict | None:
    parsed = _parse_json_payload(_extract_message_content(response))
    decision = str(parsed.get("decision") or "").strip()
    if decision not in _VALID_DECISIONS:
        return None
    return ArbitrationVerdict(
        decision=decision,
        text=str(parsed.get("text") or "").strip(),
        reason=str(parsed.get("reason") or "").strip(),
    )


__all__ = ["ChatArbitrator", "make_arbitrator", "test_provider"]
