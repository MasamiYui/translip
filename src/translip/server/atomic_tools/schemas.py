from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from ...config import SUPPORTED_DUBBING_BACKENDS


class ToolInfo(BaseModel):
    tool_id: str = Field(description="工具唯一标识")
    name_zh: str = Field(description="工具中文名")
    name_en: str = Field(description="工具英文名")
    description_zh: str = Field(description="工具中文说明")
    description_en: str = Field(description="工具英文说明")
    category: str = Field(description="工具分类，如 audio / video")
    icon: str = Field(description="图标名（前端 lucide 图标）")
    accept_formats: list[str] = Field(description="接受的输入文件扩展名列表")
    max_file_size_mb: int = Field(description="单文件大小上限（MB）")
    max_files: int = Field(description="单次允许上传的文件数上限")


class FileUploadResponse(BaseModel):
    file_id: str = Field(description="已上传文件的 ID，后续作业用它引用该文件")
    filename: str = Field(description="原始文件名")
    size_bytes: int = Field(description="文件大小（字节）")
    content_type: str = Field(description="MIME 类型")


JobStatus = Literal["pending", "running", "completed", "failed", "cancelled", "interrupted"]


class JobResponse(BaseModel):
    job_id: str = Field(description="作业 ID")
    tool_id: str = Field(description="所属工具 ID")
    status: JobStatus = Field(description="作业状态：pending/running/completed/failed/cancelled/interrupted")
    progress_percent: float = Field(description="进度百分比（0–100）")
    current_step: str | None = Field(default=None, description="当前步骤描述")
    created_at: datetime = Field(description="创建时间")
    started_at: datetime | None = Field(default=None, description="开始执行时间")
    finished_at: datetime | None = Field(default=None, description="结束时间")
    elapsed_sec: float | None = Field(default=None, description="已耗时（秒）")
    error_message: str | None = Field(default=None, description="失败时的错误信息")
    result: dict[str, Any] | None = Field(default=None, description="成功时的结果数据（各工具结构不同）")


class ArtifactInfo(BaseModel):
    filename: str = Field(description="产物文件名")
    size_bytes: int = Field(description="文件大小（字节）")
    content_type: str = Field(description="MIME 类型")
    download_url: str = Field(description="下载地址")
    file_id: str | None = Field(default=None, description="产物在存储中的文件 ID，可用于二次加工")


class AtomicStoredFileInfo(BaseModel):
    file_id: str = Field(description="文件 ID")
    filename: str = Field(description="文件名")
    size_bytes: int = Field(description="文件大小（字节）")
    content_type: str = Field(description="MIME 类型")


class AtomicJobRead(JobResponse):
    tool_name: str = Field(description="工具显示名")
    input_files: list[AtomicStoredFileInfo] = Field(default=[], description="输入文件列表")
    artifact_count: int = Field(default=0, description="产物文件数量")
    updated_at: datetime | None = Field(default=None, description="最近更新时间")


class AtomicJobDetail(AtomicJobRead):
    params: dict[str, Any] = Field(default={}, description="运行参数（提交作业时的参数快照）")
    artifacts: list[ArtifactInfo] = Field(default=[], description="产物文件详情列表")


class AtomicJobListResponse(BaseModel):
    items: list[AtomicJobRead] = Field(description="当前页的作业列表")
    total: int = Field(description="作业总数")
    page: int = Field(description="当前页码")
    size: int = Field(description="每页数量")


class SeparationToolRequest(BaseModel):
    file_id: str
    mode: str = "auto"
    quality: str = "balanced"
    output_format: str = "wav"
    cdx23_overlap: float | None = Field(default=None, gt=0, le=1)
    cdx23_shifts: int | None = Field(default=None, ge=0)


class MixingToolRequest(BaseModel):
    voice_file_id: str
    background_file_id: str
    background_gain_db: float = -8.0
    ducking_mode: str = "static"
    output_format: str = "wav"


class TranscriptionToolRequest(BaseModel):
    file_id: str
    language: str = "zh"
    asr_model: str = "paraformer-zh"
    asr_backend: Literal["faster-whisper", "funasr"] = "funasr"
    diarizer_backend: Literal["ecapa", "pyannote"] = "ecapa"
    enable_diarization: bool = False
    generate_srt: bool = True
    vad_filter: bool = True
    vad_min_silence_duration_ms: int = Field(default=400, gt=0)
    vad_max_segment_sec: float = Field(default=30.0, gt=0)
    beam_size: int = Field(default=5, gt=0)
    best_of: int = Field(default=5, gt=0)
    temperature: float = Field(default=0.0, ge=0)
    condition_on_previous_text: bool = False


