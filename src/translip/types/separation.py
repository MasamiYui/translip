from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .common import (
    Device,
    MediaInfo,
    Mode,
    OutputFormat,
    Quality,
    Route,
)


@dataclass(slots=True)
class SeparationRequest:
    input_path: Path | str
    mode: Mode = "auto"
    output_dir: Path | str = Path("output")
    output_format: OutputFormat = "wav"
    quality: Quality = "balanced"
    cdx23_overlap: float | None = None
    cdx23_shifts: int | None = None
    sample_rate: int | None = None
    bitrate: str | None = None
    enhance_voice: bool = False
    device: Device = "auto"
    keep_intermediate: bool = False
    backend_music: str = "demucs"
    backend_dialogue: str = "cdx23"
    audio_stream_index: int = 0

    def normalized(self) -> "SeparationRequest":
        return SeparationRequest(
            input_path=Path(self.input_path).expanduser().resolve(),
            mode=self.mode,
            output_dir=Path(self.output_dir).expanduser().resolve(),
            output_format=self.output_format,
            quality=self.quality,
            cdx23_overlap=self.cdx23_overlap,
            cdx23_shifts=self.cdx23_shifts,
            sample_rate=self.sample_rate,
            bitrate=self.bitrate,
            enhance_voice=self.enhance_voice,
            device=self.device,
            keep_intermediate=self.keep_intermediate,
            backend_music=self.backend_music,
            backend_dialogue=self.backend_dialogue,
            audio_stream_index=self.audio_stream_index,
        )


@dataclass(slots=True)
class RouteDecision:
    route: Route
    reason: str
    metrics: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class MusicSeparationOutput:
    voice_path: Path
    background_path: Path
    backend_name: str
    intermediate_paths: dict[str, Path] = field(default_factory=dict)


@dataclass(slots=True)
class DialogueSeparationOutput:
    dialog_path: Path
    background_path: Path
    backend_name: str
    intermediate_paths: dict[str, Path] = field(default_factory=dict)


@dataclass(slots=True)
class SeparationArtifacts:
    bundle_dir: Path
    voice_path: Path
    background_path: Path
    manifest_path: Path
    intermediate_paths: dict[str, Path] = field(default_factory=dict)


@dataclass(slots=True)
class SeparationResult:
    request: SeparationRequest
    media_info: MediaInfo
    route: RouteDecision
    artifacts: SeparationArtifacts
    manifest: dict[str, Any]
    work_dir: Path


__all__ = [
    "SeparationRequest",
    "RouteDecision",
    "MusicSeparationOutput",
    "DialogueSeparationOutput",
    "SeparationArtifacts",
    "SeparationResult",
]
