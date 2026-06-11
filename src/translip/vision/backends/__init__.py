"""Backend resolution for the vision module.

``resolve_backend_name`` is the cheap pure function the orchestrator calls when
computing cache keys (platform check + find_spec + HTTP probe — never loads a
model), so an ``auto`` request resolves to the same concrete backend in both the
cache key and the worker subprocess. ``create_backend`` is the heavy factory the
subprocess uses.
"""
from __future__ import annotations

import importlib.util
import json
import platform
import urllib.error
import urllib.request

from ..config import VisionSettings, load_settings
from .base import VisionBackend


class VisionDependencyError(RuntimeError):
    """No usable vision backend is available (clear, actionable message)."""


def _mlx_available() -> bool:
    return (
        platform.system() == "Darwin"
        and platform.machine() == "arm64"
        and importlib.util.find_spec("mlx_vlm") is not None
    )


def _ollama_available(host: str, model: str, *, timeout_sec: float = 2.0) -> bool:
    """Probe the Ollama server and check the requested model tag is pulled."""
    try:
        with urllib.request.urlopen(f"{host.rstrip('/')}/api/tags", timeout=timeout_sec) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return False
    wanted = model.split(":", 1)[0]
    for entry in payload.get("models", []):
        name = str(entry.get("name") or entry.get("model") or "")
        if name == model or name.split(":", 1)[0] == wanted:
            return True
    return False


def resolve_backend_name(settings: VisionSettings | None = None) -> tuple[str, str]:
    """Resolve ``auto`` to a concrete ``(backend_name, model_id)`` pair.

    Lightweight by contract — safe to call from the orchestrator when building
    cache keys. Raises :class:`VisionDependencyError` when nothing is usable.
    """
    settings = settings or load_settings()
    requested = settings.backend

    if requested == "mlx":
        if not _mlx_available():
            raise VisionDependencyError(
                "Vision backend 'mlx' requires Apple Silicon and the mlx-vlm package. "
                "Install it with: uv sync --extra vision"
            )
        return "mlx", settings.model
    if requested == "ollama":
        if not _ollama_available(settings.ollama_host, settings.ollama_model):
            raise VisionDependencyError(
                f"Vision backend 'ollama' is not reachable at {settings.ollama_host} or the model "
                f"'{settings.ollama_model}' is not pulled. Start ollama and run: "
                f"ollama pull {settings.ollama_model}"
            )
        return "ollama", settings.ollama_model
    if requested != "auto":
        raise VisionDependencyError(f"Unknown vision backend: {requested!r} (use auto|mlx|ollama)")

    if _mlx_available():
        return "mlx", settings.model
    if _ollama_available(settings.ollama_host, settings.ollama_model):
        return "ollama", settings.ollama_model
    raise VisionDependencyError(
        "No vision backend available. On Apple Silicon install mlx-vlm with "
        "`uv sync --extra vision`; on other platforms start an Ollama server and "
        f"run `ollama pull {settings.ollama_model}` (host: {settings.ollama_host})."
    )


def create_backend(settings: VisionSettings | None = None) -> VisionBackend:
    """Instantiate the resolved backend (heavy deps imported lazily inside)."""
    settings = settings or load_settings()
    backend_name, model_id = resolve_backend_name(settings)
    if backend_name == "mlx":
        from .mlx_backend import MlxVisionBackend

        return MlxVisionBackend(settings=settings, model_id=model_id)
    from .ollama_backend import OllamaVisionBackend

    return OllamaVisionBackend(settings=settings, model_id=model_id)


__all__ = ["VisionBackend", "VisionDependencyError", "create_backend", "resolve_backend_name"]
