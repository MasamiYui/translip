"""Vision backend protocol: load once, chat per unit, close on exit."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class VisionBackend(Protocol):
    backend_name: str
    model_id: str

    def load(self) -> None:
        """Load the model (one-time, before the unit loop)."""

    def chat(self, images: list[Path], prompt: str) -> str:
        """Run one multimodal inference and return the raw text output."""

    def close(self) -> None:
        """Release resources (no-op for subprocess-isolated runs)."""


__all__ = ["VisionBackend"]
