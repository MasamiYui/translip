"""Geometry helpers for subtitle boxes, polygons, and rotated boxes."""

from __future__ import annotations

from typing import Iterable, List, Optional, Sequence, Tuple

import cv2
import numpy as np

Point = Tuple[float, float]
AxisBox = Tuple[int, int, int, int]


def normalize_polygon(poly) -> Optional[List[Point]]:
    """Normalize detector output into a list of (x, y) points."""
    if poly is None:
        return None

    try:
        arr = np.asarray(poly, dtype=float)
    except (TypeError, ValueError):
        return None

    if arr.size == 0:
        return None

    if arr.ndim == 1 and arr.size == 4:
        x1, y1, x2, y2 = arr.tolist()
        return [
            (float(x1), float(y1)),
            (float(x2), float(y1)),
            (float(x2), float(y2)),
            (float(x1), float(y2)),
        ]

    if arr.ndim == 1 and arr.size % 2 == 0:
        arr = arr.reshape(-1, 2)

    if arr.ndim != 2 or arr.shape[1] != 2 or arr.shape[0] < 2:
        return None

    return [(float(x), float(y)) for x, y in arr]


def polygon_to_box(polygon: Optional[Sequence[Point]]) -> Optional[Tuple[float, float, float, float]]:
    if not polygon:
        return None

    arr = np.asarray(polygon, dtype=float)
    if arr.ndim != 2 or arr.shape[1] != 2:
        return None

    x_coords = arr[:, 0]
    y_coords = arr[:, 1]
    return (
        float(np.min(x_coords)),
        float(np.min(y_coords)),
        float(np.max(x_coords)),
        float(np.max(y_coords)),
    )


def float_box_to_int(box: Optional[Tuple[float, float, float, float]]) -> Optional[AxisBox]:
    if not box:
        return None
    x1, y1, x2, y2 = box
    return (
        int(round(x1)),
        int(round(y1)),
        max(int(round(x1)) + 1, int(round(x2))),
        max(int(round(y1)) + 1, int(round(y2))),
    )


def box_to_polygon(box: Optional[AxisBox]) -> Optional[List[Point]]:
    if not box:
        return None
    x1, y1, x2, y2 = box
    return [
        (float(x1), float(y1)),
        (float(x2), float(y1)),
        (float(x2), float(y2)),
        (float(x1), float(y2)),
    ]


def polygon_to_rotated_box(polygon: Optional[Sequence[Point]]) -> Optional[dict]:
    if not polygon:
        return None

    arr = np.asarray(polygon, dtype=np.float32)
    if arr.ndim != 2 or arr.shape[1] != 2 or arr.shape[0] < 2:
        return None

    rect = cv2.minAreaRect(arr)
    box_points = cv2.boxPoints(rect)
    axis_box = float_box_to_int(polygon_to_box(box_points.tolist()))
    center = rect[0]
    size = rect[1]
    angle = rect[2]

    return {
        "center": (float(center[0]), float(center[1])),
        "size": (float(size[0]), float(size[1])),
        "angle": float(angle),
        "points": [(float(x), float(y)) for x, y in box_points],
        "box": axis_box,
    }


def shift_polygon(polygon: Optional[Sequence[Point]], dx: float, dy: float) -> Optional[List[Point]]:
    if not polygon:
        return None
    return [(float(x + dx), float(y + dy)) for x, y in polygon]


def shift_rotated_box(rotated_box: Optional[dict], dx: float, dy: float) -> Optional[dict]:
    if not rotated_box:
        return None

    center = rotated_box.get("center") or (0.0, 0.0)
    shifted = {
        **rotated_box,
        "center": (float(center[0] + dx), float(center[1] + dy)),
        "points": shift_polygon(rotated_box.get("points"), dx, dy),
    }
    box = rotated_box.get("box")
    if box:
        x1, y1, x2, y2 = box
        shifted["box"] = (
            int(round(x1 + dx)),
            int(round(y1 + dy)),
            int(round(x2 + dx)),
            int(round(y2 + dy)),
        )
    return shifted


def build_geometry_from_polygon(polygon) -> Tuple[Optional[AxisBox], Optional[List[Point]], Optional[dict]]:
    normalized = normalize_polygon(polygon)
    if not normalized:
        return None, None, None
    box = float_box_to_int(polygon_to_box(normalized))
    rotated_box = polygon_to_rotated_box(normalized)
    return box, normalized, rotated_box


def representative_polygon(polygons: Sequence[Optional[Sequence[Point]]], target_box: Optional[AxisBox] = None) -> Optional[List[Point]]:
    normalized = []
    for poly in polygons:
        polygon = normalize_polygon(poly)
        if polygon:
            normalized.append(polygon)
    if not normalized:
        return None
    if len(normalized) == 1:
        return normalized[0]

    if target_box:
        tx1, ty1, tx2, ty2 = target_box
        target = np.array([(tx1 + tx2) / 2.0, (ty1 + ty2) / 2.0], dtype=np.float64)
        scored = []
        for polygon in normalized:
            arr = np.asarray(polygon, dtype=np.float64)
            center = np.mean(arr, axis=0)
            scored.append((float(np.sum(np.abs(center - target))), polygon))
        scored.sort(key=lambda item: item[0])
        return scored[0][1]

    return normalized[0]


