from __future__ import annotations

import logging
import os
import re
import tempfile
from functools import lru_cache
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
import torch

from .asr import AsrOptions, AsrSegment

logger = logging.getLogger(__name__)


_TARGET_SAMPLE_RATE = 16000
# Match SenseVoice rich-text tags such as <|zh|><|NEUTRAL|><|Speech|><|woitn|>.
# The spaced form (e.g. "< | zh | >") is tolerated too, in case a tag ever
# survives into a downstream tokenizer, so emotion/event/language markers never
# leak into the transcript or subtitles.
_SENSEVOICE_TAG_PATTERN = re.compile(r"<\s*\|.*?\|\s*>")
_LANGUAGE_TAG_MAP = {
    "zh": "zh",
    "yue": "yue",
    "en": "en",
    "ja": "ja",
    "ko": "ko",
    "auto": "auto",
}
# FSMN-VAD already caps individual speech regions at this length; keep merged
# regions within the same bound so a chunk never grows unbounded.
_MAX_SEGMENT_SEC = 30.0
# Bridge speech regions separated by a tiny silence so we do not over-fragment
# a single utterance into many sub-second segments.
_MAX_MERGE_GAP_SEC = 0.5


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


# Generic size aliases (whisper-style) collapse to SenseVoice-Small so a caller
# that just asked for "small" still gets a working FunASR model.
_SENSEVOICE_SIZE_ALIASES = {"small", "base", "medium", "large", "large-v3", "tiny"}
# Aliases that select the Mandarin Paraformer (SeACo) model, which — unlike
# SenseVoice — predicts token timestamps we can split into per-utterance segments.
_PARAFORMER_ALIASES = {"paraformer", "paraformer-zh", "paraformer_zh"}


def _resolve_model_id(model_name: str | None) -> str:
    candidate = (model_name or "").strip()
    if candidate.lower() in _PARAFORMER_ALIASES:
        return "paraformer-zh"
    if not candidate or candidate.lower() in _SENSEVOICE_SIZE_ALIASES:
        return "iic/SenseVoiceSmall"
    return candidate


def _model_family(model_id: str) -> str:
    """Which FunASR sub-backend a resolved model id belongs to."""
    return "paraformer" if "paraformer" in model_id.lower() else "sensevoice"


def _import_automodel():
    try:
        from funasr import AutoModel
    except ImportError as exc:  # pragma: no cover - import guard
        raise RuntimeError(
            "FunASR is not installed. Run `pip install funasr` to enable the FunASR backend."
        ) from exc
    return AutoModel


@lru_cache(maxsize=2)
def _load_asr_model(model_id: str, device: str):
    AutoModel = _import_automodel()
    return AutoModel(model=model_id, device=device, disable_update=True)


@lru_cache(maxsize=4)
def _load_vad_model(device: str, max_segment_sec: float = _MAX_SEGMENT_SEC):
    AutoModel = _import_automodel()
    return AutoModel(
        model="fsmn-vad",
        vad_kwargs={"max_single_segment_time": int(max_segment_sec * 1000)},
        device=device,
        disable_update=True,
    )


@lru_cache(maxsize=2)
def _load_punc_model(device: str):
    AutoModel = _import_automodel()
    try:
        return AutoModel(model="ct-punc", device=device, disable_update=True)
    except Exception as exc:  # pragma: no cover - optional dependency / download failure
        logger.warning("Failed to load ct-punc model; transcripts will be unpunctuated. %s", exc)
        return None


@lru_cache(maxsize=4)
def _load_paraformer_model(model_id: str, device: str, max_segment_sec: float = _MAX_SEGMENT_SEC):
    """Paraformer with integrated VAD + punctuation.

    Unlike the SenseVoice path, the model itself runs VAD and emits token
    timestamps, so ``generate(sentence_timestamp=True)`` returns ``sentence_info``
    we can map to one :class:`AsrSegment` per utterance.
    """
    AutoModel = _import_automodel()
    return AutoModel(
        model=model_id,
        vad_model="fsmn-vad",
        vad_kwargs={"max_single_segment_time": int(max_segment_sec * 1000)},
        punc_model="ct-punc",
        device=device,
        disable_update=True,
    )


def _strip_sensevoice_tags(text: str) -> str:
    return _SENSEVOICE_TAG_PATTERN.sub("", text or "").strip()


