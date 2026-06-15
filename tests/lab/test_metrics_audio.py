"""SI-SDR / SDR unit tests."""
from __future__ import annotations

import numpy as np

from translip_lab.metrics.audio import sdr, si_sdr


def test_si_sdr_identical_is_large():
    rng = np.random.default_rng(0)
    x = rng.standard_normal(16000)
    assert si_sdr(x, x) >= 100.0
    assert sdr(x, x) >= 100.0


def test_si_sdr_is_scale_invariant():
    rng = np.random.default_rng(1)
    ref = rng.standard_normal(16000)
    est = ref + 0.05 * rng.standard_normal(16000)
    base = si_sdr(est, ref)
    scaled = si_sdr(5.0 * est, ref)
    assert abs(base - scaled) < 1e-3  # SI-SDR ignores a global gain
    assert 10.0 < base < 100.0  # a sane mid-range value, not clamped


def test_si_sdr_monotonic_in_noise():
    rng = np.random.default_rng(2)
    ref = np.sin(np.linspace(0, 200 * np.pi, 16000))
    noise = rng.standard_normal(16000)
    clean = si_sdr(ref + 0.05 * noise, ref)
    dirty = si_sdr(ref + 0.5 * noise, ref)
    assert clean > dirty


def test_length_mismatch_truncates():
    rng = np.random.default_rng(3)
    ref = rng.standard_normal(16000)
    est = np.concatenate([ref, rng.standard_normal(500)])  # longer estimate
    assert si_sdr(est, ref) >= 100.0
