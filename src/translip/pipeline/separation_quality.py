"""Separation output quality metrics (SEP-2).

Cheap, dependency-light measures of how well stage 1 split the mix, written to
the separation manifest so a low-quality separation is *detectable* (e.g. to drive a
quality escalation) instead of silently flowing downstream to ASR/diarization.

All functions are pure (numpy) and tolerant of differing lengths; the reconstruction
residual is only reported when the three tracks share a sample rate.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np

_EPS = 1e-9


def _load_mono(path: Path) -> tuple[np.ndarray, int]:
    import soundfile as sf

    data, sample_rate = sf.read(str(path), dtype="float32", always_2d=False)
    array = np.asarray(data, dtype=np.float32)
    if array.ndim == 2:
        array = array.mean(axis=1)
    return np.squeeze(array).astype(np.float32), int(sample_rate)


def _rms(signal: np.ndarray) -> float:
    if signal.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(signal, dtype=np.float64))))


def separation_metrics(
    *,
    voice: np.ndarray,
    background: np.ndarray,
    mix: np.ndarray,
    same_sample_rate: bool = True,
) -> dict[str, Any]:
    """Compute quality metrics from already-loaded mono signals.

    Split out from the file loader so it can be unit-tested with synthetic arrays.
    """
    length = min(len(voice), len(background), len(mix))
    if length == 0:
        return {}
    voice = voice[:length]
    background = background[:length]
    mix = mix[:length]

    voice_rms = _rms(voice)
    background_rms = _rms(background)
    mix_rms = _rms(mix)

    metrics: dict[str, Any] = {
        "voice_rms": round(voice_rms, 6),
        "background_rms": round(background_rms, 6),
        "voice_to_background_db": round(20.0 * math.log10((voice_rms + _EPS) / (background_rms + _EPS)), 2),
    }

    if same_sample_rate:
        residual = mix - (voice + background)
        residual_ratio = _rms(residual) / (mix_rms + _EPS)
        metrics["reconstruction_residual_ratio"] = round(float(residual_ratio), 4)
        # Low residual => voice+background reconstruct the mix well. Bounded to [0,1].
        metrics["separation_confidence"] = round(max(0.0, min(1.0, 1.0 - residual_ratio)), 3)

    return metrics


def compute_separation_metrics(
    *, voice_path: Path, background_path: Path, mix_path: Path
) -> dict[str, Any]:
    """Load the three tracks and compute :func:`separation_metrics`."""
    voice, sr_v = _load_mono(voice_path)
    background, sr_b = _load_mono(background_path)
    mix, sr_m = _load_mono(mix_path)
    return separation_metrics(
        voice=voice,
        background=background,
        mix=mix,
        same_sample_rate=(sr_v == sr_b == sr_m),
    )
