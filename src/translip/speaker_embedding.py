from __future__ import annotations

import importlib
import os
import tempfile
from functools import lru_cache
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from speechbrain.inference.speaker import EncoderClassifier

from .config import CACHE_ROOT

SPEAKER_EMBEDDING_SAMPLE_RATE = 16_000
MIN_EMBEDDING_SEC = 1.0

SPEAKER_EMBEDDER_ENV = "TRANSLIP_SPEAKER_EMBEDDER"

ECAPA_EMBEDDER_NAME = "speechbrain-ecapa"
ERES2NETV2_EMBEDDER_NAME = "eres2netv2"
DEFAULT_SPEAKER_EMBEDDER = "auto"


def resolve_speaker_device(requested_device: str) -> str:
    if requested_device == "cuda":
        if not torch.cuda.is_available():
            return "cpu"
        return "cuda"
    if requested_device == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    if requested_device == "mps":
        return "cpu"
    return "cpu"


@lru_cache(maxsize=2)
def load_speechbrain_classifier(device: str) -> EncoderClassifier:
    savedir = CACHE_ROOT / "speechbrain" / "spkrec-ecapa-voxceleb"
    return EncoderClassifier.from_hparams(
        source="speechbrain/spkrec-ecapa-voxceleb",
        savedir=str(savedir),
        run_opts={"device": device},
    )


