from __future__ import annotations

from dataclasses import dataclass
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
        return ExportVideoRequest(
            input_video_path=(
                Path(self.input_video_path).expanduser().resolve()
                if self.input_video_path is not None
                else None
            ),
            pipeline_root=(
                Path(self.pipeline_root).expanduser().resolve()
                if self.pipeline_root is not None
                else None
            ),
            task_e_dir=(
                Path(self.task_e_dir).expanduser().resolve()
                if self.task_e_dir is not None
                else None
            ),
            output_dir=(
                Path(self.output_dir).expanduser().resolve()
                if self.output_dir is not None
                else None
            ),
            target_lang=self.target_lang,
            export_preview=self.export_preview,
            export_dub=self.export_dub,
            container=self.container,
            video_codec=self.video_codec,
            audio_codec=self.audio_codec,
            audio_bitrate=self.audio_bitrate,
            end_policy=self.end_policy,
            overwrite=self.overwrite,
            keep_temp=self.keep_temp,
            subtitle_mode=self.subtitle_mode,
            subtitle_delivery=self.subtitle_delivery,
            subtitle_source=self.subtitle_source,
            subtitle_style=self.subtitle_style,
            bilingual_chinese_position=self.bilingual_chinese_position,
            bilingual_english_position=self.bilingual_english_position,
            bilingual_export_strategy=self.bilingual_export_strategy,
            embed_original_audio=bool(self.embed_original_audio),
            crf=int(self.crf),
            preset=self.preset,
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
