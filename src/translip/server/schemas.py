from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class TaskStageRead(BaseModel):
    stage_name: str = Field(description="阶段名称，如 separation、transcription 至 delivery")
    status: str = Field(description="该阶段的执行状态")
    progress_percent: float = Field(description="该阶段进度百分比")
    current_step: Optional[str] = Field(default=None, description="当前正在执行的子步骤描述")
    cache_hit: bool = Field(default=False, description="是否命中缓存（命中则跳过重算）")
    started_at: Optional[datetime] = Field(default=None, description="该阶段开始时间")
    finished_at: Optional[datetime] = Field(default=None, description="该阶段结束时间")
    elapsed_sec: Optional[float] = Field(default=None, description="该阶段耗时（秒）")
    manifest_path: Optional[str] = Field(default=None, description="该阶段产物清单（manifest）文件路径")
    error_message: Optional[str] = Field(default=None, description="该阶段失败时的错误信息")


class TaskRead(BaseModel):
    id: str = Field(description="任务唯一标识")
    name: str = Field(description="任务名称")
    status: str = Field(description="任务整体状态")
    input_path: str = Field(description="输入视频/音频文件路径")
    output_root: str = Field(description="该任务产物输出根目录")
    work_id: Optional[str] = Field(default=None, description="所属作品（work）标识")
    episode_label: Optional[str] = Field(default=None, description="剧集/分集标签")
    source_lang: str = Field(description="源语言")
    target_lang: str = Field(description="目标语言")
    output_intent: str = Field(default="dub_final", description="输出目标，如最终配音成片")
    quality_preset: str = Field(default="standard", description="质量预设")
    config: Dict[str, Any] = Field(description="任务运行配置（流水线各阶段参数）")
    delivery_config: Dict[str, Any] = Field(description="导出/交付相关配置")
    hard_subtitle_status: str = Field(default="none", description="硬字幕处理状态（OCR/擦除）")
    asset_summary: Dict[str, Any] = Field(default={}, description="产物资产概览")
    export_readiness: Dict[str, Any] = Field(default={}, description="导出就绪情况摘要")
    last_export_summary: Dict[str, Any] = Field(default={}, description="最近一次导出结果摘要")
    transcription_correction_summary: Dict[str, Any] = Field(default={}, description="转写校正结果摘要")
    overall_progress: float = Field(description="任务整体进度百分比")
    current_stage: Optional[str] = Field(default=None, description="当前正在执行的阶段名称")
    created_at: datetime = Field(description="任务创建时间")
    updated_at: datetime = Field(description="任务最后更新时间")
    started_at: Optional[datetime] = Field(default=None, description="任务开始时间")
    finished_at: Optional[datetime] = Field(default=None, description="任务结束时间")
    elapsed_sec: Optional[float] = Field(default=None, description="任务总耗时（秒）")
    error_message: Optional[str] = Field(default=None, description="任务失败时的错误信息")
    manifest_path: Optional[str] = Field(default=None, description="流水线产物清单（manifest）文件路径")
    parent_task_id: Optional[str] = Field(default=None, description="父任务标识（重跑/派生任务时指向源任务）")
    stages: List[TaskStageRead] = Field(default=[], description="各阶段的执行状态列表")


class TaskListResponse(BaseModel):
    items: List[TaskRead] = Field(description="当前页的任务列表")
    total: int = Field(description="任务总数")
    page: int = Field(description="当前页码")
    size: int = Field(description="每页数量")


class WorkflowGraphNodeRead(BaseModel):
    id: str = Field(description="流水线节点标识")
    label: str = Field(description="节点显示名称")
    group: str = Field(description="节点所属分组")
    required: bool = Field(description="该节点在当前工作流中是否必需")
    status: str = Field(description="该节点的执行状态")
    progress_percent: float = Field(description="该节点进度百分比")
    manifest_path: Optional[str] = Field(default=None, description="该节点产物清单（manifest）文件路径")
    log_path: Optional[str] = Field(default=None, description="该节点日志文件路径")
    error_message: Optional[str] = Field(default=None, description="该节点失败时的错误信息")


class TaskGraphRead(BaseModel):
    workflow: Dict[str, Any] = Field(description="工作流模板信息")
    nodes: List[WorkflowGraphNodeRead] = Field(description="流水线节点列表")
    edges: List[Dict[str, str]] = Field(description="节点间依赖边列表")


