from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from .common import (
    Device,
    DubbingQualityCheckMode,
    TtsBackendName,
    normalize_dubbing_quality_check_mode,
)


@dataclass(slots=True)
class DubbingRequest:
    translation_path: Path | str
    profiles_path: Path | str
    output_dir: Path | str = Path("output")
    speaker_id: str = ""
    backend: TtsBackendName = "moss-tts-nano-onnx"
    device: Device = "auto"
    reference_clip_path: Path | str | None = None
    voice_bank_path: Path | str | None = None
    segment_ids: list[str] | None = None
    max_segments: int | None = None
    dubbing_workers: int | None = None
    quality_check_mode: DubbingQualityCheckMode = "standard"
    keep_intermediate: bool = False
    backread_model: str = "tiny"

    def normalized(self) -> "DubbingRequest":
        # Only these fields are transformed; replace() carries every other field,
        # so a newly added field can't be silently dropped here (ARCH-14).
        return replace(
            self,
            translation_path=Path(self.translation_path).expanduser().resolve(),
            profiles_path=Path(self.profiles_path).expanduser().resolve(),
            output_dir=Path(self.output_dir).expanduser().resolve(),
            reference_clip_path=(
                Path(self.reference_clip_path).expanduser().resolve()
                if self.reference_clip_path is not None
                else None
            ),
            voice_bank_path=(
                Path(self.voice_bank_path).expanduser().resolve()
                if self.voice_bank_path is not None
                else None
            ),
            segment_ids=list(self.segment_ids) if self.segment_ids else None,
            quality_check_mode=normalize_dubbing_quality_check_mode(self.quality_check_mode),
        )


@dataclass(slots=True)
class DubbingArtifacts:
    bundle_dir: Path
    segments_dir: Path
    report_path: Path
    manifest_path: Path
    demo_audio_path: Path | None = None
    intermediate_paths: dict[str, Path] = field(default_factory=dict)


@dataclass(slots=True)
class DubbingResult:
    request: DubbingRequest
    artifacts: DubbingArtifacts
    manifest: dict[str, Any]
    work_dir: Path


__all__ = [
    "DubbingRequest",
    "DubbingArtifacts",
    "DubbingResult",
]
