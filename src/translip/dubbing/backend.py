from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from ..utils.torch_device import resolve_torch_device


@dataclass(slots=True)
class ReferencePackage:
    speaker_id: str
    profile_id: str
    original_audio_path: Path
    prepared_audio_path: Path
    text: str
    duration_sec: float
    score: float
    selection_reason: str


@dataclass(slots=True)
class SynthSegmentInput:
    segment_id: str
    speaker_id: str
    target_lang: str
    target_text: str
    source_duration_sec: float
    duration_budget_sec: float | None
    qa_flags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SynthSegmentOutput:
    segment_id: str
    audio_path: Path
    sample_rate: int
    generated_duration_sec: float
    backend_metadata: dict[str, Any] = field(default_factory=dict)


class TTSBackend(Protocol):
    backend_name: str
    resolved_model: str
    resolved_device: str

    def synthesize(
        self,
        *,
        reference: ReferencePackage,
        segment: SynthSegmentInput,
        output_path: Path,
    ) -> SynthSegmentOutput:
        ...


def resolve_tts_device(requested_device: str) -> str:
    return resolve_torch_device(requested_device)
