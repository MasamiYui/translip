"""Box detection metrics: IoU matching → precision / recall / F1 (+ optional text).

Used by the OCR-detect scenario. Boxes are ``[x1, y1, x2, y2]`` in pixels (the
translip OCR ``box`` format). Matching is greedy by descending IoU at a fixed
threshold; an optional text comparison reports recognition accuracy among matched
boxes.
"""
from __future__ import annotations

from typing import Sequence


def box_iou(a: Sequence[float], b: Sequence[float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def match_boxes(
    pred: list[Sequence[float]],
    gt: list[Sequence[float]],
    *,
    iou_threshold: float = 0.5,
) -> dict:
    """Greedy IoU matching. Returns tp/fp/fn and the matched index pairs."""
    pairs: list[tuple[int, int, float]] = []
    for pi, pb in enumerate(pred):
        for gi, gb in enumerate(gt):
            iou = box_iou(pb, gb)
            if iou >= iou_threshold:
                pairs.append((pi, gi, iou))
    pairs.sort(key=lambda x: x[2], reverse=True)
    used_pred: set[int] = set()
    used_gt: set[int] = set()
    matches: list[tuple[int, int, float]] = []
    for pi, gi, iou in pairs:
        if pi in used_pred or gi in used_gt:
            continue
        used_pred.add(pi)
        used_gt.add(gi)
        matches.append((pi, gi, iou))
    tp = len(matches)
    return {
        "tp": tp,
        "fp": len(pred) - tp,
        "fn": len(gt) - tp,
        "matches": matches,
    }


def prf(tp: int, fp: int, fn: int) -> dict:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {"precision": precision, "recall": recall, "f1": f1, "tp": tp, "fp": fp, "fn": fn}
