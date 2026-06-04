from __future__ import annotations

from dataclasses import dataclass, field
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
    preview_format: PreviewFormat = "wav"

    def normalized(self) -> "RenderDubRequest":
        return RenderDubRequest(
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
            quality_gate=self.quality_gate,
            target_lang=self.target_lang,
            fit_policy=self.fit_policy,
            fit_backend=self.fit_backend,
            mix_profile=self.mix_profile,
            ducking_mode=self.ducking_mode,
            output_sample_rate=self.output_sample_rate,
            background_gain_db=self.background_gain_db,
            window_ducking_db=self.window_ducking_db,
            max_compress_ratio=self.max_compress_ratio,
            preview_format=self.preview_format,
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