class TaskConfigInput(BaseModel):
    device: str = Field(default="auto", description="计算设备，auto 为自动选择")
    output_intent: str = Field(default="dub_final", description="输出目标，如最终配音成片")
    quality_preset: str = Field(default="standard", description="整体质量预设")
    template: str = Field(default="asr-dub-basic", description="工作流模板，决定运行哪些节点")
    run_from_stage: str = Field(default="separation", description="起始阶段，从该阶段开始运行")
    run_to_stage: str = Field(default="delivery", description="结束阶段，运行至该阶段为止")
    use_cache: bool = Field(default=True, description="是否复用各阶段缓存")
    keep_intermediate: bool = Field(default=False, description="是否保留中间产物文件")
    video_source: str = Field(default="original", description="导出所用视频来源，如原始或字幕擦除后")
    audio_source: str = Field(default="both", description="音频来源选择（人声/背景/两者）")
    subtitle_source: str = Field(default="asr", description="字幕来源，如转写（asr）或字幕识别（OCR）")
    # Video perception (visual-context node / OCR classify post-step)
    vision_backend: Literal["auto", "mlx", "ollama"] = Field(default="auto", description="画面感知推理后端")
    vision_frames_per_unit: int = Field(default=4, ge=1, le=8, description="画面感知每单元抽帧数")
    vision_lang: Literal["zh", "en"] = Field(default="zh", description="画面感知输出语言")
    # Commentary pipeline (asr-commentary template)
    commentary_style: Literal["plot_recap", "frame_riff"] = Field(
        default="plot_recap", description="解说类型：plot_recap=剧情解说；frame_riff=逐帧吐槽（暂未实现）"
    )
    commentary_genre: str = Field(default="剧情", description="解说影视类型（剧情/悬疑/动作等），影响叙事重点")
    commentary_original_sound_ratio: int = Field(
        default=20, ge=0, le=90, description="保留原声(OST=1)的目标时长占比（%）"
    )
    commentary_backend: str = Field(default="qwen3tts", description="解说配音 TTS 后端")
    commentary_narration_language: str = Field(default="zh", description="解说配音语言")
    commentary_original_gain_db: float = Field(
        default=-15.0, description="OST=0 片段里原声被压低到的增益(dB)"
    )
    ocr_classify_text: bool = Field(
        default=False,
        description="字幕识别后用视觉模型给每条 OCR 事件分类（对白字幕/场景文字/水印/标题），擦除与字幕翻译将跳过非字幕文字。默认关闭",
    )
    erase_qc_enabled: bool = Field(
        default=False,
        description="字幕擦除后用视觉模型抽查原字幕区间是否有残留文字/涂抹痕迹，输出质检报告（纯报告，不阻断管线）。默认关闭",
    )
    erase_qc_max_units: int = Field(default=40, ge=0, description="擦除质检最多抽查的字幕区间数（均匀抽样；0=全部检查）")
    # Subtitle erase (subtitle-erase node)
    erase_backend: Literal["sttn", "lama"] = Field(default="sttn", description="字幕擦除后端：sttn/lama")
    erase_device: Literal["auto", "mps", "cuda", "cpu"] = Field(default="auto", description="字幕擦除计算设备")
    erase_max_load: int = Field(default=50, gt=0, description="字幕擦除时单批最大加载帧数")
    erase_mask_dilate_x: int = Field(default=12, ge=0, description="字幕擦除掩码横向膨胀像素（增大可消除残留，过大易溢出）")
    erase_mask_dilate_y: int = Field(default=8, ge=0, description="字幕擦除掩码纵向膨胀像素（增大可消除残留，过大易溢出）")
    erase_event_lead_frames: int = Field(default=3, ge=0, description="字幕事件提前擦除帧数（处理淡入）")
    erase_event_trail_frames: int = Field(default=8, ge=0, description="字幕事件延后擦除帧数（处理淡出）")
    erase_neighbor_stride: int = Field(default=5, gt=0, description="STTN 时间邻域采样步长")
    erase_reference_length: int = Field(default=10, gt=0, description="STTN 全局参考帧步长")
    # Stage 1
    separation_mode: str = Field(default="auto", description="separation 分离模式，auto 为自动判断")
    separation_quality: str = Field(default="balanced", description="separation 人声/背景分离质量档位")
    music_backend: str = Field(default="demucs", description="背景音乐分离后端")
    dialogue_backend: str = Field(default="cdx23", description="人声/对白分离后端")
    stage1_output_format: str = Field(default="mp3", description="separation 输出音频格式")
    audio_stream_index: int = Field(default=0, ge=0, description="选用的输入音轨索引，从 0 开始")
    # Task A
    asr_model: str = Field(default="paraformer-zh", description="转写所用 ASR 模型")
    asr_backend: Literal["faster-whisper", "funasr"] = Field(default="funasr", description="转写后端：faster-whisper 或 funasr")
    diarizer_backend: Literal["ecapa", "pyannote"] = Field(default="ecapa", description="说话人分离（diarization）后端：ecapa 或 pyannote")
    enable_diarization: bool = Field(default=True, description="是否启用说话人分离")
    generate_srt: bool = Field(default=True, description="是否生成 SRT 字幕文件")
    vad_filter: bool = Field(default=True, description="是否启用语音活动检测（VAD）过滤静音")
    vad_min_silence_duration_ms: int = Field(default=400, gt=0, description="VAD 判定静音的最短时长（毫秒）")
    beam_size: int = Field(default=5, gt=0, description="转写束搜索宽度")
    best_of: int = Field(default=5, gt=0, description="采样时保留的候选数")
    temperature: float = Field(default=0.0, ge=0, description="转写采样温度，0 为确定性解码")
    condition_on_previous_text: bool = Field(default=False, description="是否以前文为条件继续转写")
    transcription_correction: Dict[str, Any] = Field(
        default={
            "enabled": True,
            "preset": "standard",
            "ocr_only_policy": "report_only",
            "llm_arbitration": "off",
        },
        description="转写校正配置（开关、预设、仅 OCR 策略、LLM 仲裁等）",
    )
    # Task B
    existing_registry: Optional[str] = Field(default=None, description="复用的已有说话人登记表（registry）路径")
    top_k: int = Field(default=3, gt=0, description="说话人匹配返回的候选数上限")
    # Task C
    translation_backend: str = Field(default="local-m2m100", description="翻译后端：local-m2m100 或 deepseek")
    translation_glossary: Optional[str] = Field(default=None, description="翻译术语表（glossary）路径")
    translation_batch_size: int = Field(default=4, gt=0, description="翻译批处理大小")
    deepseek_base_url: Optional[str] = Field(default=None, description="deepseek 后端 API 基地址的单任务覆盖；通常留空，使用「常规 → 大模型密钥」中保存的账号级地址")
    deepseek_model: Optional[str] = Field(default=None, description="deepseek 后端使用的模型名")
    condense_mode: str = Field(default="smart", description="译文精简模式，off 为不精简，smart 仅精简超时段落")
    # Task D
    tts_backend: str = Field(default="moss-tts-nano-onnx", description="语音合成（TTS）后端")
    max_segments: Optional[int] = Field(default=None, gt=0, description="最多合成的片段数，留空为不限制")
    dubbing_workers: Optional[int] = Field(default=None, gt=0, description="配音合成并发线程数，留空为自动")
    dubbing_quality_check: Literal["standard", "duration-only"] = Field(default="standard", description="配音质检模式：standard 或仅时长（duration-only）")
    dub_repair_enabled: bool = Field(default=False, description="是否启用配音修复（重合成失败片段）")
    dub_repair_backend: List[str] = Field(default=[], description="配音修复所用的备选 TTS 后端列表")
    dub_repair_max_items: int = Field(default=12, gt=0, description="单次配音修复处理的最大片段数")
    dub_repair_attempts_per_item: int = Field(default=3, gt=0, description="每个片段的配音修复尝试次数")
    dub_repair_include_risk: bool = Field(default=False, description="是否将存在风险的片段一并纳入修复")
    # Task E
    fit_policy: str = Field(default="conservative", description="时间轴重拟合策略，conservative 为保守")
    fit_backend: str = Field(default="atempo", description="时长拟合后端：atempo 或 rubberband")
    mix_profile: str = Field(default="preview", description="混音配置档，如 preview")
    ducking_mode: str = Field(default="static", description="背景闪避（ducking）模式：static 或动态")
    background_gain_db: float = Field(default=-8.0, description="背景音整体增益（dB）")
    window_ducking_db: float = Field(default=-3.0, description="人声窗口内背景闪避量（dB）")
    max_compress_ratio: float = Field(default=1.45, gt=0, description="时长压缩的最大倍率")
    output_sample_rate: int = Field(default=24000, gt=0, description="输出音频采样率（Hz）")
    preview_format: str = Field(default="wav", description="预览音频格式")
    # Task G
    export_preview: bool = Field(default=True, description="是否导出预览成片")
    export_dub: bool = Field(default=True, description="是否导出最终配音成片")
    delivery_container: str = Field(default="mp4", description="导出封装容器格式")
    delivery_video_codec: str = Field(default="copy", description="导出视频编码，copy 为直接复用源流")
    delivery_audio_codec: str = Field(default="aac", description="导出音频编码")
    subtitle_mode: str = Field(default="none", description="字幕烧录模式，none 为不烧录")
    subtitle_render_source: str = Field(default="ocr", description="烧录字幕来源，如字幕识别（OCR）")
    subtitle_font: Optional[str] = Field(default=None, description="字幕字体，留空用默认字体")
    subtitle_font_size: int = Field(default=0, description="字幕字号，0 表示自动")
    subtitle_color: str = Field(default="#FFFFFF", description="字幕颜色（十六进制）")
    subtitle_outline_color: str = Field(default="#000000", description="字幕描边颜色（十六进制）")
    subtitle_outline_width: float = Field(default=2.0, description="字幕描边宽度")
    subtitle_position: str = Field(default="bottom", description="字幕位置，如 bottom")
    subtitle_margin_v: int = Field(default=0, description="字幕垂直边距")
    subtitle_bold: bool = Field(default=False, description="字幕是否加粗")
    bilingual_chinese_position: str = Field(default="bottom", description="双语字幕中文位置")
    bilingual_english_position: str = Field(default="top", description="双语字幕英文位置")
    bilingual_export_strategy: str = Field(default="auto_standard_bilingual", description="双语字幕导出策略")
    subtitle_preview_duration_sec: float = Field(default=10.0, description="字幕预览时长（秒）")


