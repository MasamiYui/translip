from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import torch
from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AsrSegment:
    segment_id: str
    start: float
    end: float
    text: str
    language: str

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


def resolve_asr_device(requested_device: str) -> str:
    if requested_device == "cuda":
        if not torch.cuda.is_available():
            logger.warning("CUDA requested for ASR but is unavailable. Falling back to CPU.")
            return "cpu"
        return "cuda"
    if requested_device == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    if requested_device == "mps":
        logger.info("faster-whisper does not support MPS directly. Using CPU for ASR.")
        return "cpu"
    return "cpu"


def _compute_type(device: str) -> str:
    return "float16" if device == "cuda" else "int8"


@lru_cache(maxsize=4)
def _load_model(model_name: str, device: str, compute_type: str) -> WhisperModel:
    return WhisperModel(model_name, device=device, compute_type=compute_type)


def transcribe_audio(
    audio_path: Path,
    *,
    model_name: str,
    language: str,
    requested_device: str,
) -> tuple[list[AsrSegment], dict[str, str | float | int]]:
    device = resolve_asr_device(requested_device)
    model = _load_model(model_name, device, _compute_type(device))

    segments_iter, info = model.transcribe(
        str(audio_path),
        language=language or None,
        vad_filter=True,
        beam_size=5,
        best_of=5,
        temperature=0.0,
        condition_on_previous_text=False,
        vad_parameters={"min_silence_duration_ms": 400},
    )

    detected_language = info.language or language or "unknown"
    segments: list[AsrSegment] = []
    for index, segment in enumerate(segments_iter, start=1):
        text = (segment.text or "").strip()
        if not text:
            continue
        start = max(0.0, float(segment.start))
        end = max(start, float(segment.end))
        segments.append(
            AsrSegment(
                segment_id=f"seg-{index:04d}",
                start=round(start, 3),
                end=round(end, 3),
                text=text,
                language=detected_language,
            )
        )

    metadata: dict[str, str | float | int] = {
        "asr_backend": "faster-whisper",
        "asr_model": model_name,
        "asr_device": device,
        "detected_language": detected_language,
        "segment_count": len(segments),
    }
    return segments, metadata
