"""Optional visual scene context for translation prompts.

Reads the ``visual_context.json`` the visual-context node produced and matches
its units to translation ContextUnits by **time overlap** — never by unit
numbering, which is process-local on both sides (vision groups segments its own
way; task-c regroups them independently). Missing/corrupt files degrade to "no
context": translation must never fail because the vision stage did.
"""
from __future__ import annotations

import json
from pathlib import Path


def load_visual_units(path: Path | None) -> list[dict]:
    """Load scene units from visual_context.json; [] on any problem."""
    if path is None:
        return []
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    units = payload.get("units") if isinstance(payload, dict) else None
    if not isinstance(units, list):
        return []
    cleaned: list[dict] = []
    for raw in units:
        if not isinstance(raw, dict):
            continue
        scene = str(raw.get("scene") or "").strip()
        if not scene:
            continue  # parse-error units carry no usable description
        try:
            start = float(raw["start"])
            end = float(raw["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if end <= start:
            continue
        cleaned.append({"start": start, "end": end, "scene": scene})
    return cleaned


def _overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def best_visual_scene(start: float, end: float, visual_units: list[dict]) -> str | None:
    """Return the scene of the visual unit with the largest positive overlap."""
    best_scene: str | None = None
    best_overlap = 0.0
    for unit in visual_units:
        overlap = _overlap(start, end, unit["start"], unit["end"])
        if overlap > best_overlap:
            best_overlap = overlap
            best_scene = unit["scene"]
    return best_scene


__all__ = ["best_visual_scene", "load_visual_units"]
