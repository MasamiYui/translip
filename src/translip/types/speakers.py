from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from .common import Device, MediaInfo


@dataclass(slots=True)
class SpeakerRegistryRequest:
    segments_path: Path | str
    audio_path: Path | str
    output_dir: Path | str = Path("output")
    registry_path: Path | str | None = None
    device: Device = "auto"
    top_k: int = 3
    update_registry: bool = False
    keep_intermediate: bool = False

    def normalized(self) -> "SpeakerRegistryRequest":
        # Only paths are transformed; replace() carries every other field (ARCH-14).
        return replace(
            self,
            segments_path=Path(self.segments_path).expanduser().resolve(),
            audio_path=Path(self.audio_path).expanduser().resolve(),
            output_dir=Path(self.output_dir).expanduser().resolve(),
            registry_path=(
                Path(self.registry_path).expanduser().resolve()
                if self.registry_path is not None
                else None
            ),
        )


@dataclass(slots=True)
class SpeakerRegistryArtifacts:
    bundle_dir: Path
    profiles_path: Path
    matches_path: Path
    registry_snapshot_path: Path
    manifest_path: Path
    intermediate_paths: dict[str, Path] = field(default_factory=dict)


@dataclass(slots=True)
class SpeakerRegistryResult:
    request: SpeakerRegistryRequest
    media_info: MediaInfo
    artifacts: SpeakerRegistryArtifacts
    manifest: dict[str, Any]
    work_dir: Path


__all__ = [
    "SpeakerRegistryRequest",
    "SpeakerRegistryArtifacts",
    "SpeakerRegistryResult",
]
