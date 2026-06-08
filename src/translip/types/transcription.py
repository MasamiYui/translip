from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .common import (
    AsrBackendName,
    Device,
    DiarizerBackendName,
    MediaInfo,
)


@dataclass(slots=True)
class TranscriptionRequest:
    input_path: Path | str
    output_dir: Path | str = Path("output")
    language: str = "zh"
    asr_model: str = "paraformer-zh"
    asr_backend: AsrBackendName = "funasr"
    diarizer_backend: DiarizerBackendName = "ecapa"
    enable_diarization: bool = True
    device: Device = "auto"
    audio_stream_index: int = 0
    keep_intermediate: bool = False
    write_srt: bool = True
    vad_filter: bool = True
    vad_min_silence_duration_ms: int = 400
    vad_max_segment_sec: float = 30.0
    expected_speakers: int = 0
    beam_size: int = 5
    best_of: int = 5
    temperature: float = 0.0
    condition_on_previous_text: bool = False
    # Proper-noun / terminology bias terms for the ASR backend (ASR-7).
    hotwords: tuple[str, ...] = field(default_factory=tuple)

    def normalized(self) -> "TranscriptionRequest":
        return TranscriptionRequest(
            input_path=Path(self.input_path).expanduser().resolve(),
            output_dir=Path(self.output_dir).expanduser().resolve(),
            language=self.language,
            asr_model=self.asr_model,
            asr_backend=self.asr_backend,
            diarizer_backend=self.diarizer_backend,
            enable_diarization=bool(self.enable_diarization),
            device=self.device,
            audio_stream_index=self.audio_stream_index,
            keep_intermediate=self.keep_intermediate,
            write_srt=self.write_srt,
            vad_filter=self.vad_filter,
            vad_min_silence_duration_ms=int(self.vad_min_silence_duration_ms),
            vad_max_segment_sec=float(self.vad_max_segment_sec),
            expected_speakers=int(self.expected_speakers),
            beam_size=int(self.beam_size),
            best_of=int(self.best_of),
            temperature=float(self.temperature),
            condition_on_previous_text=self.condition_on_previous_text,
            hotwords=tuple(self.hotwords),
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
    diarization_report_path: Path | None = None
    intermediate_paths: dict[str, Path] = field(default_factory=dict)


@dataclass(slots=True)
class TranscriptionResult:
    request: TranscriptionRequest
    media_info: MediaInfo
    artifacts: TranscriptionArtifacts
    segments: list[TranscriptionSegment]
    manifest: dict[str, Any]
    work_dir: Path


__all__ = [
    "TranscriptionRequest",
    "TranscriptionSegment",
    "TranscriptionArtifacts",
    "TranscriptionResult",
]
