"""Image padding/normalization helpers for the big-LaMa backend.

Ported from video-subtitle-remover ``backend/inpaint/utils/lama_util.py``
(itself from advimman/lama). big-LaMa expects CHW float32 ``[0, 1]`` tensors
padded to a multiple of 8; masks are binarized to ``{0, 1}``.
"""
from __future__ import annotations

import numpy as np


def to_chw_float(image: np.ndarray) -> np.ndarray:
    """HWC (or HW) uint8 -> CHW float32 in ``[0, 1]``."""
    img = image.astype(np.float32) / 255.0
    if img.ndim == 3:
        return np.transpose(img, (2, 0, 1))
    return img[np.newaxis, ...]


def ceil_modulo(value: int, mod: int) -> int:
    if value % mod == 0:
        return value
    return (value // mod + 1) * mod


def pad_to_modulo(img: np.ndarray, mod: int = 8) -> np.ndarray:
    """Symmetric-pad a CHW array so H and W are multiples of ``mod``."""
    _, height, width = img.shape
    return np.pad(
        img,
        ((0, 0), (0, ceil_modulo(height, mod) - height), (0, ceil_modulo(width, mod) - width)),
        mode="symmetric",
    )


__all__ = ["to_chw_float", "ceil_modulo", "pad_to_modulo"]
