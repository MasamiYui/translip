from __future__ import annotations

from collections import defaultdict
from typing import Any

from .reference import select_reference_candidates


def pick_task_d_speaker_ids(
    *,
    profiles_payload: dict[str, Any],
    translation_payload: dict[str, Any],
    limit: int = 1,
) -> list[str]:
    profiles = [profile for profile in profiles_payload.get("profiles", []) if isinstance(profile, dict)]
    if not profiles:
        return []

    usable_counts: dict[str, int] = defaultdict(int)
    short_counts: dict[str, int] = defaultdict(int)

    for row in translation_payload.get("segments", []):
        if not isinstance(row, dict):
            continue
        speaker_id = str(row.get("speaker_id") or "")
        duration_sec = float(row.get("duration") or 0.0)
        flags = {str(flag) for flag in row.get("qa_flags", [])}
        if is_usable_task_d_segment(duration_sec=duration_sec, qa_flags=flags):
            usable_counts[speaker_id] += 1
        if 1.0 <= duration_sec <= 4.0 and "too_short_source" not in flags:
            short_counts[speaker_id] += 1

    ranked: list[tuple[int, int, float, float, str]] = []
    for profile in profiles:
        speaker_id = str(profile.get("speaker_id") or "")
        if not speaker_id or usable_counts.get(speaker_id, 0) <= 0:
            continue
        try:
            top_reference = select_reference_candidates(
                profiles_payload=profiles_payload,
                speaker_id=speaker_id,
            )[0]
        except ValueError:
            continue
        ranked.append(
            (
                usable_counts.get(speaker_id, 0),
                short_counts.get(speaker_id, 0),
                float(top_reference.score),
                float(profile.get("total_speech_sec") or 0.0),
                speaker_id,
            )
        )
    ranked.sort(reverse=True)
    return [row[-1] for row in ranked[: max(limit, 0)]]


def pick_segment_ids_for_speaker(
    *,
    translation_payload: dict[str, Any],
    speaker_id: str,
    limit: int | None,
) -> list[str] | None:
    if limit is None:
        return None

    rows = [
        row
        for row in translation_payload.get("segments", [])
        if isinstance(row, dict) and str(row.get("speaker_id")) == speaker_id
    ]
    rows = sorted(rows, key=lambda row: (float(row.get("start") or 0.0), str(row.get("segment_id") or "")))
    preferred = [
        row
        for row in rows
        if is_preferred_task_d_segment(
            duration_sec=float(row.get("duration") or 0.0),
            qa_flags={str(flag) for flag in row.get("qa_flags", [])},
        )
    ]
    fallback = [
        row
        for row in rows
        if is_usable_task_d_segment(
            duration_sec=float(row.get("duration") or 0.0),
            qa_flags={str(flag) for flag in row.get("qa_flags", [])},
        )
    ]
    selected: list[str] = []
    for pool in (preferred, fallback, rows):
        for row in pool:
            segment_id = str(row.get("segment_id") or "")
            if not segment_id or segment_id in selected:
                continue
            selected.append(segment_id)
            if len(selected) >= limit:
                return selected
    return selected or None


def is_usable_task_d_segment(*, duration_sec: float, qa_flags: set[str]) -> bool:
    if duration_sec < 1.0 or duration_sec > 6.0:
        return False
    if "too_short_source" in qa_flags:
        return False
    return True


def is_preferred_task_d_segment(*, duration_sec: float, qa_flags: set[str]) -> bool:
    if not is_usable_task_d_segment(duration_sec=duration_sec, qa_flags=qa_flags):
        return False
    if "duration_risky" in qa_flags:
        return False
    return 1.5 <= duration_sec <= 4.5


__all__ = [
    "is_preferred_task_d_segment",
    "is_usable_task_d_segment",
    "pick_segment_ids_for_speaker",
    "pick_task_d_speaker_ids",
]
