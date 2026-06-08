from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from .common import (
    DuckingModeName,
    FitBackendName,
    FitPolicy,
    MixProfileName,
    PreviewFormat,
    RenderQualityGate,
)


@dataclass(slots=True)
class RenderDubRequest:
    background_path: Path | str
    segments_path: Path | str
    translation_path: Path | str
    task_d_report_paths: list[Path | str]
    output_dir: Path | str = Path("output")
    selected_segments_path: Path | str | None = None
    quality_gate: RenderQualityGate = "loose"
    target_lang: str = "en"
    fit_policy: FitPolicy = "conservative"
    fit_backend: FitBackendName = "atempo"
    mix_profile: MixProfileName = "preview"
    ducking_mode: DuckingModeName = "static"
    output_sample_rate: int = 48_000
    background_gain_db: float = -8.0
    window_ducking_db: float = -3.0
    max_compress_ratio: float = 1.45
    # Higher "last resort" cap: an over-long line is sped up to this (>=
    # max_compress_ratio) to play whole rather than have its tail cut; only what
    # even this can't absorb is trimmed. Set == max_compress_ratio to disable.
    overflow_max_compress_ratio: float = 1.6
    preview_format: PreviewFormat = "wav"

    def normalized(self) -> "RenderDubRequest":
        # Only paths are transformed; replace() carries every other field (ARCH-14).
        return replace(
            self,
            background_path=Path(self.background_path).expanduser().resolve(),
            segments_path=Path(self.segments_path).expanduser().resolve(),
            translation_path=Path(self.translation_path).expanduser().resolve(),
            task_d_report_paths=[
                Path(path).expanduser().resolve()
                for path in self.task_d_report_paths
            ],
            output_dir=Path(self.output_dir).expanduser().resolve(),
            selected_segments_path=(
                Path(self.selected_segments_path).expanduser().resolve()
                if self.selected_segments_path is not None
                else None
            ),
        )


@dataclass(slots=True)
class RenderDubArtifacts:
    bundle_dir: Path
    dub_voice_path: Path
    preview_mix_wav_path: Path
    timeline_path: Path
    mix_report_path: Path
    manifest_path: Path
    preview_mix_extra_path: Path | None = None
    intermediate_paths: dict[str, Path] = field(default_factory=dict)


@dataclass(slots=True)
class RenderDubResult:
    request: RenderDubRequest
    artifacts: RenderDubArtifacts
    manifest: dict[str, Any]
    work_dir: Path


__all__ = [
    "RenderDubRequest",
    "RenderDubArtifacts",
    "RenderDubResult",
]