def _clean_sentence(text: str) -> str:
    """Normalise a Paraformer sentence for subtitles/dubbing.

    ``sentence_info`` text ends at a sentence-final mark and may carry internal
    pause commas; turn those pauses into spaces and drop terminal punctuation so
    each line reads like the whisper backend's output (no trailing ``。``/``？``).
    """
    cleaned = re.sub(r"[，、]+", " ", (text or "").strip())
    cleaned = re.sub(r"[。？！?!]+", "", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _extract_vad_intervals(vad_results: object) -> list[tuple[float, float]]:
    """Turn FunASR FSMN-VAD output (``[{"value": [[start_ms, end_ms], ...]}]``) into seconds."""
    intervals: list[tuple[float, float]] = []
    if not isinstance(vad_results, (list, tuple)) or not vad_results:
        return intervals
    first = vad_results[0]
    value = first.get("value") if isinstance(first, dict) else None
    if not value:
        return intervals
    for pair in value:
        try:
            start = max(0.0, float(pair[0]) / 1000.0)
            end = max(start, float(pair[1]) / 1000.0)
        except (TypeError, ValueError, IndexError):
            continue
        if end > start:
            intervals.append((start, end))
    return intervals


def _merge_intervals(
    intervals: list[tuple[float, float]], max_segment_sec: float = _MAX_SEGMENT_SEC
) -> list[tuple[float, float]]:
    """Merge speech regions separated by short silences, capped at ``max_segment_sec``."""
    merged: list[tuple[float, float]] = []
    for start, end in intervals:
        if (
            merged
            and start - merged[-1][1] <= _MAX_MERGE_GAP_SEC
            and end - merged[-1][0] <= max_segment_sec
        ):
            merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))
    return merged


def _run_asr_on_chunk(asr_model, chunk: np.ndarray, *, language: str) -> list:
    """Transcribe one audio chunk. Prefers the in-memory array, falling back to a temp WAV."""
    kwargs = {"cache": {}, "language": language, "use_itn": True, "batch_size_s": 60}
    try:
        return asr_model.generate(input=chunk, **kwargs)
    except Exception as exc:  # pragma: no cover - depends on FunASR version's input handling
        logger.debug("In-memory ASR input failed (%s); retrying via a temporary WAV file.", exc)
        fd, tmp_path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            sf.write(tmp_path, chunk, _TARGET_SAMPLE_RATE)
            return asr_model.generate(input=tmp_path, **kwargs)
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def _apply_punctuation(punc_model, text: str) -> str:
    try:
        results = punc_model.generate(input=text)
    except Exception as exc:  # pragma: no cover - punctuation is best-effort
        logger.debug("Punctuation restoration failed: %s", exc)
        return text
    if results and isinstance(results[0], dict):
        return results[0].get("text") or text
    return text


def _transcribe_sensevoice(
    audio_path: Path,
    *,
    model_id: str,
    language: str,
    device: str,
    options: AsrOptions,
) -> tuple[list[AsrSegment], dict[str, str | float | int | bool]]:
    """FunASR SenseVoice-Small + FSMN-VAD + CT-Punc.

    Speech is first segmented with FSMN-VAD and each region is transcribed
    independently. SenseVoice does not expose token timestamps, so each segment
    inherits its VAD-region bounds — a region can therefore span several
    utterances of different speakers, which caps downstream diarization.
    """
    resolved_options = options
    normalized_language = _normalize_language(language)

    waveform, _ = librosa.load(str(audio_path), sr=_TARGET_SAMPLE_RATE, mono=True)
    waveform = np.ascontiguousarray(waveform, dtype=np.float32)
    audio_duration = round(len(waveform) / _TARGET_SAMPLE_RATE, 3)

    vad_model = _load_vad_model(device, resolved_options.vad_max_segment_sec)
    intervals = _merge_intervals(
        _extract_vad_intervals(vad_model.generate(input=str(audio_path))),
        resolved_options.vad_max_segment_sec,
    )
    if not intervals:
        # No speech detected (or VAD returned nothing): transcribe the whole file
        # as one window so we still emit a span with a real end time.
        intervals = [(0.0, audio_duration)]

    asr_model = _load_asr_model(model_id, device)
    punc_model = _load_punc_model(device)

    segments: list[AsrSegment] = []
    detected_language = normalized_language if normalized_language != "auto" else "unknown"
    index = 0
    for start, end in intervals:
        start_sample = max(0, int(round(start * _TARGET_SAMPLE_RATE)))
        end_sample = min(len(waveform), int(round(end * _TARGET_SAMPLE_RATE)))
        if end_sample <= start_sample:
            continue
        chunk = waveform[start_sample:end_sample]
        asr_results = _run_asr_on_chunk(asr_model, chunk, language=normalized_language)
        if not asr_results:
            continue
        item = asr_results[0]
        # Strip rich-text tags BEFORE punctuation: feeding tags into ct-punc is
        # what previously mangled them into un-strippable "< | zh | >" forms.
        text = _strip_sensevoice_tags(item.get("text", ""))
        if not text:
            continue
        if punc_model is not None:
            text = _apply_punctuation(punc_model, text)
        sentence_lang = (item.get("lang") or normalized_language or "unknown").lower()
        if normalized_language == "auto" and sentence_lang and sentence_lang != "auto":
            detected_language = sentence_lang
        index += 1
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
        "vad_backend": "fsmn-vad",
        "detected_language": detected_language,
        "audio_duration_sec": audio_duration,
        "segment_count": len(segments),
        **resolved_options.metadata(),
    }
    return segments, metadata


