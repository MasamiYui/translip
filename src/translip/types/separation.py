from __future__ import annotations

from dataclasses import dataclass, field, replace
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
        # replace() carries every field; only path resolution is overridden, so a
        # newly added field can't be silently dropped here (cf. ARCH-14).
        return replace(
            self,
            input_path=Path(self.input_path).expanduser().resolve(),
            output_dir=Path(self.output_dir).expanduser().resolve(),
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
