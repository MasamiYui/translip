from __future__ import annotations

from .base import DiarizationBackend, DiarizationResult, DiarizedTurn
from .factory import available_backends, create_backend, resolve_backend_name
from .projection import assign_turns_to_segments, refine_with_change_detection

__all__ = [
    "DiarizationBackend",
    "DiarizationResult",
    "DiarizedTurn",
    "assign_turns_to_segments",
    "available_backends",
    "create_backend",
    "refine_with_change_detection",
    "resolve_backend_name",
]
