from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import json

SHORT_SEGMENT_SEC = 1.2
LOW_SAMPLE_SEGMENT_COUNT = 2
LOW_SAMPLE_TOTAL_SEC = 6.0
LONG_SEGMENT_SEC = 8.0
VERY_LONG_SEGMENT_SEC = 15.0
SHORT_TEXT_CHARS = 8
RAPID_TURN_GAP_SEC = 0.2
SHORT_RUN_SEC = 1.5
SANDWICHED_RUN_SEC = 3.0


@dataclass(slots=True)
class NormalizedSegment:
    segment_id: str
    index: int
    start: float
    end: float
    duration: float
    text: str
    speaker_label: str
    language: str


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def write_json(payload: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(path)
    return path


def normalize_segments(segments_payload: dict[str, Any]) -> list[NormalizedSegment]:
    rows: list[NormalizedSegment] = []
    for index, raw in enumerate(segments_payload.get("segments", []), start=1):
        if not isinstance(raw, dict):
            continue
        start = _as_float(raw.get("start"))
        end = _as_float(raw.get("end"))
        duration = _as_float(raw.get("duration"))
        if duration <= 0.0:
            duration = max(0.0, end - start)
        rows.append(
            NormalizedSegment(
                segment_id=str(raw.get("id") or raw.get("segment_id") or f"seg-{index:04d}"),
                index=index,
                start=start,
                end=end,
                duration=duration,
                text=str(raw.get("text") or raw.get("source_text") or "").strip(),
                speaker_label=str(raw.get("speaker_label") or "UNKNOWN"),
                language=str(raw.get("language") or "unknown"),
            )
        )
    return sorted(rows, key=lambda item: (item.start, item.end, item.index))


def build_speaker_diagnostics(
    segments_payload: dict[str, Any],
    *,
    source_path: str | None = None,
) -> dict[str, Any]:
    segments = normalize_segments(segments_payload)
    speakers = _build_speaker_rows(segments)
    speakers_by_label = {row["speaker_label"]: row for row in speakers}
    segment_rows = _build_segment_rows(segments, speakers_by_label=speakers_by_label)
    run_rows = _build_run_rows(segments)

    _attach_reference_clips(speakers, segments)
    similarity = _build_similarity_matrix(speakers, segments)
    _attach_similar_peers(speakers, similarity)
    _attach_recommended_action(speakers, run_rows, segment_rows)

    high_risk_speaker_count = sum(1 for row in speakers if row["risk_level"] == "high")
    review_segment_count = sum(1 for row in segment_rows if row["risk_flags"])
    review_run_count = sum(1 for row in run_rows if row["risk_flags"])
    high_risk_run_count = sum(1 for row in run_rows if row["risk_level"] == "high")

    return {
        "version": 2,
        "algorithm_version": "speaker-review-diagnostics-v2",
        "generated_at": now_iso(),
        "source_path": source_path,
        "summary": {
            "segment_count": len(segments),
            "speaker_count": len(speakers),
            "high_risk_speaker_count": high_risk_speaker_count,
            "review_segment_count": review_segment_count,
            "speaker_run_count": len(run_rows),
            "review_run_count": review_run_count,
            "high_risk_run_count": high_risk_run_count,
        },
        "speakers": speakers,
        "speaker_runs": run_rows,
        "segments": segment_rows,
        "similarity": similarity,
    }


def build_speaker_review_plan(diagnostics: dict[str, Any]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for speaker in diagnostics.get("speakers", []):
        if not isinstance(speaker, dict):
            continue
        risk_flags = [str(flag) for flag in speaker.get("risk_flags", [])]
        if not risk_flags:
            continue
        items.append(
            {
                "item_id": f"speaker:{speaker.get('speaker_label')}",
                "item_type": "speaker_profile",
                "speaker_label": speaker.get("speaker_label"),
                "risk_level": speaker.get("risk_level"),
                "risk_flags": risk_flags,
                "segment_ids": speaker.get("segment_ids", []),
                "recommended_actions": _speaker_actions(risk_flags),
            }
        )

    for run in diagnostics.get("speaker_runs", []):
        if not isinstance(run, dict):
            continue
        risk_flags = [str(flag) for flag in run.get("risk_flags", [])]
        if not risk_flags:
            continue
        items.append(
            {
                "item_id": run.get("run_id"),
                "item_type": "speaker_run",
                "speaker_label": run.get("speaker_label"),
                "risk_level": run.get("risk_level"),
                "risk_flags": risk_flags,
                "segment_ids": run.get("segment_ids", []),
                "previous_speaker_label": run.get("previous_speaker_label"),
                "next_speaker_label": run.get("next_speaker_label"),
                "recommended_actions": _run_actions(run),
            }
        )

    for segment in diagnostics.get("segments", []):
        if not isinstance(segment, dict):
            continue
        risk_flags = [str(flag) for flag in segment.get("risk_flags", [])]
        if not risk_flags:
            continue
        items.append(
            {
                "item_id": f"segment:{segment.get('segment_id')}",
                "item_type": "segment",
                "speaker_label": segment.get("speaker_label"),
                "risk_level": segment.get("risk_level"),
                "risk_flags": risk_flags,
                "segment_ids": [segment.get("segment_id")],
                "recommended_actions": _segment_actions(risk_flags),
            }
        )

    return {
        "version": 1,
        "algorithm_version": "speaker-review-plan-v1",
        "generated_at": now_iso(),
        "summary": {
            "review_item_count": len(items),
            "speaker_item_count": sum(1 for item in items if item["item_type"] == "speaker_profile"),
            "run_item_count": sum(1 for item in items if item["item_type"] == "speaker_run"),
            "segment_item_count": sum(1 for item in items if item["item_type"] == "segment"),
        },
        "items": items,
    }


def write_speaker_review_artifacts(
    segments_payload: dict[str, Any],
    *,
    output_dir: Path,
    source_path: str | None = None,
) -> tuple[Path, Path]:
    diagnostics = build_speaker_diagnostics(segments_payload, source_path=source_path)
    plan = build_speaker_review_plan(diagnostics)
    diagnostics_path = write_json(diagnostics, output_dir / "speaker_diagnostics.zh.json")
    plan_path = write_json(plan, output_dir / "speaker_review_plan.zh.json")
    return diagnostics_path, plan_path


def _build_speaker_rows(segments: list[NormalizedSegment]) -> list[dict[str, Any]]:
    grouped: dict[str, list[NormalizedSegment]] = {}
    for segment in segments:
        grouped.setdefault(segment.speaker_label, []).append(segment)

    rows: list[dict[str, Any]] = []
    for speaker_label, speaker_segments in sorted(grouped.items()):
        total = round(sum(item.duration for item in speaker_segments), 3)
        short_count = sum(1 for item in speaker_segments if item.duration < SHORT_SEGMENT_SEC)
        risks: list[str] = []
        if len(speaker_segments) == 1:
            risks.append("single_segment_speaker")
        if len(speaker_segments) <= LOW_SAMPLE_SEGMENT_COUNT or total < LOW_SAMPLE_TOTAL_SEC:
            risks.append("low_sample_speaker")
        if short_count / max(len(speaker_segments), 1) >= 0.4:
            risks.append("mostly_short_segments")
        if len(speaker_segments) < 10 and total / max(len(speaker_segments), 1) >= LONG_SEGMENT_SEC:
            risks.append("sparse_long_timing")
        if not any(1.5 <= item.duration <= 15.0 for item in speaker_segments):
            risks.append("no_reference_safe_segment")
        rows.append(
            {
                "speaker_label": speaker_label,
                "segment_count": len(speaker_segments),
                "segment_ids": [item.segment_id for item in speaker_segments],
                "total_speech_sec": total,
                "avg_duration_sec": round(total / max(len(speaker_segments), 1), 3),
                "short_segment_count": short_count,
                "risk_flags": risks,
                "risk_level": _risk_level(risks),
                "cloneable_by_default": not any(
                    flag in risks for flag in {"single_segment_speaker", "low_sample_speaker", "no_reference_safe_segment"}
                ),
            }
        )
    return rows


def _build_segment_rows(
    segments: list[NormalizedSegment],
    *,
    speakers_by_label: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, segment in enumerate(segments):
        previous_segment = segments[index - 1] if index > 0 else None
        next_segment = segments[index + 1] if index + 1 < len(segments) else None
        risks: list[str] = []
        compact_text_len = len("".join(segment.text.split()))
        if segment.duration < SHORT_SEGMENT_SEC:
            risks.append("short_segment")
        if segment.duration >= LONG_SEGMENT_SEC and compact_text_len < SHORT_TEXT_CHARS:
            risks.append("long_timing_short_text")
        if segment.duration >= VERY_LONG_SEGMENT_SEC:
            risks.append("very_long_segment")
        if _has_rapid_boundary(segment, previous_segment, next_segment):
            risks.append("speaker_boundary_risk")
        speaker_risks = set(speakers_by_label.get(segment.speaker_label, {}).get("risk_flags", []))
        if speaker_risks & {"single_segment_speaker", "low_sample_speaker"}:
            risks.append("speaker_sample_risk")
        rows.append(
            {
                "segment_id": segment.segment_id,
                "index": segment.index,
                "speaker_label": segment.speaker_label,
                "start": round(segment.start, 3),
                "end": round(segment.end, 3),
                "duration": round(segment.duration, 3),
                "text": segment.text,
                "previous_speaker_label": previous_segment.speaker_label if previous_segment else None,
                "next_speaker_label": next_segment.speaker_label if next_segment else None,
                "risk_flags": _dedupe(risks),
                "risk_level": _risk_level(risks),
            }
        )
    return rows


def _build_run_rows(segments: list[NormalizedSegment]) -> list[dict[str, Any]]:
    if not segments:
        return []
    groups: list[list[NormalizedSegment]] = [[segments[0]]]
    for segment in segments[1:]:
        current = groups[-1]
        if segment.speaker_label == current[-1].speaker_label:
            current.append(segment)
        else:
            groups.append([segment])

    rows: list[dict[str, Any]] = []
    for index, group in enumerate(groups):
        previous_group = groups[index - 1] if index > 0 else None
        next_group = groups[index + 1] if index + 1 < len(groups) else None
        start = group[0].start
        end = group[-1].end
        duration = max(0.0, end - start)
        previous_speaker = previous_group[-1].speaker_label if previous_group else None
        next_speaker = next_group[0].speaker_label if next_group else None
        gap_before = max(0.0, start - previous_group[-1].end) if previous_group else None
        gap_after = max(0.0, next_group[0].start - end) if next_group else None
        risks: list[str] = []
        if len(group) == 1:
            risks.append("single_segment_run")
        if duration < SHORT_RUN_SEC:
            risks.append("short_run")
        if previous_speaker and previous_speaker == next_speaker and previous_speaker != group[0].speaker_label and duration <= SANDWICHED_RUN_SEC:
            risks.append("sandwiched_run")
        if (gap_before is not None and gap_before < RAPID_TURN_GAP_SEC) or (gap_after is not None and gap_after < RAPID_TURN_GAP_SEC):
            risks.append("rapid_turn_boundary")
        rows.append(
            {
                "run_id": f"run-{index + 1:04d}",
                "speaker_label": group[0].speaker_label,
                "start": round(start, 3),
                "end": round(end, 3),
                "duration": round(duration, 3),
                "segment_count": len(group),
                "segment_ids": [segment.segment_id for segment in group],
                "text": " ".join(segment.text for segment in group).strip(),
                "previous_speaker_label": previous_speaker,
                "next_speaker_label": next_speaker,
                "gap_before_sec": round(gap_before, 3) if gap_before is not None else None,
                "gap_after_sec": round(gap_after, 3) if gap_after is not None else None,
                "risk_flags": risks,
                "risk_level": _risk_level(risks),
            }
        )
    return rows


def _speaker_actions(risk_flags: list[str]) -> list[str]:
    actions = ["keep_independent", "merge_speaker"]
    if any(flag in risk_flags for flag in ("single_segment_speaker", "low_sample_speaker", "no_reference_safe_segment")):
        actions.insert(0, "mark_non_cloneable")
    return actions


def _run_actions(run: dict[str, Any]) -> list[str]:
    actions = ["keep_independent", "relabel"]
    if run.get("previous_speaker_label"):
        actions.insert(0, "relabel_to_previous_speaker")
    if run.get("next_speaker_label"):
        actions.insert(1, "relabel_to_next_speaker")
    if run.get("previous_speaker_label") and run.get("previous_speaker_label") == run.get("next_speaker_label"):
        actions.insert(0, "merge_to_surrounding_speaker")
    return _dedupe(actions)


def _segment_actions(risk_flags: list[str]) -> list[str]:
    actions = ["keep_independent", "relabel"]
    if "speaker_boundary_risk" in risk_flags or "speaker_sample_risk" in risk_flags:
        actions = ["relabel_to_previous_speaker", "relabel_to_next_speaker", *actions]
    return _dedupe(actions)


def _risk_level(risk_flags: list[str]) -> str:
    flags = set(risk_flags)
    if flags & {"single_segment_speaker", "very_long_segment", "sandwiched_run", "long_timing_short_text"}:
        return "high"
    if flags:
        return "medium"
    return "low"


def _has_rapid_boundary(
    segment: NormalizedSegment,
    previous_segment: NormalizedSegment | None,
    next_segment: NormalizedSegment | None,
) -> bool:
    if previous_segment and previous_segment.speaker_label != segment.speaker_label:
        if max(0.0, segment.start - previous_segment.end) < RAPID_TURN_GAP_SEC:
            return True
    if next_segment and next_segment.speaker_label != segment.speaker_label:
        if max(0.0, next_segment.start - segment.end) < RAPID_TURN_GAP_SEC:
            return True
    return False


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


REFERENCE_CLIP_LIMIT = 3


def _attach_reference_clips(
    speakers: list[dict[str, Any]],
    segments: list[NormalizedSegment],
) -> None:
    by_label: dict[str, list[NormalizedSegment]] = {}
    for segment in segments:
        by_label.setdefault(segment.speaker_label, []).append(segment)

    for row in speakers:
        label = str(row.get("speaker_label") or "")
        candidates = by_label.get(label, [])
        scored: list[tuple[float, NormalizedSegment]] = []
        for segment in candidates:
            if segment.duration < MIN_REFERENCE_DURATION:
                continue
            if segment.duration > MAX_REFERENCE_DURATION:
                continue
            text_len = len("".join(segment.text.split()))
            score = min(segment.duration, 8.0) + min(text_len / 10.0, 1.5)
            scored.append((score, segment))
        scored.sort(key=lambda item: item[0], reverse=True)
        clips: list[dict[str, Any]] = []
        for index, (score, segment) in enumerate(scored[:REFERENCE_CLIP_LIMIT]):
            clips.append(
                {
                    "clip_id": f"{label}::ref::{segment.segment_id}",
                    "segment_id": segment.segment_id,
                    "start": round(segment.start, 3),
                    "end": round(segment.end, 3),
                    "duration": round(segment.duration, 3),
                    "text": segment.text,
                    "is_best": index == 0,
                    "score": round(score, 3),
                }
            )
        if not clips and candidates:
            best = max(candidates, key=lambda item: item.duration)
            clips.append(
                {
                    "clip_id": f"{label}::ref::{best.segment_id}",
                    "segment_id": best.segment_id,
                    "start": round(best.start, 3),
                    "end": round(best.end, 3),
                    "duration": round(best.duration, 3),
                    "text": best.text,
                    "is_best": True,
                    "score": 0.0,
                }
            )
        row["reference_clips"] = clips
        row["best_reference_clip_id"] = clips[0]["clip_id"] if clips else None


MIN_REFERENCE_DURATION = 1.5
MAX_REFERENCE_DURATION = 12.0
SIMILAR_PEER_THRESHOLD = 0.55
SIMILAR_PEER_LIMIT = 3


def _build_similarity_matrix(
    speakers: list[dict[str, Any]],
    segments: list[NormalizedSegment],
) -> dict[str, Any]:
    labels = [str(row.get("speaker_label") or "") for row in speakers]
    profiles: dict[str, dict[str, float]] = {}
    for label in labels:
        profile: dict[str, float] = {
            "avg_duration": 0.0,
            "short_ratio": 0.0,
            "segment_count": 0.0,
            "total_speech": 0.0,
        }
        speaker_segments = [seg for seg in segments if seg.speaker_label == label]
        if not speaker_segments:
            profiles[label] = profile
            continue
        durations = [seg.duration for seg in speaker_segments]
        profile["avg_duration"] = float(sum(durations) / len(durations))
        short = sum(1 for value in durations if value < SHORT_SEGMENT_SEC)
        profile["short_ratio"] = float(short / len(durations))
        profile["segment_count"] = float(len(speaker_segments))
        profile["total_speech"] = float(sum(durations))
        profiles[label] = profile

    matrix: list[list[float]] = []
    for label_a in labels:
        row: list[float] = []
        for label_b in labels:
            row.append(round(_speaker_profile_similarity(profiles[label_a], profiles[label_b]), 3))
        matrix.append(row)

    return {
        "labels": labels,
        "matrix": matrix,
        "threshold_suggest_merge": SIMILAR_PEER_THRESHOLD,
        "method": "profile-heuristic-v1",
    }


def _speaker_profile_similarity(
    profile_a: dict[str, float],
    profile_b: dict[str, float],
) -> float:
    if profile_a is profile_b:
        return 1.0
    avg_diff = abs(profile_a["avg_duration"] - profile_b["avg_duration"])
    avg_score = max(0.0, 1.0 - min(avg_diff / 5.0, 1.0))
    short_score = max(0.0, 1.0 - abs(profile_a["short_ratio"] - profile_b["short_ratio"]))
    seg_a = profile_a["segment_count"]
    seg_b = profile_b["segment_count"]
    seg_score = 0.0
    if seg_a > 0 and seg_b > 0:
        seg_score = min(seg_a, seg_b) / max(seg_a, seg_b)
    return 0.5 * avg_score + 0.3 * short_score + 0.2 * seg_score


def _attach_similar_peers(
    speakers: list[dict[str, Any]],
    similarity: dict[str, Any],
) -> None:
    labels: list[str] = list(similarity.get("labels", []))
    matrix: list[list[float]] = list(similarity.get("matrix", []))
    threshold: float = float(similarity.get("threshold_suggest_merge", SIMILAR_PEER_THRESHOLD))
    for index, row in enumerate(speakers):
        label = str(row.get("speaker_label") or "")
        peers: list[dict[str, Any]] = []
        if label not in labels or index >= len(matrix):
            row["similar_peers"] = peers
            continue
        scores = matrix[index]
        ranked = sorted(
            (
                (other_label, scores[other_index])
                for other_index, other_label in enumerate(labels)
                if other_label != label
            ),
            key=lambda item: item[1],
            reverse=True,
        )
        for other_label, score in ranked[:SIMILAR_PEER_LIMIT]:
            peers.append(
                {
                    "label": other_label,
                    "similarity": round(float(score), 3),
                    "suggest_merge": bool(score >= threshold),
                }
            )
        row["similar_peers"] = peers


def _attach_recommended_action(
    speakers: list[dict[str, Any]],
    runs: list[dict[str, Any]],
    segments: list[dict[str, Any]],
) -> None:
    for row in speakers:
        flags = set(row.get("risk_flags", []))
        if flags & {"single_segment_speaker", "low_sample_speaker", "no_reference_safe_segment"}:
            row["recommended_action"] = "mark_non_cloneable"
        elif row.get("similar_peers") and row["similar_peers"][0].get("suggest_merge"):
            row["recommended_action"] = "merge_speaker"
        else:
            row["recommended_action"] = "keep_independent"

    for row in runs:
        flags = set(row.get("risk_flags", []))
        previous_label = row.get("previous_speaker_label")
        next_label = row.get("next_speaker_label")
        if "sandwiched_run" in flags and previous_label and previous_label == next_label:
            row["recommended_action"] = "merge_to_surrounding_speaker"
        elif "short_run" in flags and previous_label:
            row["recommended_action"] = "relabel_to_previous_speaker"
        elif "single_segment_run" in flags and next_label:
            row["recommended_action"] = "relabel_to_next_speaker"
        else:
            row["recommended_action"] = "keep_independent"

    for row in segments:
        flags = set(row.get("risk_flags", []))
        if "speaker_boundary_risk" in flags and row.get("previous_speaker_label"):
            row["recommended_action"] = "relabel_to_previous_speaker"
        elif "very_long_segment" in flags:
            row["recommended_action"] = "keep_independent"
        elif "speaker_sample_risk" in flags and row.get("next_speaker_label"):
            row["recommended_action"] = "relabel_to_next_speaker"
        else:
            row["recommended_action"] = "keep_independent"