def median_polygon(polygons: Sequence[Optional[Sequence[Point]]]) -> Optional[List[Point]]:
    normalized = []
    for poly in polygons:
        polygon = normalize_polygon(poly)
        if polygon:
            normalized.append(polygon)
    if not normalized:
        return None

    point_count = len(normalized[0])
    if point_count < 3:
        return normalized[0]

    for polygon in normalized[1:]:
        if len(polygon) != point_count:
            return None

    arr = np.asarray(normalized, dtype=np.float64)
    med = np.median(arr, axis=0)
    return [(float(x), float(y)) for x, y in med]


def merge_polygons(polygons: Sequence[Optional[Sequence[Point]]], target_box: Optional[AxisBox] = None) -> Optional[List[Point]]:
    polygon = median_polygon(polygons)
    if polygon:
        return polygon
    return representative_polygon(polygons, target_box=target_box)


def polygon_from_points(points: Iterable[Point]) -> Optional[List[Point]]:
    arr = np.asarray(list(points), dtype=np.float32)
    if arr.size == 0 or arr.ndim != 2 or arr.shape[1] != 2:
        return None
    if arr.shape[0] < 3:
        return [(float(x), float(y)) for x, y in arr]
    hull = cv2.convexHull(arr).reshape(-1, 2)
    return [(float(x), float(y)) for x, y in hull]


def order_quad_points(points: Sequence[Point]) -> Optional[np.ndarray]:
    arr = np.asarray(points, dtype=np.float32)
    if arr.shape != (4, 2):
        return None
    ordered = np.zeros((4, 2), dtype=np.float32)
    sums = arr.sum(axis=1)
    diffs = np.diff(arr, axis=1)
    ordered[0] = arr[np.argmin(sums)]  # top-left
    ordered[2] = arr[np.argmax(sums)]  # bottom-right
    ordered[1] = arr[np.argmin(diffs)]  # top-right
    ordered[3] = arr[np.argmax(diffs)]  # bottom-left
    return ordered


def crop_axis_aligned(image: np.ndarray, box: Optional[AxisBox]) -> Optional[np.ndarray]:
    if image is None or image.size == 0 or not box:
        return None
    h, w = image.shape[:2]
    x1, y1, x2, y2 = box
    x1 = max(0, min(w - 1, int(round(x1))))
    y1 = max(0, min(h - 1, int(round(y1))))
    x2 = max(x1 + 1, min(w, int(round(x2))))
    y2 = max(y1 + 1, min(h, int(round(y2))))
    crop = image[y1:y2, x1:x2]
    return crop if crop.size else None


def crop_rotated_box(image: np.ndarray, rotated_box: Optional[dict]) -> Optional[np.ndarray]:
    if image is None or image.size == 0 or not rotated_box:
        return None
    points = rotated_box.get("points")
    ordered = order_quad_points(points or [])
    if ordered is None:
        return crop_axis_aligned(image, rotated_box.get("box"))

    width_a = np.linalg.norm(ordered[2] - ordered[3])
    width_b = np.linalg.norm(ordered[1] - ordered[0])
    height_a = np.linalg.norm(ordered[1] - ordered[2])
    height_b = np.linalg.norm(ordered[0] - ordered[3])
    width = max(1, int(round(max(width_a, width_b))))
    height = max(1, int(round(max(height_a, height_b))))

    dst = np.array([
        [0, 0],
        [width - 1, 0],
        [width - 1, height - 1],
        [0, height - 1],
    ], dtype=np.float32)
    matrix = cv2.getPerspectiveTransform(ordered, dst)
    return cv2.warpPerspective(
        image,
        matrix,
        (width, height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )


def crop_polygon(image: np.ndarray, polygon: Optional[Sequence[Point]]) -> Optional[np.ndarray]:
    normalized = normalize_polygon(polygon)
    if image is None or image.size == 0 or not normalized:
        return None

    if len(normalized) == 4:
        rotated = polygon_to_rotated_box(normalized)
        crop = crop_rotated_box(image, rotated)
        if crop is not None and crop.size:
            return crop

    arr = np.asarray(normalized, dtype=np.int32)
    x, y, w, h = cv2.boundingRect(arr)
    crop = image[y:y + h, x:x + w]
    if crop.size == 0:
        return None

    shifted = arr - np.array([[x, y]], dtype=np.int32)
    mask = np.zeros((h, w), dtype=np.uint8)
    cv2.fillPoly(mask, [shifted], 255)
    if len(crop.shape) == 2:
        output = np.full_like(crop, 255)
        output[mask > 0] = crop[mask > 0]
        return output

    output = np.full_like(crop, 255)
    output[mask > 0] = crop[mask > 0]
    return output


def crop_by_geometry(
    image: np.ndarray,
    geometry_mode: str,
    box: Optional[AxisBox] = None,
    polygon: Optional[Sequence[Point]] = None,
    rotated_box: Optional[dict] = None,
) -> Optional[np.ndarray]:
    mode = (geometry_mode or "axis_aligned").lower()
    if mode == "rotated_box":
        crop = crop_rotated_box(image, rotated_box)
        if crop is not None and crop.size:
            return crop
        return crop_axis_aligned(image, box)
    if mode == "polygon":
        crop = crop_polygon(image, polygon)
        if crop is not None and crop.size:
            return crop
        return crop_axis_aligned(image, box)
    return crop_axis_aligned(image, box)
