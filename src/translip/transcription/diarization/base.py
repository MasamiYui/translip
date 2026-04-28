from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..asr import AsrSegment


@dataclass(slots=True)
class DiarizedTurn:
    """A homogeneous speaker-active region produced by a diarization backend."""

    start: float
    end: float
    speaker_id: int

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass(slots=True)
class DiarizationResult:
    """Container for a diarization run plus backend-level metadata."""

    turns: list[DiarizedTurn]
    backend: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def speaker_count(self) -> int:
        return len({turn.speaker_id for turn in self.turns})


class DiarizationBackend(ABC):
    """Abstract interface for speaker diarization backends used in task-a."""

    name: str = "abstract"

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if runtime prerequisites (models, deps) are satisfied."""

    @abstractmethod
    def diarize(
        self,
        audio_path: Path,
        *,
        segments: list[AsrSegment],
        requested_device: str,
    ) -> DiarizationResult:
        """Run diarization on the given audio and return a timeline of turns."""
