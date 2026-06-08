from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from .common import (
    AsrBackendName,
    BilingualExportStrategy,
    CondenseMode,
    DeliveryPolicy,
    Device,
    DiarizerBackendName,
    DubbingQualityCheckMode,
    DuckingModeName,
    FitBackendName,
    FitPolicy,
    MixProfileName,
    Mode,
    OutputFormat,
    PipelineStageName,
    PreviewFormat,
    Quality,
    SubtitleCompositionMode,
    SubtitlePosition,
    SubtitleSourceType,
    SubtitleStyle,
    TranscriptionCorrectionConfig,
    TranslationBackendName,
    TtsBackendName,
    WorkflowTemplateName,
    normalize_dubbing_quality_check_mode,
)


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
    # OCR hard-subtitle detection (ocr-detect node) tunables.
    ocr_sample_interval: float = 0.25
    ocr_position_mode: str = "auto"  # auto | bottom | middle | top
    ocr_extraction_mode: str = "conservative"  # conservative | balanced | variety_recall
    target_lang: str = "en"
    translation_backend: TranslationBackendName = "local-m2m100"
    translation_batch_size: int = 4
    tts_backend: TtsBackendName = "moss-tts-nano-onnx"
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
    condense_mode: CondenseMode = "smart"
    fit_policy: FitPolicy = "conservative"
    fit_backend: FitBackendName = "atempo"
    mix_profile: MixProfileName = "preview"
    ducking_mode: DuckingModeName = "static"
    preview_format: PreviewFormat = "wav"
    output_sample_rate: int = 48_000
    background_gain_db: float = -8.0
    window_ducking_db: float = -3.0
    max_compress_ratio: float = 1.45
    dubbing_workers: int | None = None
    dubbing_quality_check: DubbingQualityCheckMode = "standard"
    dub_repair_enabled: bool = False
    dub_repair_backends: list[str] | None = None
    dub_repair_max_items: int = 12
    dub_repair_attempts_per_item: int = 3
    dub_repair_include_risk: bool = False
    speaker_limit: int = 0
    segments_per_speaker: int = 0
    separation_mode: Mode = "dialogue"
    separation_quality: Quality = "balanced"
    stage1_output_format: OutputFormat = "mp3"
    transcription_language: str = "zh"
    asr_model: str = "paraformer-zh"
    asr_backend: AsrBackendName = "funasr"
    diarizer_backend: DiarizerBackendName = "ecapa"
    enable_diarization: bool = True
    generate_srt: bool = True
    vad_filter: bool = True
    vad_min_silence_duration_ms: int = 400
    vad_max_segment_sec: float = 30.0
    expected_speakers: int = 0
    beam_size: int = 5
    best_of: int = 5
    temperature: float = 0.0
    condition_on_previous_text: bool = False
    audio_stream_index: int = 0
    top_k: int = 3
    update_registry: bool = True
    subtitle_mode: SubtitleCompositionMode = "none"
    subtitle_source: SubtitleSourceType = "ocr"
    subtitle_style: SubtitleStyle | None = None
    bilingual_chinese_position: SubtitlePosition = "bottom"
    bilingual_english_position: SubtitlePosition = "top"
    bilingual_export_strategy: BilingualExportStrategy = "auto_standard_bilingual"
    transcription_correction: TranscriptionCorrectionConfig = field(
        default_factory=lambda: cast(
            TranscriptionCorrectionConfig,
            {
                "enabled": True,
                "preset": "standard",
                "ocr_only_policy": "report_only",
                "llm_arbitration": "off",
            },
        )
    )
    # Hard-subtitle erasure (subtitle-erase node) — in-tree inpainting.
    erase_backend: str = "sttn"  # sttn | lama
    erase_device: str = "auto"  # auto | mps | cuda | cpu
    erase_mask_dilate_x: int = 12
    erase_mask_dilate_y: int = 8
    erase_event_lead_frames: int = 3
    erase_event_trail_frames: int = 8
    erase_neighbor_stride: int = 5  # STTN: temporal neighbor window step
    erase_reference_length: int = 10  # STTN: global reference frame stride
    erase_max_load: int = 50  # max frames inpainted per batch
    erase_regions: list[tuple[float, float, float, float]] | None = None

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
            ocr_sample_interval=float(self.ocr_sample_interval),
            ocr_position_mode=self.ocr_position_mode,
            ocr_extraction_mode=self.ocr_extraction_mode,
            target_lang=self.target_lang,
            translation_backend=self.translation_backend,
            translation_batch_size=int(self.translation_batch_size),
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
            dubbing_workers=self.dubbing_workers,
            dubbing_quality_check=normalize_dubbing_quality_check_mode(self.dubbing_quality_check),
            dub_repair_enabled=bool(self.dub_repair_enabled),
            dub_repair_backends=list(self.dub_repair_backends) if self.dub_repair_backends else None,
            dub_repair_max_items=int(self.dub_repair_max_items),
            dub_repair_attempts_per_item=int(self.dub_repair_attempts_per_item),
            dub_repair_include_risk=bool(self.dub_repair_include_risk),
            speaker_limit=self.speaker_limit,
            segments_per_speaker=self.segments_per_speaker,
            separation_mode=self.separation_mode,
            separation_quality=self.separation_quality,
            stage1_output_format=self.stage1_output_format,
            transcription_language=self.transcription_language,
            asr_model=self.asr_model,
            asr_backend=self.asr_backend,
            diarizer_backend=self.diarizer_backend,
            enable_diarization=bool(self.enable_diarization),
            generate_srt=bool(self.generate_srt),
            vad_filter=bool(self.vad_filter),
            vad_min_silence_duration_ms=int(self.vad_min_silence_duration_ms),
            vad_max_segment_sec=float(self.vad_max_segment_sec),
            expected_speakers=int(self.expected_speakers),
            beam_size=int(self.beam_size),
            best_of=int(self.best_of),
            temperature=float(self.temperature),
            condition_on_previous_text=bool(self.condition_on_previous_text),
            audio_stream_index=self.audio_stream_index,
            top_k=self.top_k,
            update_registry=self.update_registry,
            subtitle_mode=self.subtitle_mode,
            subtitle_source=self.subtitle_source,
            subtitle_style=self.subtitle_style,
            bilingual_chinese_position=self.bilingual_chinese_position,
            bilingual_english_position=self.bilingual_english_position,
            bilingual_export_strategy=self.bilingual_export_strategy,
            transcription_correction=cast(TranscriptionCorrectionConfig, dict(self.transcription_correction)),
            erase_backend=self.erase_backend,
            erase_device=self.erase_device,
            erase_mask_dilate_x=int(self.erase_mask_dilate_x),
            erase_mask_dilate_y=int(self.erase_mask_dilate_y),
            erase_event_lead_frames=int(self.erase_event_lead_frames),
            erase_event_trail_frames=int(self.erase_event_trail_frames),
            erase_neighbor_stride=int(self.erase_neighbor_stride),
            erase_reference_length=int(self.erase_reference_length),
            erase_max_load=int(self.erase_max_load),
            erase_regions=list(self.erase_regions) if self.erase_regions else None,
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


__all__ = [
    "PipelineRequest",
    "PipelineResult",
]
