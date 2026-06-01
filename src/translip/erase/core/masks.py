"""Subtitle mask construction and inpaint-band selection.

Ported (and cleaned) from video-subtitle-remover's ``tools/inpaint_tools.py``
(``create_mask`` + ``get_inpaint_area_by_mask``). Coordinate convention for a
box here is ``(xmin, xmax, ymin, ymax)`` — width-pair first — matching the
upstream mask code. Mask images are 2-D ``uint8`` with values ``{0, 255}`` and
shape ``(H, W)``.
"""
from __future__ import annotations

import cv2
import numpy as np


def create_mask(
    size_hw: tuple[int, int],
    boxes: list[tuple[int, int, int, int]],
    *,
    dilate_x: int = 12,
    dilate_y: int = 8,
) -> np.ndarray:
    """Paint every ``(xmin, xmax, ymin, ymax)`` box as a filled white rectangle.

    Each box is dilated outward by ``dilate_x``/``dilate_y`` pixels so the
    inpainter also covers anti-aliased glyph edges. Overlapping boxes merge
    naturally as filled pixels.
    """
    height, width = size_hw
    mask = np.zeros((height, width), dtype=np.uint8)
    for xmin, xmax, ymin, ymax in boxes:
        x1 = max(0, xmin - dilate_x)
        y1 = max(0, ymin - dilate_y)
        x2 = min(width, xmax + dilate_x)
        y2 = min(height, ymax + dilate_y)
        cv2.rectangle(mask, (x1, y1), (x2, y2), 255, thickness=-1)
    return mask


def get_inpaint_bands(width: int, height: int, band_height: int, mask: np.ndarray) -> list[tuple[int, int]]:
    """Group mask islands into full-width vertical bands of fixed ``band_height``.

    Returns a list of ``(ymin, ymax)`` strips (each exactly ``band_height`` tall,
    clamped to the frame) covering every connected mask region. The neural
    backends crop these strips, resize to the model input, inpaint, and paste
    back — so the model only ever sees a tight band around the subtitle.

    A faithful port of upstream ``get_inpaint_area_by_mask`` (full-image width),
    returning only the y-range since x always spans the full width.
    """
    if not np.any(mask):
        return []

    binary = (mask > 0).astype(np.uint8) * 255
    num_labels, _labels, stats, centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)

    islands: list[tuple[int, int, int]] = []  # (top_y, bottom_y, center_y)
    for label in range(1, num_labels):
        if stats[label, cv2.CC_STAT_AREA] < 10:
            continue
        top = int(stats[label, cv2.CC_STAT_TOP])
        bottom = top + int(stats[label, cv2.CC_STAT_HEIGHT])
        islands.append((top, bottom, int(centroids[label][1])))
    if not islands:
        return []

    islands.sort(key=lambda item: item[2])

    # Greedily merge vertically-close islands whose combined height still fits a band.
    groups: list[list[tuple[int, int, int]]] = [[islands[0]]]
    for top, bottom, center in islands[1:]:
        group = groups[-1]
        group_min = min(item[0] for item in group)
        group_max = max(item[1] for item in group)
        connected = group_max >= top or np.any(binary[group_max:top, :] > 0)
        if (max(group_max, bottom) - min(group_min, top)) <= band_height and connected:
            group.append((top, bottom, center))
        else:
            groups.append([(top, bottom, center)])

    bands: list[tuple[int, int]] = []
    for group in groups:
        group_min = min(item[0] for item in group)
        group_max = max(item[1] for item in group)
        center = sum(item[2] for item in group) // len(group)
        ymin, ymax = _center_band(center, band_height, height)
        if ymin > group_min or ymax < group_max:
            ymin, ymax = _recenter_band(group_min, group_max, band_height, height)
        band = (int(ymin), int(ymax))
        if band not in bands:
            bands.append(band)
    return bands


def _center_band(center_y: int, band_height: int, frame_height: int) -> tuple[int, int]:
    ymin = max(0, center_y - band_height // 2)
    ymax = ymin + band_height
    if ymax > frame_height:
        ymax = frame_height
        ymin = max(0, frame_height - band_height)
    return ymin, ymax


def _recenter_band(group_min: int, group_max: int, band_height: int, frame_height: int) -> tuple[int, int]:
    if group_max - group_min <= band_height:
        ymin = group_min
    else:
        ymin = max(0, (group_min + group_max) // 2 - band_height // 2)
    ymax = ymin + band_height
    if ymax > frame_height:
        ymax = frame_height
        ymin = max(0, frame_height - band_height)
    return ymin, ymax


__all__ = ["create_mask", "get_inpaint_bands"]
