from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path

import torch
from faster_whisper import WhisperModel
try:
    from faster_whisper.utils import _MODELS as FASTER_WHISPER_MODEL_ALIASES
except ImportError:  # pragma: no cover - compatibility guard for future faster-whisper releases.
    FASTER_WHISPER_MODEL_ALIASES = {
        "tiny": "Systran/faster-whisper-tiny",
        "base": "Systran/faster-whisper-base",
        "small": "Systran/faster-whisper-small",
        "medium": "Systran/faster-whisper-medium",
        "large-v3": "Systran/faster-whisper-large-v3",
    }
from huggingface_hub import try_to_load_from_cache

logger = logging.getLogger(__name__)

_FASTER_WHISPER_REQUIRED_FILES = ("model.bin", "config.json", "tokenizer.json", "vocabulary.txt")


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


@dataclass(slots=True)
class AsrOptions:
    vad_filter: bool = True
    vad_min_silence_duration_ms: int = 400
    beam_size: int = 5
    best_of: int = 5
    temperature: float = 0.0
    condition_on_previous_text: bool = False

    def metadata(self) -> dict[str, bool | int | float]:
        return asdict(self)


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


def _repo_id_for_model(model_name: str) -> str | None:
    normalized = model_name.strip()
    if normalized in FASTER_WHISPER_MODEL_ALIASES:
        return FASTER_WHISPER_MODEL_ALIASES[normalized]
    if normalized.startswith("Systran/faster-whisper-"):
        return normalized
    return None


def resolve_faster_whisper_model_path(model_name: str, *, cache_dir: Path | str | None = None) -> str:
    """Resolve a cached faster-whisper model to a local snapshot path when possible."""
    repo_id = _repo_id_for_model(model_name)
    if repo_id is None:
        return model_name

    cached_files: list[Path] = []
    for filename in _FASTER_WHISPER_REQUIRED_FILES:
        cached_file = try_to_load_from_cache(repo_id, filename, cache_dir=cache_dir)
        if not isinstance(cached_file, str):
            return model_name
        cached_path = Path(cached_file)
        if not cached_path.exists():
            return model_name
        cached_files.append(cached_path)

    snapshot_dir = cached_files[0].parent
    if any(path.parent != snapshot_dir for path in cached_files):
        return model_name
    return str(snapshot_dir)


@lru_cache(maxsize=4)
def _load_model(model_name: str, device: str, compute_type: str) -> WhisperModel:
    return WhisperModel(model_name, device=device, compute_type=compute_type)


def transcribe_audio(
    audio_path: Path,
    *,
    model_name: str,
    language: str,
    requested_device: str,
    options: AsrOptions | None = None,
) -> tuple[list[AsrSegment], dict[str, str | float | int | bool]]:
    device = resolve_asr_device(requested_device)
    resolved_model_path = resolve_faster_whisper_model_path(model_name)
    model = _load_model(resolved_model_path, device, _compute_type(device))
    resolved_options = options or AsrOptions()

    transcribe_kwargs: dict[str, object] = {
        "language": language or None,
        "vad_filter": resolved_options.vad_filter,
        "beam_size": resolved_options.beam_size,
        "best_of": resolved_options.best_of,
        "temperature": resolved_options.temperature,
        "condition_on_previous_text": resolved_options.condition_on_previous_text,
    }
    if resolved_options.vad_filter:
        transcribe_kwargs["vad_parameters"] = {
            "min_silence_duration_ms": resolved_options.vad_min_silence_duration_ms,
        }

    segments_iter, info = model.transcribe(
        str(audio_path),
        **transcribe_kwargs,
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

    metadata: dict[str, str | float | int | bool] = {
        "asr_backend": "faster-whisper",
        "asr_model": model_name,
        "asr_model_resolved": resolved_model_path,
        "asr_device": device,
        "detected_language": detected_language,
        "segment_count": len(segments),
        **resolved_options.metadata(),
    }
    return segments, metadata
