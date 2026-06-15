"""Image fidelity metrics: PSNR and a windowed SSIM (numpy/scipy only).

Used by the subtitle-erase scenario to compare translip's cleaned frames against
the subtitle-free reference frames (synthetic GT). Inputs are HxWx3 uint8 (or
HxW grayscale). SSIM uses a uniform 7x7 window — close to skimage's default and
fully dependency-free.
"""
from __future__ import annotations

import numpy as np


def _to_gray(img: np.ndarray) -> np.ndarray:
    img = np.asarray(img, dtype=np.float64)
    if img.ndim == 2:
        return img
    return img[..., :3] @ np.array([0.299, 0.587, 0.114])


def _match(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if a.shape[:2] != b.shape[:2]:
        h = min(a.shape[0], b.shape[0])
        w = min(a.shape[1], b.shape[1])
        a = a[:h, :w]
        b = b[:h, :w]
    return a, b


def psnr(a: np.ndarray, b: np.ndarray, *, max_val: float = 255.0) -> float:
    """Peak signal-to-noise ratio (dB). Identical images → +inf."""
    a, b = _match(np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64))
    mse = float(np.mean((a - b) ** 2))
    if mse == 0.0:
        return float("inf")
    return 10.0 * np.log10(max_val ** 2 / mse)


def ssim(a: np.ndarray, b: np.ndarray, *, win: int = 7, max_val: float = 255.0) -> float:
    """Mean structural similarity over a uniform window. Identical images → 1.0."""
    from scipy.ndimage import uniform_filter

    ga, gb = _match(_to_gray(a), _to_gray(b))
    c1 = (0.01 * max_val) ** 2
    c2 = (0.03 * max_val) ** 2
    mu_a = uniform_filter(ga, win)
    mu_b = uniform_filter(gb, win)
    mu_a2, mu_b2, mu_ab = mu_a * mu_a, mu_b * mu_b, mu_a * mu_b
    var_a = uniform_filter(ga * ga, win) - mu_a2
    var_b = uniform_filter(gb * gb, win) - mu_b2
    cov = uniform_filter(ga * gb, win) - mu_ab
    num = (2 * mu_ab + c1) * (2 * cov + c2)
    den = (mu_a2 + mu_b2 + c1) * (var_a + var_b + c2)
    return float(np.mean(num / den))
