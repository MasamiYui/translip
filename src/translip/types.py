from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, TypedDict, cast

Mode = Literal["music", "dialogue", "auto"]
Route = Literal["music", "dialogue"]
OutputFormat = Literal["wav", "mp3", "flac", "aac", "opus"]
Device = Literal["auto", "cpu", "cuda", "mps"]
Quality = Literal["balanced", "high"]
TranslationBackendName = Literal["local-m2m100", "siliconflow"]
TtsBackendName = Literal["qwen3tts"]
CondenseMode = Literal["off", "smart", "aggressive"]
FitPolicy = Literal["conservative", "high_quality"]
FitBackendName = Literal["atempo", "rubberband"]
MixProfileName = Literal["preview", "enhanced"]
DuckingModeName = Literal["static", "sidechain"]
PreviewFormat = Literal["wav", "mp3"]
PipelineStageName = Literal["stage1", "task-a", "task-b", "task-c", "task-d", "task-e", "task-g"]
PipelineStageStatus = Literal["pending", "running", "succeeded", "cached", "failed", "skipped"]
WorkflowTemplateName = Literal["asr-dub-basic", "asr-dub+ocr-subs", "asr-dub+ocr-subs+erase"]
WorkflowNodeName = Literal[
    "stage1",
    "ocr-detect",
    "task-a",
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
DeliveryAudioSource = Literal["preview_mix", "dub_voice", "both", "original"]
DeliverySubtitleSource = Literal["none", "asr", "ocr", "both"]
DeliveryContainer = Literal["mp4"]
DeliveryVideoCodec = Literal["copy", "libx264"]
DeliveryAudioCodec = Literal["aac"]
DeliveryEndPolicy = Literal["trim_audio_to_video", "keep_longest"]
SubtitleCompositionMode = Literal["none", "chinese_only", "english_only", "bilingual"]
SubtitleSourceType = Literal["ocr", "asr"]
SubtitlePosition = Literal["top", "bottom"]


class DeliveryPolicy(TypedDict):
    video_source: DeliveryVideoSource
    audio_source: DeliveryAudioSource
    subtitle_source: DeliverySubtitleSource


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


@dataclass(slots=True)
class SeparationRequest:
    input_path: Path | str
    mode: Mode = "auto"
    output_dir: Path | str = Path("output")
    output_format: OutputFormat = "wav"
    quality: Quality = "balanced"
    music_model: str | None = None
    sample_rate: int | None = None
    bitrate: str | None = None
    enhance_voice: bool = False
    device: Device = "auto"
    keep_intermediate: bool = False
    backend_music: str = "demucs"
    backend_dialogue: str = "cdx23"
    audio_stream_index: int = 0

    def normalized(self) -> "SeparationRequest":
        return SeparationRequest(
            input_path=Path(self.input_path).expanduser().resolve(),
            mode=self.mode,
            output_dir=Path(self.output_dir).expanduser().resolve(),
            output_format=self.output_format,
            quality=self.quality,
            music_model=self.music_model,
            sample_rate=self.sample_rate,
            bitrate=self.bitrate,
            enhance_voice=self.enhance_voice,
            device=self.device,
            keep_intermediate=self.keep_intermediate,
            backend_music=self.backend_music,
            backend_dialogue=self.backend_dialogue,
            audio_stream_index=self.audio_stream_index,
        )


@dataclass(slots=True)
class RouteDecision:
    route: Route
    reason: str
    metrics: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class MusicSeparationOutput:
    voice_path: Path
    background_path: Path
    backend_name: str
    intermediate_paths: dict[str, Path] = field(default_factory=dict)


@dataclass(slots=True)
class DialogueSeparationOutput:
    dialog_path: Path
    background_path: Path
    backend_name: str
    intermediate_paths: dict[str, Path] = field(default_factory=dict)


@dataclass(slots=True)
class SeparationArtifacts:
    bundle_dir: Path
    voice_path: Path
    background_path: Path
    manifest_path: Path
    intermediate_paths: dict[str, Path] = field(default_factory=dict)


@dataclass(slots=True)
class SeparationResult:
    request: SeparationRequest
    media_info: MediaInfo
    route: RouteDecision
    artifacts: SeparationArtifacts
    manifest: dict[str, Any]
    work_dir: Path


@dataclass(slots=True)
class TranscriptionRequest:
    input_path: Path | str
    output_dir: Path | str = Path("output")
    language: str = "zh"
    asr_model: str = "small"
    device: Device = "auto"
    audio_stream_index: int = 0
    keep_intermediate: bool = False
    write_srt: bool = True

    def normalized(self) -> "TranscriptionRequest":
        return TranscriptionRequest(
            input_path=Path(self.input_path).expanduser().resolve(),
            output_dir=Path(self.output_dir).expanduser().resolve(),
            language=self.language,
            asr_model=self.asr_model,
            device=self.device,
            audio_stream_index=self.audio_stream_index,
            keep_intermediate=self.keep_intermediate,
            write_srt=self.write_srt,
        )


@dataclass(slots=True)
class TranscriptionSegment:
    segment_id: str
    start: float
    end: float
    text: str
    speaker_label: str
    language: str
    duration: float


@dataclass(slots=True)
class TranscriptionArtifacts:
    bundle_dir: Path
    segments_json_path: Path
    manifest_path: Path
    srt_path: Path | None = None
    intermediate_paths: dict[str, Path] = field(default_factory=dict)


@dataclass(slots=True)
class TranscriptionResult:
    request: TranscriptionRequest
    media_info: MediaInfo
    artifacts: TranscriptionArtifacts
    segments: list[TranscriptionSegment]
    manifest: dict[str, Any]
    work_dir: Path


@dataclass(slots=True)
class SpeakerRegistryRequest:
    segments_path: Path | str
    audio_path: Path | str
    output_dir: Path | str = Path("output")
    registry_path: Path | str | None = None
    device: Device = "auto"
    top_k: int = 3
    update_registry: bool = False
    keep_intermediate: bool = False

    def normalized(self) -> "SpeakerRegistryRequest":
        return SpeakerRegistryRequest(
            segments_path=Path(self.segments_path).expanduser().resolve(),
            audio_path=Path(self.audio_path).expanduser().resolve(),
            output_dir=Path(self.output_dir).expanduser().resolve(),
            registry_path=(
                Path(self.registry_path).expanduser().resolve()
                if self.registry_path is not None
                else None
            ),
            device=self.device,
            top_k=self.top_k,
            update_registry=self.update_registry,
            keep_intermediate=self.keep_intermediate,
        )


@dataclass(slots=True)
class SpeakerRegistryArtifacts:
    bundle_dir: Path
    profiles_path: Path
    matches_path: Path
    registry_snapshot_path: Path
    manifest_path: Path
    intermediate_paths: dict[str, Path] = field(default_factory=dict)


@dataclass(slots=True)
class SpeakerRegistryResult:
    request: SpeakerRegistryRequest
    media_info: MediaInfo
    artifacts: SpeakerRegistryArtifacts
    manifest: dict[str, Any]
    work_dir: Path


@dataclass(slots=True)
class TranslationRequest:
    segments_path: Path | str
    profiles_path: Path | str
    output_dir: Path | str = Path("output")
    source_lang: str = "zh"
    target_lang: str = "en"
    backend: TranslationBackendName = "local-m2m100"
    device: Device = "auto"
    glossary_path: Path | str | None = None
    batch_size: int = 4
    local_model: str = "facebook/m2m100_418M"
    api_model: str | None = None
    api_base_url: str | None = None
    condense_mode: CondenseMode = "off"

    def normalized(self) -> "TranslationRequest":
        return TranslationRequest(
            segments_path=Path(self.segments_path).expanduser().resolve(),
            profiles_path=Path(self.profiles_path).expanduser().resolve(),
            output_dir=Path(self.output_dir).expanduser().resolve(),
            source_lang=self.source_lang,
            target_lang=self.target_lang,
            backend=self.backend,
            device=self.device,
            glossary_path=(
                Path(self.glossary_path).expanduser().resolve()
                if self.glossary_path is not None
                else None
            ),
            batch_size=self.batch_size,
            local_model=self.local_model,
            api_model=self.api_model,
            api_base_url=self.api_base_url,
            condense_mode=self.condense_mode,
        )


@dataclass(slots=True)
class TranslationArtifacts:
    bundle_dir: Path
    translation_json_path: Path
    editable_json_path: Path
    srt_path: Path
    manifest_path: Path


@dataclass(slots=True)
class TranslationResult:
    request: TranslationRequest
    artifacts: TranslationArtifacts
    manifest: dict[str, Any]


@dataclass(slots=True)
class DubbingRequest:
    translation_path: Path | str
    profiles_path: Path | str
    output_dir: Path | str = Path("output")
    speaker_id: str = ""
    backend: TtsBackendName = "qwen3tts"
    device: Device = "auto"
    reference_clip_path: Path | str | None = None
    segment_ids: list[str] | None = None
    max_segments: int | None = None
    keep_intermediate: bool = False
    backread_model: str = "tiny"

    def normalized(self) -> "DubbingRequest":
        return DubbingRequest(
            translation_path=Path(self.translation_path).expanduser().resolve(),
            profiles_path=Path(self.profiles_path).expanduser().resolve(),
            output_dir=Path(self.output_dir).expanduser().resolve(),
            speaker_id=self.speaker_id,
            backend=self.backend,
            device=self.device,
            reference_clip_path=(
                Path(self.reference_clip_path).expanduser().resolve()
                if self.reference_clip_path is not None
                else None
            ),
            segment_ids=list(self.segment_ids) if self.segment_ids else None,
            max_segments=self.max_segments,
            keep_intermediate=self.keep_intermediate,
            backread_model=self.backread_model,
        )


@dataclass(slots=True)
class DubbingArtifacts:
    bundle_dir: Path
    segments_dir: Path
    report_path: Path
    manifest_path: Path
    demo_audio_path: Path | None = None
    intermediate_paths: dict[str, Path] = field(default_factory=dict)


@dataclass(slots=True)
class DubbingResult:
    request: DubbingRequest
    artifacts: DubbingArtifacts
    manifest: dict[str, Any]
    work_dir: Path


@dataclass(slots=True)
class RenderDubRequest:
    background_path: Path | str
    segments_path: Path | str
    translation_path: Path | str
    task_d_report_paths: list[Path | str]
    output_dir: Path | str = Path("output")
    target_lang: str = "en"
    fit_policy: FitPolicy = "conservative"
    fit_backend: FitBackendName = "atempo"
    mix_profile: MixProfileName = "preview"
    ducking_mode: DuckingModeName = "static"
    output_sample_rate: int = 24_000
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


@dataclass(slots=True)
class PipelineRequest:
    input_path: Path | str
    output_root: Path | str = Path("output-pipeline")
    config_path: Path | str | None = None
    template_id: WorkflowTemplateName = "asr-dub-basic"
    delivery_policy: DeliveryPolicy = field(
        default_factory=lambda: cast(
            DeliveryPolicy,
            {
                "video_source": "original",
                "audio_source": "both",
                "subtitle_source": "asr",
            },
        )
    )
    ocr_project_root: Path | str | None = None
    erase_project_root: Path | str | None = None
    target_lang: str = "en"
    translation_backend: TranslationBackendName = "local-m2m100"
    tts_backend: TtsBackendName = "qwen3tts"
    device: Device = "auto"
    run_from_stage: PipelineStageName = "stage1"
    run_to_stage: PipelineStageName = "task-g"
    resume: bool = False
    force_stages: list[PipelineStageName] | None = None
    reuse_existing: bool = True
    keep_logs: bool = True
    write_status: bool = True
    status_update_interval_sec: float = 2.0
    glossary_path: Path | str | None = None
    registry_path: Path | str | None = None
    api_model: str | None = None
    api_base_url: str | None = None
    condense_mode: CondenseMode = "off"
    fit_policy: FitPolicy = "conservative"
    fit_backend: FitBackendName = "atempo"
    mix_profile: MixProfileName = "preview"
    ducking_mode: DuckingModeName = "static"
    preview_format: PreviewFormat = "wav"
    output_sample_rate: int = 24_000
    background_gain_db: float = -8.0
    window_ducking_db: float = -3.0
    max_compress_ratio: float = 1.45
    speaker_limit: int = 0
    segments_per_speaker: int = 0
    separation_mode: Mode = "dialogue"
    separation_quality: Quality = "balanced"
    stage1_output_format: OutputFormat = "mp3"
    transcription_language: str = "zh"
    asr_model: str = "small"
    audio_stream_index: int = 0
    top_k: int = 3
    update_registry: bool = True
    subtitle_mode: SubtitleCompositionMode = "none"
    subtitle_source: SubtitleSourceType = "ocr"
    subtitle_style: SubtitleStyle | None = None
    bilingual_chinese_position: SubtitlePosition = "bottom"
    bilingual_english_position: SubtitlePosition = "top"

    def normalized(self) -> "PipelineRequest":
        return PipelineRequest(
            input_path=Path(self.input_path).expanduser().resolve(),
            output_root=Path(self.output_root).expanduser().resolve(),
            config_path=(
                Path(self.config_path).expanduser().resolve()
                if self.config_path is not None
                else None
            ),
            template_id=self.template_id,
            delivery_policy=cast(DeliveryPolicy, dict(self.delivery_policy)),
            ocr_project_root=(
                Path(self.ocr_project_root).expanduser().resolve()
                if self.ocr_project_root is not None
                else None
            ),
            erase_project_root=(
                Path(self.erase_project_root).expanduser().resolve()
                if self.erase_project_root is not None
                else None
            ),
            target_lang=self.target_lang,
            translation_backend=self.translation_backend,
            tts_backend=self.tts_backend,
            device=self.device,
            run_from_stage=self.run_from_stage,
            run_to_stage=self.run_to_stage,
            resume=self.resume,
            force_stages=list(self.force_stages) if self.force_stages else None,
            reuse_existing=self.reuse_existing,
            keep_logs=self.keep_logs,
            write_status=self.write_status,
            status_update_interval_sec=self.status_update_interval_sec,
            glossary_path=(
                Path(self.glossary_path).expanduser().resolve()
                if self.glossary_path is not None
                else None
            ),
            registry_path=(
                Path(self.registry_path).expanduser().resolve()
                if self.registry_path is not None
                else None
            ),
            api_model=self.api_model,
            api_base_url=self.api_base_url,
            condense_mode=self.condense_mode,
            fit_policy=self.fit_policy,
            fit_backend=self.fit_backend,
            mix_profile=self.mix_profile,
            ducking_mode=self.ducking_mode,
            preview_format=self.preview_format,
            output_sample_rate=self.output_sample_rate,
            background_gain_db=self.background_gain_db,
            window_ducking_db=self.window_ducking_db,
            max_compress_ratio=self.max_compress_ratio,
            speaker_limit=self.speaker_limit,
            segments_per_speaker=self.segments_per_speaker,
            separation_mode=self.separation_mode,
            separation_quality=self.separation_quality,
            stage1_output_format=self.stage1_output_format,
            transcription_language=self.transcription_language,
            asr_model=self.asr_model,
            audio_stream_index=self.audio_stream_index,
            top_k=self.top_k,
            update_registry=self.update_registry,
            subtitle_mode=self.subtitle_mode,
            subtitle_source=self.subtitle_source,
            subtitle_style=self.subtitle_style,
            bilingual_chinese_position=self.bilingual_chinese_position,
            bilingual_english_position=self.bilingual_english_position,
        )


@dataclass(slots=True)
class PipelineResult:
    request: PipelineRequest
    output_root: Path
    manifest_path: Path
    report_path: Path
    status_path: Path
    request_path: Path
    manifest: dict[str, Any]
    report: dict[str, Any]


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
    subtitle_source: SubtitleSourceType = "ocr"
    subtitle_style: SubtitleStyle | None = None
    bilingual_chinese_position: SubtitlePosition = "bottom"
    bilingual_english_position: SubtitlePosition = "top"

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
            subtitle_source=self.subtitle_source,
            subtitle_style=self.subtitle_style,
            bilingual_chinese_position=self.bilingual_chinese_position,
            bilingual_english_position=self.bilingual_english_position,
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
