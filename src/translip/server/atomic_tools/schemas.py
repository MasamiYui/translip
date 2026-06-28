from __future__ import annotations

import re
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


class DetectLanguageToolRequest(BaseModel):
    file_id: str = Field(description="待识别语种的音/视频文件 ID")
    model: Literal["tiny", "base", "small", "medium", "large-v3"] = Field(
        default="medium", description="faster-whisper 模型；越大越准但越慢、占内存越多"
    )
    windows: int = Field(default=3, ge=1, le=10, description="采样的 30 秒窗口数；越多对长视频越稳但越慢")


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


class DubRenderToolRequest(BaseModel):
    translation_file_id: str = Field(description="翻译结果 JSON（含每段 segment_id/speaker_id/时间轴/target_text），来自「文本翻译」工具")
    background_file_id: str = Field(description="背景/伴奏音轨文件 ID，来自「人声/背景分离」工具")
    reference_audio_file_id: str | None = Field(
        default=None, description="参考音色音频文件 ID；moss-tts-nano-onnx / voxcpm2 后端必填（音色克隆）"
    )
    video_file_id: str | None = Field(
        default=None, description="可选：目标视频文件 ID，提供则把配音混音合并回视频输出成品 MP4"
    )
    backend: str = Field(default="qwen3tts", description="TTS 后端")
    target_lang: str = Field(default="auto", description="目标语言；auto 表示沿用翻译 JSON 中记录的目标语言")
    ducking_mode: Literal["static", "sidechain"] = Field(default="static", description="背景压混方式")
    background_gain_db: float = Field(default=-8.0, description="背景音轨增益 (dB)")

    @model_validator(mode="after")
    def validate_backend(self) -> "DubRenderToolRequest":
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


class SubtitleBurnToolRequest(BaseModel):
    video_file_id: str = Field(description="待烧录字幕的视频文件 ID")
    subtitle_file_id: str = Field(description="字幕文件 ID（.srt 或 .ass）")
    lang: Literal["auto", "cjk", "latin"] = Field(
        default="auto", description="字体选择：auto 自动判断中日韩/拉丁，cjk 强制中日韩字体，latin 强制拉丁字体"
    )
    position: Literal["bottom", "top"] = Field(default="bottom", description="字幕位置")
    quality: Literal["balanced", "high"] = Field(
        default="balanced", description="编码质量：balanced=较快，high=更清晰但更慢"
    )


class SubtitleEmbedToolRequest(BaseModel):
    video_file_id: str = Field(description="目标视频文件 ID")
    subtitle_file_id: str = Field(description="字幕文件 ID（.srt 或 .ass）")
    container: Literal["mp4", "mkv"] = Field(default="mp4", description="输出容器：mp4 用 mov_text，mkv 用 srt 软字幕")
    subtitle_language: str = Field(default="und", description="字幕语言标签（ISO 639，如 zh/en/und）")


SubtitleErasePreset = Literal["balanced", "quality"]


class SubtitleDetectToolRequest(BaseModel):
    file_id: str
    language: Literal["ch", "en", "ch_tra", "japan", "korean"] = "ch"
    sample_interval: float = 0.4
    preview_frames: int = 3
    position_mode: Literal["auto", "bottom", "middle", "top"] = "auto"
    extraction_mode: Literal["conservative", "balanced", "variety_recall"] = "conservative"
    # Render the legacy red-box annotated preview JPGs alongside detection.json.
    # The interactive overlay UI does not need them, but lab snapshots / CLI
    # consumers still rely on them. Set to False to skip and save ~30KB/frame.
    preview_with_annotations: bool = True
    # Number of clean keyframes (without burned-in boxes) emitted as kf_NN.jpg,
    # used by the interactive preview overlay in the UI. Set to 0 to opt out
    # entirely (the preview panel will then fall back to artifact list only).
    preview_keyframe_density: int = 3


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


M3u8Mode = Literal["copy", "transcode"]
M3u8Container = Literal["mp4", "mkv"]
X264Preset = Literal[
    "ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"
]


