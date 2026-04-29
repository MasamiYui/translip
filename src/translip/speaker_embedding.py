from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from speechbrain.inference.speaker import EncoderClassifier

from .config import CACHE_ROOT

SPEAKER_EMBEDDING_SAMPLE_RATE = 16_000
MIN_EMBEDDING_SEC = 1.0


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
