"""Turn an OCR ``detection.json`` into a per-frame mask plan.

Bridges translip's OCR detection contract (events with ``box: [x1, y1, x2, y2]``
and inclusive 0-indexed ``start_frame``/``end_frame``) to the mask coordinate
convention used by :mod:`translip.erase.core.masks` (``(xmin, xmax, ymin, ymax)``)
and groups frames into the contiguous, same-mask ranges the inpainters consume.

Range grouping + merge logic is ported from video-subtitle-remover
(``find_continuous_ranges_with_same_mask`` / ``filter_and_merge_intervals``).
"""
from __future__ import annotations

from typing import Any

# A subtitle box in mask coordinates: (xmin, xmax, ymin, ymax).
Box = tuple[int, int, int, int]
# Maps a frame index -> the sorted, de-duplicated boxes active on that frame.
FrameBoxes = dict[int, list[Box]]


def subtitle_frames(events: list[dict[str, Any]], *, yx_diff_px: int = 10) -> FrameBoxes:
    """Expand detection events into a ``frame -> [box, ...]`` dict.

    Drops tall-thin boxes (``(ymax-ymin) - (xmax-xmin) > yx_diff_px``) which are
    almost always vertical UI elements rather than horizontal subtitle lines.
    """
    frames: FrameBoxes = {}
    for event in events:
        box = _event_box(event)
        if box is None:
            continue
        xmin, xmax, ymin, ymax = box
        if (ymax - ymin) - (xmax - xmin) > yx_diff_px:
            continue
        start = _as_int(event.get("start_frame"))
        end = _as_int(event.get("end_frame"))
        if start is None or end is None:
            continue
        for frame_no in range(start, max(start, end) + 1):
            bucket = frames.setdefault(frame_no, [])
            if box not in bucket:
                bucket.append(box)
    return frames


def regions_to_frames(
    regions: list[tuple[float, float, float, float]],
    *,
    width: int,
    height: int,
    total_frames: int,
) -> FrameBoxes:
    """Build a static per-frame plan from normalized ``(x1, y1, x2, y2)`` regions.

    Used for manual erase: the regions are applied to every frame of the video.
    """
    boxes: list[Box] = []
    for x1, y1, x2, y2 in regions:
        box = (
            int(round(min(x1, x2) * width)),
            int(round(max(x1, x2) * width)),
            int(round(min(y1, y2) * height)),
            int(round(max(y1, y2) * height)),
        )
        if box[1] > box[0] and box[3] > box[2]:
            boxes.append(box)
    if not boxes:
        return {}
    return {frame_no: list(boxes) for frame_no in range(max(0, total_frames))}


def plan_ranges(frames: FrameBoxes, *, total_frames: int, reference_length: int) -> list[tuple[int, int]]:
    """Group frames into contiguous, same-mask ranges merged to >= reference_length.

    Returns inclusive ``(start, end)`` frame ranges (0-indexed) clamped to the
    video length so the reader loop can never run past the last frame.
    """
    if not frames:
        return []
    ranges = _continuous_ranges_same_mask(frames)
    ranges = _filter_and_merge_intervals(ranges, reference_length)
    last = total_frames - 1 if total_frames > 0 else None
    clamped: list[tuple[int, int]] = []
    for start, end in ranges:
        end = end if last is None else min(end, last)
        if end >= start:
            clamped.append((start, end))
    return clamped


def boxes_for_range(frames: FrameBoxes, start: int, end: int, *, yx_diff_px: int = 10) -> list[Box]:
    """Union of all boxes active anywhere in ``[start, end]`` (inclusive)."""
    union: list[Box] = []
    for frame_no in range(start, end + 1):
        for box in frames.get(frame_no, ()):
            xmin, xmax, ymin, ymax = box
            if (ymax - ymin) - (xmax - xmin) > yx_diff_px:
                continue
            if box not in union:
                union.append(box)
    return union


def _event_box(event: dict[str, Any]) -> Box | None:
    raw = event.get("box") or event.get("bbox") or event.get("region_box")
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        return None
    x1, y1, x2, y2 = (_as_int(raw[0]), _as_int(raw[1]), _as_int(raw[2]), _as_int(raw[3]))
    if None in (x1, y1, x2, y2):
        return None
    xmin, xmax = sorted((x1, x2))  # type: ignore[type-var]
    ymin, ymax = sorted((y1, y2))  # type: ignore[type-var]
    if xmax <= xmin or ymax <= ymin:
        return None
    return (xmin, xmax, ymin, ymax)


def _continuous_ranges_same_mask(frames: FrameBoxes) -> list[tuple[int, int]]:
    numbers = sorted(frames.keys())
    ranges: list[tuple[int, int]] = []
    start = numbers[0]
    for i in range(1, len(numbers)):
        gap = numbers[i] - numbers[i - 1] != 1
        changed = frames[numbers[i]] != frames[numbers[i - 1]]
        if gap or changed:
            ranges.append((start, numbers[i - 1]))
            start = numbers[i]
    ranges.append((start, numbers[-1]))
    return ranges


def _filter_and_merge_intervals(intervals: list[tuple[int, int]], target_length: int) -> list[tuple[int, int]]:
    """Expand single-frame intervals toward ``target_length`` and merge short
    adjacent/overlapping ones, so each range gives the temporal model enough
    context. Faithful O(n log n) port of upstream ``filter_and_merge_intervals``.
    """
    if not intervals:
        return []
    intervals = sorted(intervals, key=lambda item: item[0])
    expanded: list[tuple[int, int]] = []
    for i, (start, end) in enumerate(intervals):
        if start == end:
            prev_end = expanded[-1][1] if expanded else float("-inf")
            next_start = intervals[i + 1][0] if i + 1 < len(intervals) else float("inf")
            half = (target_length - 1) // 2
            new_start = max(start - half, prev_end + 1)
            new_end = min(start + half, next_start - 1)
            if new_end < new_start:
                new_start, new_end = start, start
            expanded.append((int(new_start), int(new_end)))
        else:
            expanded.append((start, end))
    merged: list[tuple[int, int]] = [expanded[0]]
    for start, end in expanded[1:]:
        last_start, last_end = merged[-1]
        last_len = last_end - last_start + 1
        cur_len = end - start + 1
        if start <= last_end + 1 and (cur_len < target_length or last_len < target_length):
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def _as_int(value: Any) -> int | None:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


__all__ = [
    "Box",
    "FrameBoxes",
    "subtitle_frames",
    "regions_to_frames",
    "plan_ranges",
    "boxes_for_range",
]