class M3u8ToMp4ToolRequest(BaseModel):
    """Convert an HLS (.m3u8) playlist — remote URL or uploaded file — into one MP4/MKV.

    Exactly one input source is required: either ``url`` (an http/https playlist,
    VOD or live) or ``playlist_file_id`` (an uploaded local ``.m3u8`` whose segment
    URIs must themselves be reachable). Everything else is optional tuning; the
    network knobs (``user_agent`` / ``referer`` / ``headers``) cover anti-hotlink
    streams, ``duration_limit_sec`` bounds otherwise-endless live captures, and
    ``mode=transcode`` re-encodes when a stream's codecs aren't MP4-friendly.
    """

    url: str | None = Field(
        default=None, description="HLS 播放列表 URL（http/https），点播或直播均可"
    )
    playlist_file_id: str | None = Field(
        default=None,
        description="上传的本地 .m3u8 文件 ID（其分片地址需为可访问的完整 URL）",
    )
    mode: M3u8Mode = Field(
        default="copy",
        description="copy=快速转封装（不重新编码，最快且无损）；transcode=重新编码为 H.264/AAC（兼容优先）",
    )
    output_format: M3u8Container = Field(default="mp4", description="输出容器：mp4 或 mkv")
    output_name: str | None = Field(
        default=None, description="输出文件名（不含扩展名），留空则自动命名"
    )
    duration_limit_sec: float | None = Field(
        default=None, gt=0, description="仅抓取前 N 秒；直播流必填，否则会持续录制直至停止"
    )
    start_sec: float | None = Field(
        default=None, ge=0, description="起始偏移（秒），用于裁剪片段"
    )
    user_agent: str | None = Field(default=None, description="自定义 User-Agent 请求头")
    referer: str | None = Field(default=None, description="Referer 请求头，用于绕过防盗链")
    headers: str | None = Field(
        default=None, description="附加 HTTP 请求头，每行一个 'Key: Value'"
    )
    crf: int = Field(
        default=20, ge=0, le=51, description="transcode 模式的 x264 画质（越小越清晰，18–23 常用）"
    )
    preset: X264Preset = Field(default="veryfast", description="transcode 模式的 x264 编码速度")
    audio_bitrate: str = Field(default="192k", description="transcode 模式的音频码率")

    @model_validator(mode="after")
    def validate_source(self) -> "M3u8ToMp4ToolRequest":
        url = (self.url or "").strip()
        has_url = bool(url)
        has_file = bool(self.playlist_file_id)
        if has_url == has_file:
            raise ValueError(
                "Provide exactly one input: an m3u8 URL or an uploaded .m3u8 file."
            )
        if has_url:
            if not url.lower().startswith(("http://", "https://")):
                raise ValueError("URL must start with http:// or https://")
            self.url = url
        else:
            self.url = None
        return self


VideoTrimMode = Literal["fast", "accurate"]
VideoTrimContainer = Literal["mp4", "mkv"]
# Minimum trim window length (seconds). Matches the frontend MIN_GAP so the
# preview slider and direct API callers agree on the smallest legal cut.
VIDEO_TRIM_MIN_WINDOW_SEC = 0.1


class VideoTrimToolRequest(BaseModel):
    """Cut a ``[start, end)`` window out of one video into a new MP4/MKV.

    The window is given as ``start_sec`` plus *exactly one* upper bound —
    ``end_sec`` (an absolute timestamp) or ``duration_sec`` (a length). Supplying
    neither trims from ``start_sec`` to the end of the file; supplying both is
    rejected. ``mode=fast`` stream-copies (lossless, near-instant, but the start
    snaps to the nearest keyframe), while ``mode=accurate`` re-encodes for a
    frame-exact cut (``quality`` only matters there).
    """

    file_id: str = Field(description="待裁剪的视频文件 ID")
    start_sec: float = Field(default=0.0, ge=0, description="起始时间（秒）")
    end_sec: float | None = Field(
        default=None,
        ge=0,
        description="结束时间（秒，不含）；与 duration_sec 二选一，留空则裁到片尾",
    )
    duration_sec: float | None = Field(
        default=None,
        ge=VIDEO_TRIM_MIN_WINDOW_SEC,
        description="截取时长（秒）；与 end_sec 二选一",
    )
    mode: VideoTrimMode = Field(
        default="accurate",
        description="fast=流复制（极快无损，起点对齐到最近关键帧）；accurate=重新编码（精确到帧）",
    )
    output_format: VideoTrimContainer = Field(default="mp4", description="输出容器：mp4 或 mkv")
    quality: Literal["balanced", "high"] = Field(
        default="balanced",
        description="accurate 模式的编码画质：balanced=较快，high=更清晰但更慢（fast 模式忽略）",
    )

    @model_validator(mode="after")
    def validate_window(self) -> "VideoTrimToolRequest":
        if self.end_sec is not None and self.duration_sec is not None:
            raise ValueError("Provide either end_sec or duration_sec, not both.")
        # Enforce a minimum window in both end_sec / duration_sec branches so
        # ffmpeg never receives a degenerate request that would silently produce
        # a 0-frame clip.
        if self.end_sec is not None and (
            self.end_sec - self.start_sec
        ) < VIDEO_TRIM_MIN_WINDOW_SEC:
            raise ValueError(
                "end_sec must be at least "
                f"{VIDEO_TRIM_MIN_WINDOW_SEC}s greater than start_sec."
            )
        return self


