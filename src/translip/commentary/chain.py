"""Orchestrate the 3-stage commentary-script chain: understand → plan → write.

MVP is single-block (no map-reduce) and ``plot_recap`` only. The planner owns the
timeline + OST assignment; the writer only fills narration text into the planned
``ost=0`` slots (locked structure, mirroring NarratoAI's split). We then merge the
two by id into the final OST-interleaved :class:`CommentaryScript`.
"""

from __future__ import annotations

from typing import Any, Callable

from ..config import DEFAULT_DEEPSEEK_MODEL
from . import llm, prompts
from .inputs import StoryDocument
from .types import CommentaryItem, CommentaryOptions, CommentaryScript

ProgressFn = Callable[[float, str | None], None]

# Items shorter than this (after clamping) are dropped — a degenerate window can't
# host a clip. Matches video-trim's VIDEO_TRIM_MIN_WINDOW_SEC.
_MIN_WINDOW_SEC = 0.1
# Spoken-narration pacing: ~5 Chinese chars per second of video (字数/5 ≈ 秒数).
_CHARS_PER_SEC = 5.0


def generate_commentary_script(
    *,
    story: StoryDocument,
    options: CommentaryOptions,
    on_progress: ProgressFn | None = None,
) -> CommentaryScript:
    if options.style != "plot_recap":
        raise ValueError(
            f"commentary_style={options.style!r} 暂未实现（MVP 仅支持 plot_recap）。"
        )
    progress = on_progress or (lambda _pct, _step=None: None)

    progress(15.0, "plot_analysis")
    plot = llm.call_text(**prompts.plot_analysis(story.text, options), model=options.model, temperature=0.3)

    progress(45.0, "segment_planning")
    plan_raw = llm.call_json(
        **prompts.segment_planning(story.text, plot, options), model=options.model, temperature=0.7
    )
    plan = _normalize_plan(plan_raw, max_end=story.duration_sec)
    if not plan:
        raise ValueError(
            "segment_planning 未产出任何可用片段。请检查字幕输入是否为空，或调整 original_sound_ratio。"
        )

    progress(75.0, "script_generation")
    items_raw = llm.call_json(
        **prompts.script_generation(story.text, plot, plan, options), model=options.model, temperature=1.0
    )
    narration_by_id = _index_narration(items_raw)

    items = _merge(plan, narration_by_id)
    return CommentaryScript(
        items=items,
        plot_analysis=plot,
        style=options.style,
        genre=options.genre,
        language=options.language,
        original_sound_ratio=options.original_sound_ratio,
        model=options.model or DEFAULT_DEEPSEEK_MODEL,
    )


def _coerce_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_plan(raw: dict[str, Any], *, max_end: float) -> list[dict[str, Any]]:
    """Validate/clamp the planner output into clean ordered segments.

    Keeps each segment's original ``id`` (the writer keys narration by it) but
    discards anything with an unparseable / degenerate / out-of-range window.
    """
    segments = raw.get("segments") if isinstance(raw, dict) else None
    if not isinstance(segments, list):
        return []
    cleaned: list[dict[str, Any]] = []
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        src = seg.get("src")
        if not (isinstance(src, (list, tuple)) and len(src) == 2):
            continue
        start = _coerce_float(src[0])
        end = _coerce_float(src[1])
        if start is None or end is None:
            continue
        start = max(0.0, start)
        if max_end and end > max_end:
            end = max_end
        if end - start < _MIN_WINDOW_SEC:
            continue
        ost = 1 if int(seg.get("ost", 0) or 0) == 1 else 0
        cleaned.append(
            {
                "id": seg.get("id"),
                "ost": ost,
                "start": start,
                "end": end,
                "story_role": str(seg.get("story_role") or ""),
            }
        )
    cleaned.sort(key=lambda item: item["start"])
    return cleaned


def _index_narration(raw: dict[str, Any]) -> dict[str, tuple[str, str]]:
    items = raw.get("items") if isinstance(raw, dict) else None
    mapping: dict[str, tuple[str, str]] = {}
    if not isinstance(items, list):
        return mapping
    for item in items:
        if not isinstance(item, dict) or "id" not in item:
            continue
        mapping[str(item["id"])] = (
            str(item.get("narration") or "").strip(),
            str(item.get("picture") or "").strip(),
        )
    return mapping


def _merge(
    plan: list[dict[str, Any]],
    narration_by_id: dict[str, tuple[str, str]],
) -> list[CommentaryItem]:
    items: list[CommentaryItem] = []
    for new_id, seg in enumerate(plan, start=1):
        narration, picture = narration_by_id.get(str(seg["id"]), ("", ""))
        if seg["ost"] == 1:
            # Original-sound passthrough: drop any narration the writer leaked in;
            # the clip plays with its own audio. Estimated runtime = clip length.
            narration = ""
            est = seg["end"] - seg["start"]
        else:
            est = round(len(narration) / _CHARS_PER_SEC, 2) if narration else 0.0
        items.append(
            CommentaryItem(
                id=new_id,
                ost=seg["ost"],
                src_start=seg["start"],
                src_end=seg["end"],
                narration=narration,
                picture=picture,
                story_role=seg["story_role"],
                est_duration_sec=est,
            )
        )
    return items
