from __future__ import annotations

from collections import defaultdict
from typing import Any

from ..translation.glossary import GlossaryEntry
from .reference_selection import build_reference_plan
from .rewrite import rewrite_for_dubbing


def build_repair_plan(
    *,
    translation_payload: dict[str, Any],
    profiles_payload: dict[str, Any],
    task_d_reports: list[dict[str, Any]],
    target_lang: str,
    glossary: list[GlossaryEntry],
    max_items: int | None = None,
) -> dict[str, Any]:
    translation_by_id = {
        str(row.get("segment_id")): row
        for row in translation_payload.get("segments", [])
        if isinstance(row, dict) and row.get("segment_id")
    }
    report_rows = _collect_report_rows(task_d_reports)
    items = [
        _repair_item(row=row, translation=translation_by_id.get(str(row.get("segment_id"))), report=report)
        for report, row in report_rows
    ]
    items = [item for item in items if item is not None]
    items.sort(
        key=lambda item: (
            0 if bool(item.get("strict_blocker")) else 1,
            -float(item["priority_score"]),
            item["segment_id"],
        )
    )
    if max_items is not None:
        items = items[:max(0, max_items)]

    rewrite_plan = _build_rewrite_plan(items=items, target_lang=target_lang, glossary=glossary)
    reference_plan = _build_reference_plans(
        items=items,
        profiles_payload=profiles_payload,
        reports=task_d_reports,
    )
    return {
        "target_lang": target_lang,
        "stats": _stats(items=items, task_d_reports=task_d_reports),
        "items": items,
        "rewrite_plan": rewrite_plan,
        "reference_plan": reference_plan,
    }


