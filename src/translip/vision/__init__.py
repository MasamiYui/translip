"""In-tree video content perception (Qwen3-VL via mlx-vlm / Ollama).

Lazy exports only — importing :mod:`translip.vision` must stay cheap so the
CLI/server can reference it without the optional ``vision`` extra installed.
"""
from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

__all__ = ["AnalyzeRequest", "analyze_video"]

if TYPE_CHECKING:
    from .services.vision_service import AnalyzeRequest, analyze_video


def __getattr__(name: str) -> Any:
    if name in __all__:
        return getattr(import_module(".services.vision_service", __name__), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
