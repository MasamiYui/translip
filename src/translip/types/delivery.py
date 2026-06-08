from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .common import (
    BilingualExportStrategy,
    DeliveryAudioCodec,
    DeliveryContainer,
    DeliveryEndPolicy,
    DeliveryVideoCodec,
    SubtitleCompositionMode,
    SubtitleDeliveryMode,
    SubtitlePosition,
    SubtitleSourceType,
    SubtitleStyle,
)


@dataclass(slots=True)
class ExportVideoRequest:
    input_video_path: Path | str | None = None
    pipeline_root: Path | str | None = None
    task_e_dir: Path | str | None = None
    output_dir: Path | str | None = None
    target_lang: str | None = None
    export_preview: bool = True
    export_dub: bool = True
    container: DeliveryContainer = "mp4"
    video_codec: DeliveryVideoCodec = "copy"
    audio_codec: DeliveryAudioCodec = "aac"
    audio_bitrate: str | None = "192k"
    end_policy: DeliveryEndPolicy = "trim_audio_to_video"
    overwrite: bool = True
    keep_temp: bool = False
    subtitle_mode: SubtitleCompositionMode = "none"
    subtitle_delivery: SubtitleDeliveryMode = "burn"
    subtitle_source: SubtitleSourceType = "ocr"
    subtitle_style: SubtitleStyle | None = None
    bilingual_chinese_position: SubtitlePosition = "bottom"
    bilingual_english_position: SubtitlePosition = "top"
    bilingual_export_strategy: BilingualExportStrategy = "auto_standard_bilingual"
    embed_original_audio: bool = False
    crf: int = 18
    preset: str = "medium"

    def normalized(self) -> "ExportVideoRequest":
        # Only these fields are transformed; replace() carries every other field,
        # so a newly added field can't be silently dropped here (ARCH-14).
        def _resolve(value: Path | str | None) -> Path | None:
            return Path(value).expanduser().resolve() if value is not None else None

        return replace(
            self,
            input_video_path=_resolve(self.input_video_path),
            pipeline_root=_resolve(self.pipeline_root),
            task_e_dir=_resolve(self.task_e_dir),
            output_dir=_resolve(self.output_dir),
            embed_original_audio=bool(self.embed_original_audio),
            crf=int(self.crf),
        )


@dataclass(slots=True)
class ExportVideoArtifacts:
    output_dir: Path
    preview_video_path: Path | None
    dub_video_path: Path | None
    manifest_path: Path
    report_path: Path


@dataclass(slots=True)
class ExportVideoResult:
    request: ExportVideoRequest
    artifacts: ExportVideoArtifacts
    manifest: dict[str, Any]
    report: dict[str, Any]


__all__ = [
    "ExportVideoRequest",
    "ExportVideoArtifacts",
    "ExportVideoResult",
]