def _collect_report_rows(task_d_reports: list[dict[str, Any]]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    rows: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for report in task_d_reports:
        for row in report.get("segments", []):
            if isinstance(row, dict):
                rows.append((report, row))
    return rows


def _repair_item(
    *,
    row: dict[str, Any],
    translation: dict[str, Any] | None,
    report: dict[str, Any],
) -> dict[str, Any] | None:
    failure_reasons = _failure_reasons(row=row, translation=translation)
    if not failure_reasons:
        return None
    strict_blocker = _strict_blocker(failure_reasons)
    segment_id = str(row.get("segment_id") or "")
    source_duration_sec = float(row.get("source_duration_sec") or (translation or {}).get("duration") or 0.0)
    generated_duration_sec = float(row.get("generated_duration_sec") or 0.0)
    duration_ratio = float(row.get("duration_ratio") or 0.0)
    speaker_id = str(row.get("speaker_id") or (translation or {}).get("speaker_id") or report.get("speaker_id") or "")
    item = {
        "segment_id": segment_id,
        "speaker_id": speaker_id,
        "source_text": str((translation or {}).get("source_text") or ""),
        "target_text": str((translation or {}).get("target_text") or row.get("target_text") or ""),
        "anchor_start": _float_or_none((translation or {}).get("start")),
        "anchor_end": _float_or_none((translation or {}).get("end")),
        "source_duration_sec": round(source_duration_sec, 3),
        "generated_duration_sec": round(generated_duration_sec, 3),
        "audio_path": str(row.get("audio_path") or ""),
        "reference_path": str(row.get("reference_path") or report.get("reference", {}).get("path") or ""),
        "queue_class": "strict_blocker" if strict_blocker else "risk_only",
        "strict_blocker": strict_blocker,
        "failure_reasons": failure_reasons,
        "metrics": {
            "duration_ratio": round(duration_ratio, 3),
            "duration_status": str(row.get("duration_status") or ""),
            "speaker_similarity": row.get("speaker_similarity"),
            "speaker_status": str(row.get("speaker_status") or ""),
            "text_similarity": row.get("text_similarity"),
            "intelligibility_status": str(row.get("intelligibility_status") or ""),
            "overall_status": str(row.get("overall_status") or ""),
        },
        "suggested_actions": _suggested_actions(failure_reasons),
        "priority": _priority(failure_reasons, duration_ratio=duration_ratio),
        "priority_score": _priority_score(failure_reasons, duration_ratio=duration_ratio),
        "attempts": [],
        "selected_attempt_id": None,
    }
    return item


def _strict_blocker(failure_reasons: list[str]) -> bool:
    reasons = set(failure_reasons)
    return bool({"task_d_overall_failed", "missing_audio_path"} & reasons)


def _failure_reasons(*, row: dict[str, Any], translation: dict[str, Any] | None) -> list[str]:
    reasons: list[str] = []
    if str(row.get("overall_status") or "") == "failed":
        reasons.append("task_d_overall_failed")
    if str(row.get("duration_status") or "") == "failed":
        reasons.append("duration_failed")
    if str(row.get("speaker_status") or "") == "failed":
        reasons.append("speaker_failed")
    if str(row.get("intelligibility_status") or "") == "failed":
        reasons.append("intelligibility_failed")
    source_duration_sec = float(row.get("source_duration_sec") or (translation or {}).get("duration") or 0.0)
    if source_duration_sec < 1.2 or "too_short_source" in {str(flag) for flag in (translation or {}).get("qa_flags", [])}:
        reasons.append("too_short_source")
    duration_ratio = float(row.get("duration_ratio") or 0.0)
    if duration_ratio > 1.65:
        reasons.append("generated_too_long")
    elif 0.0 < duration_ratio < 0.55:
        reasons.append("generated_too_short")
    if not str(row.get("audio_path") or ""):
        reasons.append("missing_audio_path")
    return _dedupe(reasons)


def _suggested_actions(failure_reasons: list[str]) -> list[str]:
    reasons = set(failure_reasons)
    actions: list[str] = []
    if "too_short_source" in reasons and "duration_failed" in reasons:
        actions.append("merge_short_segments")
    if "duration_failed" in reasons or "intelligibility_failed" in reasons:
        actions.append("rewrite_for_dubbing")
        actions.append("regenerate_candidates")
    if "speaker_failed" in reasons:
        actions.append("switch_reference_audio")
    if {"duration_failed", "speaker_failed", "intelligibility_failed"}.issubset(reasons):
        actions.append("switch_tts_backend")
    if "missing_audio_path" in reasons:
        actions.append("manual_review")
    if not actions:
        actions.append("manual_review")
    return _dedupe(actions)


def _priority(failure_reasons: list[str], *, duration_ratio: float) -> str:
    score = _priority_score(failure_reasons, duration_ratio=duration_ratio)
    if score >= 5.0:
        return "high"
    if score >= 3.0:
        return "medium"
    return "low"


def _priority_score(failure_reasons: list[str], *, duration_ratio: float) -> float:
    reasons = set(failure_reasons)
    score = 0.0
    if "duration_failed" in reasons:
        score += 1.5
    if "speaker_failed" in reasons:
        score += 1.4
    if "intelligibility_failed" in reasons:
        score += 1.4
    if "too_short_source" in reasons:
        score += 0.7
    if duration_ratio >= 2.5 or (0.0 < duration_ratio <= 0.35):
        score += 1.4
    return round(score, 3)


def _build_rewrite_plan(
    *,
    items: list[dict[str, Any]],
    target_lang: str,
    glossary: list[GlossaryEntry],
) -> dict[str, Any]:
    rows = []
    for item in items:
        actions = set(item.get("suggested_actions", []))
        if not ({"rewrite_for_dubbing", "merge_short_segments"} & actions):
            continue
        candidates = rewrite_for_dubbing(
            segment_id=str(item["segment_id"]),
            source_text=str(item.get("source_text") or ""),
            current_target_text=str(item.get("target_text") or ""),
            source_duration_sec=float(item.get("source_duration_sec") or 0.0),
            target_lang=target_lang,
            glossary=glossary,
        )
        rows.append(
            {
                "segment_id": item["segment_id"],
                "speaker_id": item["speaker_id"],
                "source_text": item["source_text"],
                "current_target_text": item["target_text"],
                "rewrite_candidates": [candidate.to_payload() for candidate in candidates],
            }
        )
    return {"items": rows, "item_count": len(rows)}


def _build_reference_plans(
    *,
    items: list[dict[str, Any]],
    profiles_payload: dict[str, Any],
    reports: list[dict[str, Any]],
) -> dict[str, Any]:
    items_by_speaker: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        if "switch_reference_audio" in set(item.get("suggested_actions", [])):
            items_by_speaker[str(item.get("speaker_id") or "")].append(item)
    report_reference_by_speaker = {
        str(report.get("speaker_id") or ""): str(report.get("reference", {}).get("path") or "")
        for report in reports
        if isinstance(report, dict)
    }
    plans = [
        build_reference_plan(
            profiles_payload=profiles_payload,
            speaker_id=speaker_id,
            repair_items=speaker_items,
            current_reference_path=report_reference_by_speaker.get(speaker_id) or None,
        ).to_payload()
        for speaker_id, speaker_items in sorted(items_by_speaker.items())
        if speaker_id
    ]
    return {"speakers": plans, "speaker_count": len(plans)}


def _stats(*, items: list[dict[str, Any]], task_d_reports: list[dict[str, Any]]) -> dict[str, Any]:
    total_segments = sum(len(report.get("segments", [])) for report in task_d_reports)
    reason_counts: dict[str, int] = defaultdict(int)
    action_counts: dict[str, int] = defaultdict(int)
    priority_counts: dict[str, int] = defaultdict(int)
    queue_class_counts: dict[str, int] = defaultdict(int)
    for item in items:
        priority_counts[str(item.get("priority") or "")] += 1
        queue_class_counts[str(item.get("queue_class") or "")] += 1
        for reason in item.get("failure_reasons", []):
            reason_counts[str(reason)] += 1
        for action in item.get("suggested_actions", []):
            action_counts[str(action)] += 1
    strict_blocker_count = sum(1 for item in items if bool(item.get("strict_blocker")))
    return {
        "total_segments": total_segments,
        "repair_count": len(items),
        "strict_blocker_count": strict_blocker_count,
        "risk_only_count": len(items) - strict_blocker_count,
        "queue_class_counts": dict(sorted(queue_class_counts.items())),
        "reason_counts": dict(sorted(reason_counts.items())),
        "action_counts": dict(sorted(action_counts.items())),
        "priority_counts": dict(sorted(priority_counts.items())),
    }


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _dedupe(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


__all__ = ["build_repair_plan"]
