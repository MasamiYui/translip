from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from .diagnostics import load_json, now_iso, normalize_segments, write_json


def latest_decisions_by_item(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for raw in payload.get("decisions", []):
        if not isinstance(raw, dict):
            continue
        item_id = str(raw.get("item_id") or "")
        if item_id:
            rows[item_id] = raw
    return rows


def apply_speaker_decisions(
    segments_payload: dict[str, Any],
    decisions_payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    output = copy.deepcopy(segments_payload)
    raw_segments = output.get("segments", [])
    if not isinstance(raw_segments, list):
        raw_segments = []
        output["segments"] = raw_segments

    normalized = normalize_segments(output)
    index_by_id = {segment.segment_id: index for index, segment in enumerate(normalized)}
    raw_by_id: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(raw_segments, start=1):
        if not isinstance(raw, dict):
            continue
        segment_id = str(raw.get("id") or raw.get("segment_id") or f"seg-{index:04d}")
        raw_by_id[segment_id] = raw

    decisions = list(latest_decisions_by_item(decisions_payload).values())
    applied: list[dict[str, Any]] = []
    non_cloneable: set[str] = set()
    changed_segment_ids: set[str] = set()

    for decision in decisions:
        action = str(decision.get("decision") or "").strip()
        if not action:
            continue
        source_label = str(decision.get("source_speaker_label") or decision.get("speaker_label") or "")
        target_label = str(decision.get("target_speaker_label") or "")
        segment_ids = _decision_segment_ids(decision, raw_by_id=raw_by_id, source_label=source_label)

        if action in {"keep_independent", "keep"}:
            applied.append(_applied_row(decision, action=action, segment_ids=[]))
            continue

        if action in {"mark_non_cloneable", "non_cloneable"}:
            label = target_label or source_label or _speaker_from_item_id(str(decision.get("item_id") or ""))
            if label:
                non_cloneable.add(label)
            applied.append(_applied_row(decision, action="mark_non_cloneable", segment_ids=[]))
            continue

        if action in {"relabel_to_previous_speaker", "merge_to_previous_speaker"}:
            target_label = target_label or _neighbor_label(segment_ids, index_by_id=index_by_id, normalized=normalized, direction="previous")
        elif action in {"relabel_to_next_speaker", "merge_to_next_speaker"}:
            target_label = target_label or _neighbor_label(segment_ids, index_by_id=index_by_id, normalized=normalized, direction="next")
        elif action == "merge_to_surrounding_speaker":
            previous = _neighbor_label(segment_ids, index_by_id=index_by_id, normalized=normalized, direction="previous")
            next_label = _neighbor_label(segment_ids, index_by_id=index_by_id, normalized=normalized, direction="next")
            target_label = target_label or (previous if previous and previous == next_label else previous or next_label)

        if action in {"relabel", "merge_speaker", "relabel_to_previous_speaker", "merge_to_previous_speaker", "relabel_to_next_speaker", "merge_to_next_speaker", "merge_to_surrounding_speaker"}:
            if not target_label:
                applied.append(_applied_row(decision, action=action, segment_ids=[], skipped_reason="missing_target_speaker_label"))
                continue
            touched = _apply_label_change(
                raw_by_id=raw_by_id,
                segment_ids=segment_ids,
                target_label=target_label,
                decision=decision,
                action=action,
            )
            changed_segment_ids.update(touched)
            applied.append(_applied_row(decision, action=action, segment_ids=touched, target_speaker_label=target_label))
            continue

        applied.append(_applied_row(decision, action=action, segment_ids=[], skipped_reason="unsupported_decision"))

    review_meta = {
        "algorithm_version": "speaker-decision-apply-v1",
        "applied_at": now_iso(),
        "decision_count": len(decisions),
        "applied_decision_count": sum(1 for row in applied if not row.get("skipped_reason")),
        "changed_segment_count": len(changed_segment_ids),
        "non_cloneable_speakers": sorted(non_cloneable),
        "applied_decisions": applied,
    }
    output["speaker_review"] = review_meta
    output["segments"] = raw_segments
    return output, review_meta


def write_speaker_corrected_artifacts(
    *,
    source_segments_path: Path,
    decisions_path: Path,
    output_segments_path: Path,
    output_srt_path: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    source_payload = load_json(source_segments_path)
    decisions_payload = load_json(decisions_path) if decisions_path.exists() else {}
    corrected_payload, review_meta = apply_speaker_decisions(source_payload, decisions_payload)
    write_json(corrected_payload, output_segments_path)
    write_srt(corrected_payload, output_srt_path)
    manifest = {
        "version": 1,
        "algorithm_version": "speaker-review-apply-v1",
        "generated_at": now_iso(),
        "input_segments": str(source_segments_path),
        "manual_decisions": str(decisions_path),
        "output_segments": str(output_segments_path),
        "output_srt": str(output_srt_path),
        "summary": {
            "decision_count": review_meta["decision_count"],
            "applied_decision_count": review_meta["applied_decision_count"],
            "changed_segment_count": review_meta["changed_segment_count"],
            "non_cloneable_speaker_count": len(review_meta["non_cloneable_speakers"]),
        },
        "non_cloneable_speakers": review_meta["non_cloneable_speakers"],
    }
    write_json(manifest, manifest_path)
    return manifest


def write_srt(segments_payload: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for index, raw in enumerate(segments_payload.get("segments", []), start=1):
        if not isinstance(raw, dict):
            continue
        start = float(raw.get("start") or 0.0)
        end = float(raw.get("end") or 0.0)
        speaker_label = str(raw.get("speaker_label") or "UNKNOWN")
        text = str(raw.get("text") or raw.get("source_text") or "")
        lines.extend(
            [
                str(index),
                f"{_srt_timestamp(start)} --> {_srt_timestamp(end)}",
                f"[{speaker_label}] {text}",
                "",
            ]
        )
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def _decision_segment_ids(
    decision: dict[str, Any],
    *,
    raw_by_id: dict[str, dict[str, Any]],
    source_label: str,
) -> list[str]:
    payload = decision.get("payload") if isinstance(decision.get("payload"), dict) else {}
    raw_ids = decision.get("segment_ids") or payload.get("segment_ids")
    if isinstance(raw_ids, list):
        return [str(item) for item in raw_ids if str(item)]
    item_type = str(decision.get("item_type") or "")
    item_id = str(decision.get("item_id") or "")
    if item_type == "segment" or item_id.startswith("segment:"):
        segment_id = item_id.split(":", 1)[1] if item_id.startswith("segment:") else item_id
        return [segment_id] if segment_id else []
    if source_label:
        return [
            segment_id
            for segment_id, raw in raw_by_id.items()
            if str(raw.get("speaker_label") or "") == source_label
        ]
    return []


def _apply_label_change(
    *,
    raw_by_id: dict[str, dict[str, Any]],
    segment_ids: list[str],
    target_label: str,
    decision: dict[str, Any],
    action: str,
) -> list[str]:
    touched: list[str] = []
    for segment_id in segment_ids:
        raw = raw_by_id.get(segment_id)
        if raw is None:
            continue
        previous_label = str(raw.get("speaker_label") or "")
        if previous_label == target_label:
            continue
        raw.setdefault("original_speaker_label", previous_label)
        raw["speaker_label"] = target_label
        raw["speaker_correction"] = {
            "source": "manual_speaker_decision",
            "decision": action,
            "item_id": decision.get("item_id"),
            "previous_speaker_label": previous_label,
            "target_speaker_label": target_label,
            "updated_at": decision.get("updated_at") or now_iso(),
        }
        touched.append(segment_id)
    return touched


def _neighbor_label(
    segment_ids: list[str],
    *,
    index_by_id: dict[str, int],
    normalized: list[Any],
    direction: str,
) -> str | None:
    if not segment_ids:
        return None
    indexes = sorted(index_by_id[segment_id] for segment_id in segment_ids if segment_id in index_by_id)
    if not indexes:
        return None
    target_index = indexes[0] - 1 if direction == "previous" else indexes[-1] + 1
    if target_index < 0 or target_index >= len(normalized):
        return None
    return str(normalized[target_index].speaker_label)


def _speaker_from_item_id(item_id: str) -> str:
    if item_id.startswith("speaker:"):
        return item_id.split(":", 1)[1]
    return item_id


def _applied_row(
    decision: dict[str, Any],
    *,
    action: str,
    segment_ids: list[str],
    target_speaker_label: str | None = None,
    skipped_reason: str | None = None,
) -> dict[str, Any]:
    row = {
        "item_id": decision.get("item_id"),
        "item_type": decision.get("item_type"),
        "decision": action,
        "source_speaker_label": decision.get("source_speaker_label"),
        "target_speaker_label": target_speaker_label or decision.get("target_speaker_label"),
        "segment_ids": segment_ids,
    }
    if skipped_reason:
        row["skipped_reason"] = skipped_reason
    return row


def _srt_timestamp(seconds: float) -> str:
    millis = int(round(seconds * 1000))
    hours, remainder = divmod(millis, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, ms = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"
