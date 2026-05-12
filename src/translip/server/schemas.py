from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class TaskStageRead(BaseModel):
    stage_name: str
    status: str
    progress_percent: float
    current_step: Optional[str] = None
    cache_hit: bool = False
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    elapsed_sec: Optional[float] = None
    manifest_path: Optional[str] = None
    error_message: Optional[str] = None


class TaskRead(BaseModel):
    id: str
    name: str
    status: str
    input_path: str
    output_root: str
    work_id: Optional[str] = None
    episode_label: Optional[str] = None
    source_lang: str
    target_lang: str
    output_intent: str = "dub_final"
    quality_preset: str = "standard"
    config: Dict[str, Any]
    delivery_config: Dict[str, Any]
    hard_subtitle_status: str = "none"
    asset_summary: Dict[str, Any] = {}
    export_readiness: Dict[str, Any] = {}
    last_export_summary: Dict[str, Any] = {}
    transcription_correction_summary: Dict[str, Any] = {}
    overall_progress: float
    current_stage: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    elapsed_sec: Optional[float] = None
    error_message: Optional[str] = None
    manifest_path: Optional[str] = None
    parent_task_id: Optional[str] = None
    stages: List[TaskStageRead] = []


class TaskListResponse(BaseModel):
    items: List[TaskRead]
    total: int
    page: int
    size: int


class WorkflowGraphNodeRead(BaseModel):
    id: str
    label: str
    group: str
    required: bool
    status: str
    progress_percent: float
    manifest_path: Optional[str] = None
    log_path: Optional[str] = None
    error_message: Optional[str] = None


class TaskGraphRead(BaseModel):
    workflow: Dict[str, Any]
    nodes: List[WorkflowGraphNodeRead]
    edges: List[Dict[str, str]]


class TaskConfigInput(BaseModel):
    device: str = "auto"
    output_intent: str = "dub_final"
    quality_preset: str = "standard"
    template: str = "asr-dub-basic"
    run_from_stage: str = "stage1"
    run_to_stage: str = "task-g"
    use_cache: bool = True
    keep_intermediate: bool = False
    video_source: str = "original"
    audio_source: str = "both"
    subtitle_source: str = "asr"
    ocr_project_root: Optional[str] = None
    erase_project_root: Optional[str] = None
    # Stage 1
    separation_mode: str = "auto"
    separation_quality: str = "balanced"
    music_backend: str = "demucs"
    dialogue_backend: str = "cdx23"
    # Task A
    asr_model: str = "small"
    generate_srt: bool = True
    transcription_correction: Dict[str, Any] = {
        "enabled": True,
        "preset": "standard",
        "ocr_only_policy": "report_only",
        "llm_arbitration": "off",
    }
    # Task B
    existing_registry: Optional[str] = None
    top_k: int = 3
    # Task C
    translation_backend: str = "local-m2m100"
    translation_glossary: Optional[str] = None
    translation_batch_size: int = 4
    siliconflow_base_url: Optional[str] = None
    siliconflow_model: Optional[str] = None
    condense_mode: str = "off"
    # Task D
    tts_backend: str = "moss-tts-nano-onnx"
    max_segments: Optional[int] = None
    dub_repair_enabled: bool = False
    dub_repair_backend: List[str] = []
    dub_repair_max_items: int = 12
    dub_repair_attempts_per_item: int = 3
    dub_repair_include_risk: bool = False
    # Task E
    fit_policy: str = "conservative"
    fit_backend: str = "atempo"
    mix_profile: str = "preview"
    ducking_mode: str = "static"
    background_gain_db: float = -8.0
    # Task G
    export_preview: bool = True
    export_dub: bool = True
    delivery_container: str = "mp4"
    delivery_video_codec: str = "copy"
    delivery_audio_codec: str = "aac"
    subtitle_mode: str = "none"
    subtitle_render_source: str = "ocr"
    subtitle_font: Optional[str] = None
    subtitle_font_size: int = 0
    subtitle_color: str = "#FFFFFF"
    subtitle_outline_color: str = "#000000"
    subtitle_outline_width: float = 2.0
    subtitle_position: str = "bottom"
    subtitle_margin_v: int = 0
    subtitle_bold: bool = False
    bilingual_chinese_position: str = "bottom"
    bilingual_english_position: str = "top"
    bilingual_export_strategy: str = "auto_standard_bilingual"
    subtitle_preview_duration_sec: float = 10.0


class CreateTaskRequest(BaseModel):
    name: str
    input_path: str
    source_lang: str = "zh"
    target_lang: str = "en"
    config: TaskConfigInput = TaskConfigInput()
    output_root: Optional[str] = None
    save_as_preset: bool = False
    preset_name: Optional[str] = None


class RerunTaskRequest(BaseModel):
    from_stage: str = "stage1"


class ConfigPresetRead(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    source_lang: str
    target_lang: str
    config: Dict[str, Any]
    created_at: datetime
    updated_at: datetime


class CreatePresetRequest(BaseModel):
    name: str
    description: Optional[str] = None
    source_lang: str = "zh"
    target_lang: str = "en"
    config: Dict[str, Any]


class SystemInfo(BaseModel):
    python_version: str
    device: str
    cache_dir: str
    cache_size_bytes: int
    pipeline_output_root: str
    models: List[Dict[str, Any]] = []


class MediaProbeResult(BaseModel):
    path: str
    duration_sec: float
    has_video: bool
    has_audio: bool
    width: Optional[int] = None
    height: Optional[int] = None
    sample_rate: Optional[int] = None
    format_name: Optional[str] = None
