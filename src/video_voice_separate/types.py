from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

Mode = Literal["music", "dialogue", "auto"]
Route = Literal["music", "dialogue"]
OutputFormat = Literal["wav", "mp3", "flac", "aac", "opus"]
Device = Literal["auto", "cpu", "cuda", "mps"]
Quality = Literal["balanced", "high"]
TranslationBackendName = Literal["local-m2m100", "siliconflow"]
TtsBackendName = Literal["f5tts", "openvoice"]


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
    backend: TtsBackendName = "f5tts"
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
