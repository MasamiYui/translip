"""PSNR / SSIM unit tests."""
from __future__ import annotations

import numpy as np

from translip_lab.metrics.image import psnr, ssim


def test_psnr_identical_is_inf():
    rng = np.random.default_rng(0)
    img = rng.integers(0, 256, size=(32, 32, 3), dtype=np.uint8)
    assert psnr(img, img) == float("inf")


def test_psnr_finite_for_difference():
    rng = np.random.default_rng(1)
    a = rng.integers(0, 256, size=(32, 32, 3), dtype=np.uint8)
    b = a.copy()
    b[0, 0, 0] = (int(b[0, 0, 0]) + 100) % 256
    val = psnr(a, b)
    assert np.isfinite(val) and val > 30.0


def test_ssim_identical_is_one():
    rng = np.random.default_rng(2)
    img = rng.integers(0, 256, size=(64, 64, 3), dtype=np.uint8)
    assert ssim(img, img) > 0.999


def test_ssim_low_for_very_different():
    a = np.zeros((64, 64, 3), dtype=np.uint8)
    b = np.full((64, 64, 3), 255, dtype=np.uint8)
    assert ssim(a, b) < 0.2


def test_ssim_decreases_with_noise():
    rng = np.random.default_rng(3)
    base = rng.integers(0, 256, size=(64, 64, 3), dtype=np.uint8).astype(np.float64)
    noisy = np.clip(base + 40 * rng.standard_normal(base.shape), 0, 255)
    assert ssim(base, base) > ssim(base, noisy)


def test_ssim_handles_shape_mismatch():
    a = np.zeros((64, 64, 3), dtype=np.uint8)
    b = np.zeros((60, 70, 3), dtype=np.uint8)
    # should crop to the common region without raising
    assert ssim(a, b) > 0.999
