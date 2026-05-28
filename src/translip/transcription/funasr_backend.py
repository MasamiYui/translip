from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path

import torch

from .asr import AsrOptions, AsrSegment

logger = logging.getLogger(__name__)


_SENSEVOICE_TAG_PATTERN = re.compile(r"<\|[^|]*\|>")
_LANGUAGE_TAG_MAP = {
    "zh": "zh",
    "yue": "yue",
    "en": "en",
    "ja": "ja",
    "ko": "ko",
    "auto": "auto",
}


def _resolve_funasr_device(requested_device: str) -> str:
    if requested_device == "cuda":
        if not torch.cuda.is_available():
            logger.warning("CUDA requested for FunASR but is unavailable. Falling back to CPU.")
            return "cpu"
        return "cuda"
    if requested_device == "auto":
        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
            return "mps"
        return "cpu"
    if requested_device == "mps":
        if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
            return "mps"
        logger.info("MPS requested but unavailable; falling back to CPU for FunASR.")
        return "cpu"
    return "cpu"


def _normalize_language(language: str | None) -> str:
    if not language:
        return "auto"
    key = language.strip().lower()
    return _LANGUAGE_TAG_MAP.get(key, "auto")


def _resolve_model_id(model_name: str | None) -> str:
    candidate = (model_name or "").strip()
    if not candidate or candidate.lower() in {"small", "base", "medium", "large", "large-v3", "tiny"}:
        return "iic/SenseVoiceSmall"
    return candidate


@lru_cache(maxsize=2)
def _load_sensevoice_model(model_id: str, device: str):
    try:
        from funasr import AutoModel
    except ImportError as exc:  # pragma: no cover - import guard
        raise RuntimeError(
            "FunASR is not installed. Run `pip install funasr` to enable the FunASR backend."
        ) from exc

    return AutoModel(
        model=model_id,
        vad_model="fsmn-vad",
        vad_kwargs={"max_single_segment_time": 30000},
        punc_model="ct-punc",
        device=device,
        disable_update=True,
    )


def _strip_sensevoice_tags(text: str) -> str:
    return _SENSEVOICE_TAG_PATTERN.sub("", text or "").strip()


def transcribe_audio(
    audio_path: Path,
    *,
    model_name: str,
    language: str,
    requested_device: str,
    options: AsrOptions | None = None,
) -> tuple[list[AsrSegment], dict[str, str | float | int | bool]]:
    """FunASR (SenseVoice-Small + FSMN-VAD + CT-Punc) ASR backend.

    The returned shape mirrors :func:`translip.transcription.asr.transcribe_audio` so that
    the caller can swap backends without further changes.
    """
    device = _resolve_funasr_device(requested_device)
    model_id = _resolve_model_id(model_name)
    resolved_options = options or AsrOptions()
    normalized_language = _normalize_language(language)

    model = _load_sensevoice_model(model_id, device)
    raw_results = model.generate(
        input=str(audio_path),
        cache={},
        language=normalized_language,
        use_itn=True,
        batch_size_s=60,
        merge_vad=True,
        merge_length_s=15,
    )

    segments: list[AsrSegment] = []
    detected_language = normalized_language if normalized_language != "auto" else "unknown"
    for index, item in enumerate(raw_results, start=1):
        text = _strip_sensevoice_tags(item.get("text", ""))
        if not text:
            continue
        timestamp = item.get("timestamp")
        if timestamp:
            start = max(0.0, float(timestamp[0][0]) / 1000.0)
            end = max(start, float(timestamp[-1][1]) / 1000.0)
        else:
            start = 0.0
            end = 0.0
        sentence_lang = (item.get("lang") or normalized_language or "unknown").lower()
        if normalized_language == "auto" and sentence_lang and sentence_lang != "auto":
            detected_language = sentence_lang
        segments.append(
            AsrSegment(
                segment_id=f"seg-{index:04d}",
                start=round(start, 3),
                end=round(end, 3),
                text=text,
                language=sentence_lang or detected_language,
            )
        )

    metadata: dict[str, str | float | int | bool] = {
        "asr_backend": "funasr-sensevoice",
        "asr_model": model_id,
        "asr_model_resolved": model_id,
        "asr_device": device,
        "detected_language": detected_language,
        "segment_count": len(segments),
        **resolved_options.metadata(),
    }
    return segments, metadata


__all__ = ["transcribe_audio"]