WatermarkPosition = Literal[
    "top-left", "top-right", "bottom-left", "bottom-right", "center"
]

# An ffmpeg color is a name (``white``) or ``#RRGGBB``/``#RRGGBBAA`` hex, each
# optionally suffixed ``@<opacity>``. We validate the *shape* (not the full name
# table) so values that would break the filtergraph or smuggle in extra options
# — anything with ``:``, ``,``, quotes, spaces, brackets — are rejected before
# they reach the drawtext/overlay filter string.
_FFMPEG_COLOR_RE = re.compile(
    r"^(#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?|[A-Za-z]+)(?:@\d*\.?\d+)?$"
)


def _validate_ffmpeg_color(value: str, field: str) -> str:
    if not _FFMPEG_COLOR_RE.match(value or ""):
        raise ValueError(
            f"{field} must be an ffmpeg color name or #hex, optionally with @opacity "
            f"(e.g. white, #ffcc00, black@0.6); got {value!r}"
        )
    return value


class WatermarkToolRequest(BaseModel):
    """Overlay an image or text watermark onto a video and re-encode it.

    Two modes share the same position / opacity controls:

    * ``image``: requires ``image_file_id`` (PNG/JPG, alpha respected). ``scale``
      sizes the watermark relative to the video width (0.15 = 15% of width).
    * ``text``:  requires ``text``. ``font_size`` is in pixels; ``font_color`` /
      ``stroke_color`` accept ffmpeg color spellings (e.g. ``white``, ``#ffcc00``,
      ``black@0.6``).
    """

    video_file_id: str = Field(description="待加水印的视频文件 ID")
    image_file_id: str | None = Field(
        default=None, description="图片水印的图片文件 ID（mode=image 时必填，建议 PNG）"
    )
    mode: Literal["image", "text"] = Field(default="image", description="水印类型")
    position: WatermarkPosition = Field(
        default="bottom-right", description="水印位置：四角或居中"
    )
    margin: int = Field(default=24, ge=0, description="距离边缘的像素")
    opacity: float = Field(default=0.8, ge=0.0, le=1.0, description="透明度 0.0–1.0")
    quality: Literal["balanced", "high"] = Field(
        default="balanced", description="编码质量：balanced=较快，high=更清晰但更慢"
    )

    # image-mode only
    scale: float = Field(
        default=0.15, gt=0.0, le=1.0, description="图片水印宽度相对视频宽度的比例 (mode=image)"
    )

    # text-mode only
    text: str | None = Field(default=None, description="文字水印内容 (mode=text 必填)")
    font_size: int = Field(default=36, gt=0, description="字号 (mode=text)")
    font_color: str = Field(default="white", description="文字颜色，如 white / #ffcc00")
    stroke_color: str = Field(default="black@0.6", description="描边颜色，可带透明度")
    stroke_width: int = Field(default=2, ge=0, description="描边宽度像素")

    @model_validator(mode="after")
    def validate_mode_inputs(self) -> "WatermarkToolRequest":
        if self.mode == "image" and not self.image_file_id:
            raise ValueError("mode=image requires image_file_id")
        if self.mode == "text" and not (self.text or "").strip():
            raise ValueError("mode=text requires non-empty text")
        if self.mode == "text":
            _validate_ffmpeg_color(self.font_color, "font_color")
            _validate_ffmpeg_color(self.stroke_color, "stroke_color")
        return self


CommentaryStyle = Literal[
    "plot_recap", "plot_tease", "analysis", "roast", "reaction", "tutorial", "frame_riff"
]
CommentaryTonePreset = Literal[
    "objective", "passionate", "humorous", "sarcastic", "suspenseful", "chill", "dramatic", "professional"
]
CommentaryPacingPreset = Literal["sparse", "balanced", "dense"]
CommentaryPerspective = Literal[
    "third_person", "first_person_narrator", "first_person_protagonist", "second_person", "god_view"
]
CommentaryAudience = Literal[
    "generic", "bilibili", "douyin", "xiaohongshu", "youtube_long", "wechat_video", "professional_b2b"
]