def _transcribe_paraformer(
    audio_path: Path,
    *,
    model_id: str,
    language: str,
    device: str,
    options: AsrOptions,
) -> tuple[list[AsrSegment], dict[str, str | float | int | bool]]:
    """FunASR Paraformer (SeACo) + FSMN-VAD + CT-Punc.

    Paraformer predicts token timestamps, so ``sentence_info`` returns one
    punctuation-delimited sentence per entry with real start/end times — i.e.
    utterance-level segments a single speaker label can attach to cleanly,
    instead of SenseVoice's multi-utterance VAD regions.
    """
    info = sf.info(str(audio_path))
    audio_duration = round(info.frames / float(info.samplerate), 3) if info.samplerate else 0.0

    model = _load_paraformer_model(model_id, device, options.vad_max_segment_sec)
    results = model.generate(
        input=str(audio_path),
        batch_size_s=300,
        use_itn=True,
        sentence_timestamp=True,
    )
    item = results[0] if results and isinstance(results[0], dict) else {}
    sentences = item.get("sentence_info") or []

    segments: list[AsrSegment] = []
    for raw in sentences:
        text = _clean_sentence(raw.get("text") or raw.get("sentence") or "")
        if not text:
            continue
        start = max(0.0, float(raw.get("start", 0.0)) / 1000.0)
        end = max(start, float(raw.get("end", start)) / 1000.0)
        segments.append(
            AsrSegment(
                segment_id=f"seg-{len(segments) + 1:04d}",
                start=round(start, 3),
                end=round(end, 3),
                text=text,
                language="zh",
            )
        )

    if not segments:
        # No sentence segmentation (e.g. punctuation model unavailable): fall back
        # to a single span so the file still yields a transcript with a real end.
        full_text = _clean_sentence(item.get("text", ""))
        if full_text:
            segments.append(
                AsrSegment(segment_id="seg-0001", start=0.0, end=audio_duration, text=full_text, language="zh")
            )

    metadata: dict[str, str | float | int | bool] = {
        "asr_backend": "funasr-paraformer",
        "asr_model": model_id,
        "asr_model_resolved": model_id,
        "asr_device": device,
        "vad_backend": "fsmn-vad",
        "punc_backend": "ct-punc",
        "detected_language": "zh",
        "audio_duration_sec": audio_duration,
        "segment_count": len(segments),
        **options.metadata(),
    }
    return segments, metadata


def transcribe_audio(
    audio_path: Path,
    *,
    model_name: str,
    language: str,
    requested_device: str,
    options: AsrOptions | None = None,
) -> tuple[list[AsrSegment], dict[str, str | float | int | bool]]:
    """FunASR backend dispatcher.

    Routes to Paraformer (timestamped, utterance-level segments) or SenseVoice
    (VAD-region segments) by resolved model id. The returned shape mirrors
    :func:`translip.transcription.asr.transcribe_audio` so callers can swap
    backends without further changes.
    """
    device = _resolve_funasr_device(requested_device)
    model_id = _resolve_model_id(model_name)
    resolved_options = options or AsrOptions()
    if _model_family(model_id) == "paraformer":
        return _transcribe_paraformer(
            audio_path, model_id=model_id, language=language, device=device, options=resolved_options
        )
    return _transcribe_sensevoice(
        audio_path, model_id=model_id, language=language, device=device, options=resolved_options
    )


__all__ = ["transcribe_audio"]
