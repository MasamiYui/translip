"""Load + interleave the two input artifacts into one grounded "story document".

The transcript (``segments.{lang}.json`` from the transcription tool) is the
*fact source*; the optional scene analysis (``visual_context.json`` from the
video-analyze scene-context task) is *auxiliary* — it helps the LLM when dialogue
is sparse but never overrides the subtitles. Both use a SECONDS float timeline, so
we render one time-ordered document the planning/writing stages can reason over.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Soft ceiling on the story document fed to a single LLM call. MVP is single-block
# (no map-reduce yet), so for a feature-length source we truncate and FLAG it
# rather than silently drop the tail — long-video map-reduce is a follow-up.
MAX_STORY_CHARS = 48_000


@dataclass(slots=True)
class StoryDocument:
    text: str
    duration_sec: float
    segment_count: int
    visual_unit_count: int
    truncated: bool


def _load_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_segments(path: Path) -> list[dict[str, Any]]:
    """Return the transcript segment list, tolerating either ``{segments:[...]}`` or a bare list."""
    payload = _load_json(path)
    if isinstance(payload, dict):
        segments = payload.get("segments")
    else:
        segments = payload
    return [seg for seg in segments if isinstance(seg, dict)] if isinstance(segments, list) else []


def load_visual_units(path: Path) -> list[dict[str, Any]]:
    """Return the scene-context unit list, tolerating ``{units:[...]}`` or a bare list."""
    payload = _load_json(path)
    if isinstance(payload, dict):
        units = payload.get("units")
    else:
        units = payload
    return [unit for unit in units if isinstance(unit, dict)] if isinstance(units, list) else []


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_story_document(
    segments: list[dict[str, Any]],
    visual_units: list[dict[str, Any]],
) -> StoryDocument:
    """Render the grounded, time-ordered story document fed to the LLM chain."""
    seg_sorted = sorted(segments, key=lambda s: _coerce_float(s.get("start")))
    duration = max((_coerce_float(s.get("end")) for s in seg_sorted), default=0.0)

    lines: list[str] = ["# 字幕时间轴（事实源，单位：秒，仅此为可信事实）"]
    for seg in seg_sorted:
        start = _coerce_float(seg.get("start"))
        end = _coerce_float(seg.get("end"))
        speaker = str(seg.get("speaker_label") or "").strip()
        text = str(seg.get("text") or "").strip()
        if not text:
            continue
        speaker_tag = f"（{speaker}）" if speaker else ""
        lines.append(f"[{start:.2f}-{end:.2f}]{speaker_tag} {text}")

    if visual_units:
        lines.append("")
        lines.append("# 画面场景（辅助理解，按时间；与字幕冲突时以字幕为准）")
        for unit in sorted(visual_units, key=lambda u: _coerce_float(u.get("start"))):
            start = _coerce_float(unit.get("start"))
            end = _coerce_float(unit.get("end"))
            parts: list[str] = []
            for label, key in (("场景", "scene"), ("设定", "setting"), ("氛围", "mood")):
                value = str(unit.get(key) or "").strip()
                if value:
                    parts.append(f"{label}:{value}")
            people = unit.get("people_visible")
            if isinstance(people, int):
                parts.append(f"人数:{people}")
            if parts:
                lines.append(f"[{start:.2f}-{end:.2f}] " + " | ".join(parts))

    text = "\n".join(lines)
    truncated = len(text) > MAX_STORY_CHARS
    if truncated:
        text = text[:MAX_STORY_CHARS] + "\n…（输入过长已截断；长视频 map-reduce 为后续增强）"

    return StoryDocument(
        text=text,
        duration_sec=round(duration, 3),
        segment_count=len(seg_sorted),
        visual_unit_count=len(visual_units),
        truncated=truncated,
    )
