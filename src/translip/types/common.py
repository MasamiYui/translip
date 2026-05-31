from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypedDict, cast

Mode = Literal["music", "dialogue", "auto"]
Route = Literal["music", "dialogue"]
OutputFormat = Literal["wav", "mp3", "flac", "aac", "opus"]
Device = Literal["auto", "cpu", "cuda", "mps"]
Quality = Literal["balanced", "high"]
TranslationBackendName = Literal["local-m2m100", "siliconflow"]
TtsBackendName = Literal["moss-tts-nano-onnx", "qwen3tts", "voxcpm2"]
AsrBackendName = Literal["faster-whisper", "funasr"]
DiarizerBackendName = Literal["ecapa", "pyannote"]
DubbingQualityCheckMode = Literal["standard", "duration-only"]
DUBBING_QUALITY_CHECK_MODES = {"standard", "duration-only"}
CondenseMode = Literal["off", "smart", "aggressive"]
FitPolicy = Literal["conservative", "high_quality"]
FitBackendName = Literal["atempo", "rubberband"]
MixProfileName = Literal["preview", "enhanced"]
DuckingModeName = Literal["static", "sidechain"]
PreviewFormat = Literal["wav", "mp3"]
RenderQualityGate = Literal["loose", "strict"]
CorrectionPreset = Literal["conservative", "standard", "aggressive"]
PipelineStageName = Literal["stage1", "task-a", "asr-ocr-correct", "task-b", "task-c", "task-d", "task-e", "task-g"]
PipelineStageStatus = Literal["pending", "running", "succeeded", "cached", "failed", "skipped"]
WorkflowTemplateName = Literal["asr-dub-basic", "asr-dub+ocr-subs", "asr-dub+ocr-subs+erase"]
WorkflowNodeName = Literal[
    "stage1",
    "ocr-detect",
    "task-a",
    "asr-ocr-correct",
    "task-b",
    "task-c",
    "ocr-translate",
    "task-d",
    "task-e",
    "subtitle-erase",
    "task-g",
]
WorkflowNodeGroup = Literal["audio-spine", "ocr-subtitles", "video-cleanup", "delivery"]
WorkflowNodeStatus = Literal["pending", "running", "succeeded", "cached", "failed", "skipped"]
WorkflowStatus = Literal["pending", "running", "succeeded", "partial_success", "failed"]
DeliveryVideoSource = Literal["original", "clean", "clean_if_available"]
DeliveryAudioSource = Literal["preview_mix", "dub_voice", "preview", "dub", "both", "original"]
DeliverySubtitleSource = Literal["none", "asr", "ocr", "both"]
DeliveryContainer = Literal["mp4"]
DeliveryVideoCodec = Literal["copy", "libx264"]
DeliveryAudioCodec = Literal["aac"]
DeliveryEndPolicy = Literal["trim_audio_to_video", "keep_longest"]
SubtitleCompositionMode = Literal["none", "chinese_only", "english_only", "bilingual"]
SubtitleSourceType = Literal["ocr", "asr"]
SubtitlePosition = Literal["top", "bottom"]
BilingualExportStrategy = Literal[
    "auto_standard_bilingual",
    "preserve_hard_subtitles_add_english",
    "clean_video_rebuild_bilingual",
]


class DeliveryPolicy(TypedDict):
    video_source: DeliveryVideoSource
    audio_source: DeliveryAudioSource
    subtitle_source: DeliverySubtitleSource


class TranscriptionCorrectionConfig(TypedDict, total=False):
    enabled: bool
    preset: CorrectionPreset
    min_ocr_confidence: float
    min_alignment_score: float
    lead_tolerance_sec: float
    lag_tolerance_sec: float
    min_length_ratio: float
    max_length_ratio: float
    ocr_only_policy: Literal["report_only"]
    llm_arbitration: Literal["off", "deepseek", "siliconflow"]


@dataclass(slots=True)
class SubtitleStyle:
    font_family: str = "Noto Sans CJK SC"
    font_size: int = 0
    primary_color: str = "#FFFFFF"
    outline_color: str = "#000000"
    outline_width: float = 2.0
    shadow_depth: float = 1.0
    bold: bool = False
    position: SubtitlePosition = "bottom"
    margin_v: int = 0
    margin_h: int = 20
    alignment: int = 2


def normalize_dubbing_quality_check_mode(value: object | None) -> DubbingQualityCheckMode:
    text = str(value or "standard").strip().lower()
    return cast(DubbingQualityCheckMode, text)


@dataclass(slots=True)
class MediaInfo:
    path: Path
    media_type: Literal["audio", "video"]
    format_name: str | None
    duration_sec: float
    audio_stream_index: int | None
    audio_stream_count: int
    sample_rate: int | None
    channels: int | None


__all__ = [
    "Mode",
    "Route",
    "OutputFormat",
    "Device",
    "Quality",
    "TranslationBackendName",
    "TtsBackendName",
    "AsrBackendName",
    "DiarizerBackendName",
    "DubbingQualityCheckMode",
    "DUBBING_QUALITY_CHECK_MODES",
    "CondenseMode",
    "FitPolicy",
    "FitBackendName",
    "MixProfileName",
    "DuckingModeName",
    "PreviewFormat",
    "RenderQualityGate",
    "CorrectionPreset",
    "PipelineStageName",
    "PipelineStageStatus",
    "WorkflowTemplateName",
    "WorkflowNodeName",
    "WorkflowNodeGroup",
    "WorkflowNodeStatus",
    "WorkflowStatus",
    "DeliveryVideoSource",
    "DeliveryAudioSource",
    "DeliverySubtitleSource",
    "DeliveryContainer",
    "DeliveryVideoCodec",
    "DeliveryAudioCodec",
    "DeliveryEndPolicy",
    "SubtitleCompositionMode",
    "SubtitleSourceType",
    "SubtitlePosition",
    "BilingualExportStrategy",
    "DeliveryPolicy",
    "TranscriptionCorrectionConfig",
    "SubtitleStyle",
    "normalize_dubbing_quality_check_mode",
    "MediaInfo",
]