class TranscriptCorrectionToolRequest(BaseModel):
    segments_file_id: str
    ocr_events_file_id: str
    enabled: bool = True
    preset: Literal["conservative", "standard", "aggressive"] = "standard"
    ocr_only_policy: Literal["report_only"] = "report_only"
    llm_arbitration: Literal["off", "deepseek"] = "off"


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
    backend: str = "qwen3tts"
    reference_audio_file_id: str | None = None

    @model_validator(mode="after")
    def validate_backend(self) -> "TtsToolRequest":
        if self.backend not in SUPPORTED_DUBBING_BACKENDS:
            raise ValueError(
                f"Unsupported TTS backend: {self.backend}. "
                f"Choose one of: {', '.join(SUPPORTED_DUBBING_BACKENDS)}"
            )
        if self.backend in {"moss-tts-nano-onnx", "voxcpm2"} and not self.reference_audio_file_id:
            raise ValueError(
                f"The {self.backend} backend requires a reference audio upload for voice cloning."
            )
        return self


class ProbeToolRequest(BaseModel):
    file_id: str


class MuxingToolRequest(BaseModel):
    video_file_id: str
    audio_file_id: str
    video_codec: str = "copy"
    audio_codec: str = "aac"
    audio_bitrate: str = "192k"


SubtitleErasePreset = Literal["balanced", "quality"]


class SubtitleDetectToolRequest(BaseModel):
    file_id: str
    language: Literal["ch", "en", "ch_tra", "japan", "korean"] = "ch"
    sample_interval: float = 0.4
    preview_frames: int = 3
    position_mode: Literal["auto", "bottom", "middle", "top"] = "auto"
    extraction_mode: Literal["conservative", "balanced", "variety_recall"] = "conservative"


VideoAnalyzeTask = Literal["scene-context", "erase-qc", "ocr-classify", "freeform"]


class VideoAnalyzeToolRequest(BaseModel):
    file_id: str = Field(description="待分析视频的文件 ID")
    task: VideoAnalyzeTask = Field(
        default="scene-context",
        description="分析任务：scene-context=场景描述；erase-qc=擦除质检；ocr-classify=画面文字分类（需上传 OCR 事件 JSON）；freeform=自由问答",
    )
    question: str | None = Field(default=None, description="自由问答的问题（task=freeform 时必填）")
    detection_file_id: str | None = Field(
        default=None,
        description="OCR 事件 JSON（ocr_events.json / detection.json）的文件 ID；ocr-classify 必填，erase-qc 可选（提供则只检查原字幕区间）",
    )
    sample_interval: float = Field(default=10.0, gt=0, description="无字幕分段时的固定采样间隔（秒）")
    frames_per_unit: int = Field(default=4, ge=1, le=8, description="每个分析单元抽取的帧数")
    lang: Literal["zh", "en"] = Field(default="zh", description="分析输出语言")
    max_units: int | None = Field(default=None, ge=1, description="最多分析的单元数（均匀抽样，控制耗时）")
    backend: Literal["auto", "mlx", "ollama"] = Field(default="auto", description="推理后端")

    @model_validator(mode="after")
    def validate_task_inputs(self) -> "VideoAnalyzeToolRequest":
        if self.task == "freeform" and not (self.question or "").strip():
            raise ValueError("task=freeform requires a question")
        if self.task == "ocr-classify" and not self.detection_file_id:
            raise ValueError("task=ocr-classify requires detection_file_id (OCR events JSON)")
        return self


class SubtitleEraseToolRequest(BaseModel):
    file_id: str
    detection_file_id: str | None = None
    preset: SubtitleErasePreset = "balanced"
    backend: Literal["sttn", "lama"] | None = None
    device: Literal["auto", "mps", "cuda", "cpu"] | None = None
    sample_interval: float | None = None
    regions: list[tuple[float, float, float, float]] | None = None
    mask_dilate_x: int | None = None
    mask_dilate_y: int | None = None
    event_lead_frames: int | None = None
    event_trail_frames: int | None = None
    neighbor_stride: int | None = None
    reference_length: int | None = None
    max_load: int | None = None
