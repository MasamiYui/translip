from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from speechbrain.inference.speaker import EncoderClassifier

from .config import CACHE_ROOT


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
) -> np.ndarray | None:
    if clip.size == 0:
        return None
    tensor = torch.from_numpy(clip).float().unsqueeze(0)
    with torch.inference_mode():
        embedding = classifier.encode_batch(tensor).squeeze().detach().cpu().numpy()
    return normalize_embedding(embedding)