def normalize_embedding(embedding: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(embedding)
    if norm <= 1e-12:
        return embedding.astype(np.float32)
    return (embedding / norm).astype(np.float32)


def read_audio_mono(audio_path: Path) -> tuple[np.ndarray, int]:
    waveform, sample_rate = sf.read(audio_path, dtype="float32", always_2d=False)
    if waveform.ndim == 2:
        waveform = waveform.mean(axis=1)
    return waveform.astype(np.float32), sample_rate


def extract_audio_clip(
    waveform: np.ndarray,
    sample_rate: int,
    *,
    start: float,
    end: float,
) -> np.ndarray:
    start_idx = max(0, int(start * sample_rate))
    end_idx = min(len(waveform), int(end * sample_rate))
    if end_idx <= start_idx:
        return np.zeros(0, dtype=np.float32)
    return waveform[start_idx:end_idx].astype(np.float32)


def embedding_for_clip(
    classifier: EncoderClassifier,
    clip: np.ndarray,
    sample_rate: int,
) -> np.ndarray | None:
    if clip.size == 0:
        return None
    prepared = _prepare_embedding_audio(clip, sample_rate)
    tensor = torch.from_numpy(prepared).float().unsqueeze(0)
    with torch.inference_mode():
        embedding = classifier.encode_batch(tensor).squeeze().detach().cpu().numpy()
    return normalize_embedding(embedding)


def _prepare_embedding_audio(clip: np.ndarray, sample_rate: int) -> np.ndarray:
    normalized = clip.astype(np.float32)
    if sample_rate <= 0:
        return normalized
    if sample_rate != SPEAKER_EMBEDDING_SAMPLE_RATE:
        normalized = _resample_linear(normalized, sample_rate, SPEAKER_EMBEDDING_SAMPLE_RATE)
    min_samples = int(MIN_EMBEDDING_SEC * SPEAKER_EMBEDDING_SAMPLE_RATE)
    if normalized.size == 0:
        return normalized
    if normalized.size < min_samples:
        repeats = (min_samples + normalized.size - 1) // normalized.size
        normalized = np.tile(normalized, repeats)[:min_samples]
    return normalized.astype(np.float32)


def _resample_linear(waveform: np.ndarray, original_rate: int, target_rate: int) -> np.ndarray:
    if waveform.size == 0 or original_rate == target_rate:
        return waveform.astype(np.float32)
    duration_sec = waveform.size / float(original_rate)
    target_size = max(1, int(round(duration_sec * target_rate)))
    source_index = np.linspace(0.0, waveform.size - 1, num=waveform.size, dtype=np.float32)
    target_index = np.linspace(0.0, waveform.size - 1, num=target_size, dtype=np.float32)
    return np.interp(target_index, source_index, waveform).astype(np.float32)


# ---------------------------------------------------------------------------
# Embedder abstraction layer
# ---------------------------------------------------------------------------
#
# The legacy code path uses SpeechBrain's ECAPA-TDNN classifier directly via
# :func:`embedding_for_clip`.  Newer Chinese-optimised models such as
# 3D-Speaker's ``ERes2NetV2`` live inside ModelScope pipelines and have a
# different I/O shape.  To let the diarization and dubbing-metrics paths share
# a single configurable extractor, we expose a tiny :class:`SpeakerEmbedder`
# protocol backed by two concrete implementations.
#
# Selection is driven by the ``TRANSLIP_SPEAKER_EMBEDDER`` environment variable
# (``auto`` / ``speechbrain-ecapa`` / ``eres2netv2``).  ``auto`` prefers the
# ERes2NetV2 pipeline when ModelScope is installed and silently falls back to
# ECAPA otherwise, so legacy deployments keep working unchanged.


class SpeakerEmbedder:
    """Minimal duck-typed base class for speaker embedders."""

    name: str = "unknown"
    embedding_dim: int = 0

    def encode(self, clip: np.ndarray, sample_rate: int) -> np.ndarray | None:
        raise NotImplementedError


class _EcapaEmbedder(SpeakerEmbedder):
    name = ECAPA_EMBEDDER_NAME
    embedding_dim = 192

    def __init__(self, device: str) -> None:
        self._device = device
        self._classifier = load_speechbrain_classifier(device)

    def encode(self, clip: np.ndarray, sample_rate: int) -> np.ndarray | None:
        return embedding_for_clip(self._classifier, clip, sample_rate)


def _has_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


class _Eres2NetV2Embedder(SpeakerEmbedder):
    name = ERES2NETV2_EMBEDDER_NAME
    embedding_dim = 192

    MODEL_ID = "iic/speech_eres2netv2_sv_zh-cn_16k-common"

    def __init__(self) -> None:
        from modelscope.pipelines import pipeline as ms_pipeline

        self._pipeline = ms_pipeline(
            task="speaker-verification",
            model=self.MODEL_ID,
        )

    def encode(self, clip: np.ndarray, sample_rate: int) -> np.ndarray | None:
        if clip.size == 0:
            return None
        prepared = _prepare_embedding_audio(clip, sample_rate)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
            wav_path = Path(handle.name)
        try:
            sf.write(wav_path, prepared, SPEAKER_EMBEDDING_SAMPLE_RATE, subtype="PCM_16")
            result = self._pipeline([str(wav_path)], output_emb=True)
        finally:
            wav_path.unlink(missing_ok=True)
        if not isinstance(result, dict):
            return None
        embs = result.get("embs")
        if embs is None:
            return None
        array = np.asarray(embs, dtype=np.float32)
        if array.ndim == 2:
            array = array[0]
        if array.size == 0:
            return None
        return normalize_embedding(array)


@lru_cache(maxsize=4)
def _cached_embedder(name: str, device: str) -> SpeakerEmbedder:
    if name == ERES2NETV2_EMBEDDER_NAME:
        return _Eres2NetV2Embedder()
    return _EcapaEmbedder(device)


def resolve_speaker_embedder_name(raw: str | None = None) -> str:
    value = (raw or os.environ.get(SPEAKER_EMBEDDER_ENV) or DEFAULT_SPEAKER_EMBEDDER).strip().lower()
    if value in {"auto", ""}:
        if _has_module("modelscope") and _has_module("funasr"):
            return ERES2NETV2_EMBEDDER_NAME
        return ECAPA_EMBEDDER_NAME
    if value in {"ecapa", "speechbrain", ECAPA_EMBEDDER_NAME}:
        return ECAPA_EMBEDDER_NAME
    if value in {"eres2net", "eres2netv2", ERES2NETV2_EMBEDDER_NAME}:
        return ERES2NETV2_EMBEDDER_NAME
    return ECAPA_EMBEDDER_NAME


def get_speaker_embedder(
    requested_device: str,
    *,
    name: str | None = None,
) -> SpeakerEmbedder:
    """Return the configured :class:`SpeakerEmbedder`.

    Parameters
    ----------
    requested_device:
        Device requested by the caller; only used by the ECAPA backend.  The
        ModelScope pipeline auto-selects CPU/GPU internally.
    name:
        Optional override.  Defaults to the ``TRANSLIP_SPEAKER_EMBEDDER`` env
        var with ``auto`` semantics (see :func:`resolve_speaker_embedder_name`).
    """

    resolved = resolve_speaker_embedder_name(name)
    device = resolve_speaker_device(requested_device)
    try:
        return _cached_embedder(resolved, device)
    except Exception:
        if resolved == ERES2NETV2_EMBEDDER_NAME:
            # Fall back to ECAPA if ModelScope fails at load time so the
            # pipeline keeps running on machines without the optional deps.
            return _cached_embedder(ECAPA_EMBEDDER_NAME, device)
        raise
