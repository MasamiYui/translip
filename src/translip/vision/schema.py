"""Tolerant parsing of model output into per-task payloads.

Models are prompted to emit bare JSON but routinely wrap it in code fences or
prose. ``extract_json`` digs the first JSON value out of arbitrary text; the
``parse_*`` helpers then coerce fields defensively. A unit whose output cannot
be parsed degrades to ``{"error": ..., "raw": ...}`` instead of failing the
whole run (the service layer relies on this).
"""
from __future__ import annotations

import json
import re
from typing import Any

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)

# Soft confidence floor applied when the model omits/garbles the field.
_DEFAULT_CONFIDENCE = 0.5


def extract_json(text: str) -> Any:
    """Extract the first JSON object/array from possibly chatty model output.

    Raises ``ValueError`` when no parseable JSON is present.
    """
    candidates: list[str] = []
    stripped = text.strip()
    if stripped:
        candidates.append(stripped)
    candidates.extend(match.group(1).strip() for match in _FENCE_RE.finditer(text))
    # Last resort: first {...} or [...] span (greedy to the matching tail).
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end > start:
            candidates.append(text[start : end + 1])
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
    raise ValueError("model output contains no parseable JSON")


def _coerce_int(value: Any, default: int | None = None) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return _DEFAULT_CONFIDENCE
    return max(0.0, min(1.0, confidence))


def _coerce_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_scene_context(text: str) -> dict[str, Any]:
    data = extract_json(text)
    if not isinstance(data, dict):
        raise ValueError("scene-context output is not a JSON object")
    return {
        "scene": _coerce_str(data.get("scene")) or "",
        "people_visible": _coerce_int(data.get("people_visible")),
        "setting": _coerce_str(data.get("setting")),
        "mood": _coerce_str(data.get("mood")),
        "confidence": _coerce_confidence(data.get("confidence")),
    }


def parse_erase_qc(text: str) -> dict[str, Any]:
    data = extract_json(text)
    if not isinstance(data, dict):
        raise ValueError("erase-qc output is not a JSON object")
    return {
        "residual_text": bool(data.get("residual_text")),
        "artifact": _coerce_str(data.get("artifact")),
        "note": _coerce_str(data.get("note")),
        "confidence": _coerce_confidence(data.get("confidence")),
    }


_OCR_KINDS = ("subtitle", "scene_text", "watermark", "title_card")


def parse_ocr_classify(text: str) -> dict[str, Any]:
    data = extract_json(text)
    # Some models answer with a one-element array even for one event.
    if isinstance(data, list):
        data = next((item for item in data if isinstance(item, dict)), None)
    if not isinstance(data, dict):
        raise ValueError("ocr-classify output is not a JSON object")
    kind = _coerce_str(data.get("kind"))
    if kind not in _OCR_KINDS:
        raise ValueError(f"ocr-classify kind not recognized: {kind!r}")
    return {"kind": kind, "confidence": _coerce_confidence(data.get("confidence"))}


def parse_speaker_visual(text: str) -> dict[str, Any]:
    data = extract_json(text)
    if not isinstance(data, dict):
        raise ValueError("speaker-visual output is not a JSON object")
    speaking_face = data.get("speaking_face")
    return {
        "people_visible": _coerce_int(data.get("people_visible")),
        "speaking_face": bool(speaking_face) if speaking_face is not None else None,
        "speaker_hint": _coerce_str(data.get("speaker_hint")),
        "confidence": _coerce_confidence(data.get("confidence")),
    }


def parse_freeform(text: str) -> dict[str, Any]:
    try:
        data = extract_json(text)
    except ValueError:
        # Freeform answers are for humans; plain text is acceptable output.
        return {"answer": text.strip(), "confidence": _DEFAULT_CONFIDENCE}
    if isinstance(data, dict) and "answer" in data:
        return {
            "answer": _coerce_str(data.get("answer")) or "",
            "confidence": _coerce_confidence(data.get("confidence")),
        }
    return {"answer": text.strip(), "confidence": _DEFAULT_CONFIDENCE}


PARSERS = {
    "scene-context": parse_scene_context,
    "erase-qc": parse_erase_qc,
    "ocr-classify": parse_ocr_classify,
    "speaker-visual": parse_speaker_visual,
    "freeform": parse_freeform,
}


def parse_unit_output(task: str, text: str) -> dict[str, Any]:
    """Parse one unit's model output; degrade to an error payload, never raise."""
    parser = PARSERS.get(task)
    if parser is None:
        raise ValueError(f"Unsupported vision task: {task}")
    try:
        return parser(text)
    except ValueError as exc:
        return {"error": str(exc), "raw": text.strip()[:500]}


__all__ = ["PARSERS", "extract_json", "parse_unit_output"]
