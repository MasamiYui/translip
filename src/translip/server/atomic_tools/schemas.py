from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, model_validator


class ToolInfo(BaseModel):
    tool_id: str
    name_zh: str
    name_en: str
    description_zh: str
    description_en: str
    category: str
    icon: str
    accept_formats: list[str]
    max_file_size_mb: int
    max_files: int


class FileUploadResponse(BaseModel):
    file_id: str
    filename: str
    size_bytes: int
    content_type: str


JobStatus = Literal["pending", "running", "completed", "failed"]


class JobResponse(BaseModel):
    job_id: str
    tool_id: str
    status: JobStatus
    progress_percent: float
    current_step: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    elapsed_sec: float | None = None
    error_message: str | None = None
    result: dict[str, Any] | None = None


class ArtifactInfo(BaseModel):
    filename: str
    size_bytes: int
    content_type: str
    download_url: str
    file_id: str | None = None


class SeparationToolRequest(BaseModel):
    file_id: str
    mode: str = "auto"
    quality: str = "balanced"
    output_format: str = "wav"


class MixingToolRequest(BaseModel):
    voice_file_id: str
    background_file_id: str
    background_gain_db: float = -8.0
    ducking_mode: str = "static"
    output_format: str = "wav"


class TranscriptionToolRequest(BaseModel):
    file_id: str
    language: str = "zh"
    asr_model: str = "small"
    enable_diarization: bool = False
    generate_srt: bool = True


class TranscriptCorrectionToolRequest(BaseModel):
    segments_file_id: str
    ocr_events_file_id: str
    enabled: bool = True
    preset: Literal["conservative", "standard", "aggressive"] = "standard"
    ocr_only_policy: Literal["report_only"] = "report_only"


class TranslationToolRequest(BaseModel):
    text: str | None = None
    file_id: str | None = None
    source_lang: str = "zh"
    target_lang: str = "en"
    backend: str = "local-m2m100"
    glossary_file_id: str | None = None

    @model_validator(mode="after")
    def validate_input_mode(self) -> "TranslationToolRequest":
        if not self.text and not self.file_id:
            raise ValueError("Either text or file_id is required")
        return self


class TtsToolRequest(BaseModel):
    text: str
    language: str = "auto"
    reference_audio_file_id: str | None = None


class ProbeToolRequest(BaseModel):
    file_id: str


class MuxingToolRequest(BaseModel):
    video_file_id: str
    audio_file_id: str
    video_codec: str = "copy"
    audio_codec: str = "aac"
    audio_bitrate: str = "192k"


SubtitleErasePreset = Literal["fast", "balanced", "quality"]


class SubtitleDetectToolRequest(BaseModel):
    file_id: str
    language: Literal["ch", "en", "ch_tra", "japan", "korean"] = "ch"
    position_mode: Literal["auto", "bottom", "top", "full"] = "bottom"
    roi_bottom_ratio: float = 0.34
    sample_interval: float = 0.4
    merge_threshold: float = 0.78
    preview_frames: int = 3


class SubtitleEraseToolRequest(BaseModel):
    file_id: str
    detection_file_id: str
    preset: SubtitleErasePreset = "fast"
    backend: Literal["telea", "flow-guided", "lama"] | None = None
    mode: Literal["auto", "manual"] = "auto"
    regions: list[tuple[float, float, float, float]] | None = None
    mask_dilate_x: int | None = None
    mask_dilate_y: int | None = None
    mask_temporal_radius: int | None = None
    event_lead_frames: int | None = None
    event_trail_frames: int | None = None
    cleanup_max_coverage: float | None = None
    temporal_consensus: int | None = None
    temporal_std_threshold: float | None = None
    auto_tune: bool = False
