"""Lightweight textness prefilter used before OCR."""

from __future__ import annotations

from typing import Dict, Tuple

import cv2
import numpy as np

from translip.ocr.config import settings


def _resize_for_analysis(image: np.ndarray, max_width: int = 320) -> np.ndarray:
    h, w = image.shape[:2]
    if w <= max_width:
        return image
    scale = max_width / max(w, 1)
    new_h = max(1, int(round(h * scale)))
    return cv2.resize(image, (max_width, new_h), interpolation=cv2.INTER_AREA)


def analyze_textness(image: np.ndarray) -> Dict[str, float]:
    if image is None or image.size == 0:
        return {
            "stddev": 0.0,
            "edge_density": 0.0,
            "hat_density": 0.0,
            "score": 0.0,
        }

    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image

    sample = _resize_for_analysis(gray)
    stddev = float(np.std(sample))

    edges = cv2.Canny(sample, 80, 180)
    edge_density = float(np.mean(edges > 0))

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 3))
    top_hat = cv2.morphologyEx(sample, cv2.MORPH_TOPHAT, kernel)
    black_hat = cv2.morphologyEx(sample, cv2.MORPH_BLACKHAT, kernel)
    hat_density = float(max(np.mean(top_hat > 20), np.mean(black_hat > 20)))

    score = (
        0.45 * min(1.0, stddev / 64.0) +
        0.35 * min(1.0, edge_density / 0.025) +
        0.20 * min(1.0, hat_density / 0.05)
    )

    return {
        "stddev": round(stddev, 4),
        "edge_density": round(edge_density, 6),
        "hat_density": round(hat_density, 6),
        "score": round(float(score), 6),
    }


def should_run_ocr(
    image: np.ndarray,
    enabled: bool | None = None,
) -> Tuple[bool, Dict[str, float | bool | str]]:
    metrics = analyze_textness(image)
    prefilter_enabled = settings.SUBTITLE_PREFILTER_ENABLED if enabled is None else bool(enabled)
    if not prefilter_enabled:
        return True, {**metrics, "enabled": False, "passed": True, "reason": "disabled"}

    stddev = float(metrics["stddev"])
    edge_density = float(metrics["edge_density"])
    hat_density = float(metrics["hat_density"])
    score = float(metrics["score"])

    passed = (
        stddev >= settings.SUBTITLE_PREFILTER_MIN_STDDEV and
        (
            edge_density >= settings.SUBTITLE_PREFILTER_MIN_EDGE_DENSITY or
            hat_density >= settings.SUBTITLE_PREFILTER_MIN_HAT_DENSITY or
            score >= settings.SUBTITLE_PREFILTER_MIN_SCORE
        )
    )
    reason = "passed" if passed else "low_textness"
    return passed, {**metrics, "enabled": True, "passed": passed, "reason": reason}