class CommentaryScriptToolRequest(BaseModel):
    """Generate an OST-interleaved movie-recap narration script (commentary.json).

    Consumes the transcript ``segments.{lang}.json`` (fact source, from the
    transcription tool) and, optionally, ``visual_context.json`` (scene cues, from
    the video-analyze scene-context task). Runs a 3-stage LLM chain (understand →
    plan clips → write narration) and emits a reviewable script where each item is
    either narration-over-picture (``ost=0``) or original-sound passthrough
    (``ost=1``); ``original_sound_ratio`` is the OST=1 target share.
    """

    segments_file_id: str = Field(
        description="转写结果 segments JSON 文件 ID（来自「语音转文字」，提供带时间戳的台词，作为事实源）"
    )
    visual_context_file_id: str | None = Field(
        default=None,
        description="可选：视频内容分析 visual_context.json 文件 ID（来自「视频内容分析」scene-context），提供则解说更贴合画面",
    )
    commentary_style: CommentaryStyle = Field(
        default="plot_recap",
        description="解说模式：plot_recap=剧情解说；plot_tease=悬念预告；analysis=影视解读；roast=吐槽锐评；reaction=实时反应；tutorial=教学科普；frame_riff=逐帧吐槽（预留）",
    )
    drama_genre: str = Field(
        default="剧情", description="影视类型（剧情/悬疑/动作/喜剧/科幻/历史/恐怖等），影响叙事重点"
    )
    narration_language: str = Field(default="zh", description="解说台词语言（如 zh/en）")
    original_sound_ratio: int = Field(
        default=20, ge=0, le=90, description="保留原声(OST=1)的目标时长占比（%）；0=全程解说旁白"
    )
    model: str | None = Field(
        default=None, description="LLM 模型名；留空用 DEEPSEEK_MODEL 默认（deepseek-v4-pro）"
    )
    # --- Phase-1 style customization ---
    tone_preset: CommentaryTonePreset = Field(
        default="objective",
        description="语气人格：objective/passionate/humorous/sarcastic/suspenseful/chill/dramatic/professional",
    )
    pacing_preset: CommentaryPacingPreset = Field(
        default="balanced", description="节奏密度：sparse 克制 / balanced 标准 / dense 密集"
    )
    perspective: CommentaryPerspective = Field(
        default="third_person",
        description="叙事人称：third_person/first_person_narrator/first_person_protagonist/second_person/god_view",
    )
    audience: CommentaryAudience = Field(
        default="generic",
        description="受众/平台：generic/bilibili/douyin/xiaohongshu/youtube_long/wechat_video/professional_b2b",
    )
    style_intensity: float = Field(
        default=0.6, ge=0.0, le=1.0, description="风格强度（0=轻度，1=强烈）"
    )


class CommentaryRenderToolRequest(BaseModel):
    """Assemble a reviewed ``commentary.json`` + the source video into a recap MP4.

    OST=0 items are voiced with the chosen TTS backend and laid over the original
    audio attenuated by ``original_gain_db`` (ducking); OST=1 items keep the
    original audio. The narration language defaults to the one recorded in
    ``commentary.json`` and can be overridden here.
    """

    commentary_file_id: str = Field(
        description="解说文案 commentary.json 文件 ID（来自「解说文案」工具，可人工审阅修改后再渲染）"
    )
    video_file_id: str = Field(description="源视频文件 ID（被解说的原片）")
    reference_audio_file_id: str | None = Field(
        default=None,
        description="参考音色音频文件 ID（上传自己的解说员录音做克隆）；提供时优先于 narrator_voice",
    )
    narrator_voice: str | None = Field(
        default=None,
        description="内置解说音色 id（如 narrator-male-calm）/ 'source'（借用源片音色）/ 留空用默认内置音色；上传 reference_audio_file 时以上传为准",
    )
    backend: str = Field(default="qwen3tts", description="解说配音 TTS 后端")
    narration_language: str | None = Field(
        default=None, description="解说配音语言；留空则沿用 commentary.json 中记录的语言"
    )
    original_gain_db: float = Field(
        default=-15.0,
        description="OST=0 片段里原声被压低到的增益(dB)，越低原声越弱（默认 -15）",
    )

    @model_validator(mode="after")
    def validate_backend(self) -> "CommentaryRenderToolRequest":
        if self.backend not in SUPPORTED_DUBBING_BACKENDS:
            raise ValueError(
                f"Unsupported TTS backend: {self.backend}. "
                f"Choose one of: {', '.join(SUPPORTED_DUBBING_BACKENDS)}"
            )
        # No reference upload is required anymore: a built-in narrator voice (or
        # "source") always resolves to a reference clip for clone-only backends.
        return self
