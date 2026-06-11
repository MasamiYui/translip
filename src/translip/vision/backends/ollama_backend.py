"""Ollama HTTP backend (stdlib urllib only — works without the vision extra)."""
from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from pathlib import Path

from ..config import VisionSettings


class OllamaVisionBackend:
    backend_name = "ollama"

    def __init__(self, *, settings: VisionSettings, model_id: str) -> None:
        self._settings = settings
        self.model_id = model_id

    def load(self) -> None:
        # The server owns the model; nothing to load client-side.
        return None

    def chat(self, images: list[Path], prompt: str) -> str:
        payload = {
            "model": self.model_id,
            "stream": False,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [
                        base64.b64encode(path.read_bytes()).decode("ascii") for path in images
                    ],
                }
            ],
            "options": {
                "temperature": self._settings.temperature,
                "num_predict": self._settings.max_new_tokens,
            },
        }
        request = urllib.request.Request(
            f"{self._settings.ollama_host.rstrip('/')}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._settings.timeout_sec) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise RuntimeError(f"ollama chat failed ({exc.code}): {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RuntimeError(f"ollama chat failed: {exc}") from exc
        return str((body.get("message") or {}).get("content") or "")

    def close(self) -> None:
        return None


__all__ = ["OllamaVisionBackend"]
