"""Source-separation metrics: SI-SDR (scale-invariant) and plain SDR, in dB.

Used by the separation scenario against synthetic mixes where the clean voice /
background stems are known exactly. Higher is better. Identical signals yield a
large (clamped) value rather than +inf.
"""
from __future__ import annotations

import numpy as np

_MAX_DB = 120.0  # clamp for (near-)perfect reconstruction


def _align(est: np.ndarray, ref: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    est = np.asarray(est, dtype=np.float64).reshape(-1)
    ref = np.asarray(ref, dtype=np.float64).reshape(-1)
    n = min(len(est), len(ref))
    return est[:n], ref[:n]


def si_sdr(estimate: np.ndarray, reference: np.ndarray, *, eps: float = 1e-12) -> float:
    """Scale-invariant SDR (dB). Invariant to a global gain on the estimate."""
    est, ref = _align(estimate, reference)
    est = est - est.mean()
    ref = ref - ref.mean()
    ref_energy = float(np.dot(ref, ref)) + eps
    alpha = float(np.dot(est, ref)) / ref_energy
    proj = alpha * ref
    noise = est - proj
    ratio = float(np.dot(proj, proj)) / (float(np.dot(noise, noise)) + eps)
    return min(_MAX_DB, 10.0 * np.log10(ratio + eps))


def sdr(estimate: np.ndarray, reference: np.ndarray, *, eps: float = 1e-12) -> float:
    """Plain signal-to-distortion ratio (dB): 10log10(||ref||^2 / ||ref-est||^2)."""
    est, ref = _align(estimate, reference)
    ref_energy = float(np.dot(ref, ref))
    noise = ref - est
    noise_energy = float(np.dot(noise, noise))
    ratio = (ref_energy + eps) / (noise_energy + eps)
    return min(_MAX_DB, 10.0 * np.log10(ratio + eps))