class CreateTaskRequest(BaseModel):
    name: str = Field(description="任务名称")
    input_path: str = Field(description="输入视频/音频文件路径")
    source_lang: str = Field(default="zh", description="源语言")
    target_lang: str = Field(default="en", description="目标语言")
    config: TaskConfigInput = Field(default=TaskConfigInput(), description="任务运行配置")
    output_root: Optional[str] = Field(default=None, description="产物输出根目录，留空用默认")
    save_as_preset: bool = Field(default=False, description="是否将本次配置另存为预设")
    preset_name: Optional[str] = Field(default=None, description="另存预设时使用的名称")


class RerunTaskRequest(BaseModel):
    from_stage: str = Field(default="separation", description="重跑的起始阶段")


class ConfigPresetRead(BaseModel):
    id: int = Field(description="预设标识")
    name: str = Field(description="预设名称")
    description: Optional[str] = Field(default=None, description="预设说明")
    source_lang: str = Field(description="源语言")
    target_lang: str = Field(description="目标语言")
    config: Dict[str, Any] = Field(description="预设保存的配置内容")
    created_at: datetime = Field(description="预设创建时间")
    updated_at: datetime = Field(description="预设最后更新时间")


class CreatePresetRequest(BaseModel):
    name: str = Field(description="预设名称")
    description: Optional[str] = Field(default=None, description="预设说明")
    source_lang: str = Field(default="zh", description="源语言")
    target_lang: str = Field(default="en", description="目标语言")
    config: Dict[str, Any] = Field(description="要保存的配置内容")


class SystemInfo(BaseModel):
    python_version: str = Field(description="Python 版本")
    device: str = Field(description="当前计算设备")
    cache_dir: str = Field(description="缓存目录路径")
    cache_size_bytes: int = Field(description="缓存目录占用空间（字节）")
    pipeline_output_root: str = Field(description="流水线产物输出根目录")
    models: List[Dict[str, Any]] = Field(default=[], description="已缓存模型信息列表")


class MediaProbeResult(BaseModel):
    path: str = Field(description="被探测的媒体文件路径")
    duration_sec: float = Field(description="媒体时长（秒）")
    has_video: bool = Field(description="是否含视频流")
    has_audio: bool = Field(description="是否含音频流")
    width: Optional[int] = Field(default=None, description="视频宽度（像素）")
    height: Optional[int] = Field(default=None, description="视频高度（像素）")
    sample_rate: Optional[int] = Field(default=None, description="音频采样率（Hz）")
    format_name: Optional[str] = Field(default=None, description="容器格式名")
