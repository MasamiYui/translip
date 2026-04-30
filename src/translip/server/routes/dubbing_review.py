from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session

from ..database import get_session
from ..models import Task

router = APIRouter(prefix="/api/tasks", tags=["dubbing-review"])

_DECISION_FILES = {
    "reference": "manual_reference_decisions",
    "merge": "manual_merge_decisions",
    "repair": "manual_repair_decisions",
}


class DubbingReviewDecisionRequest(BaseModel):
    category: str
    item_id: str
    decision: str
    speaker_id: str | None = None
    reference_path: str | None = None
    attempt_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


@router.get("/{task_id}/dubbing-review")
def get_dubbing_review(task_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    task = _get_task(session, task_id)
    root = Path(task.output_root).resolve()
    target_lang = task.target_lang or "en"
    paths = _review_paths(root, target_lang)

    profiles = _read_json(paths["profiles"])
    repair_queue = _read_json(paths["repair_queue"])
    reference_plan = _read_json(paths["reference_plan"])
    rewrite_plan = _read_json(paths["rewrite_plan"])
    merge_plan = _read_json(paths["merge_plan"])
    translation = _read_json(paths["translation"])
    repair_attempts = _read_json(paths["repair_attempts"])
    voice_bank = _read_json(paths["voice_bank"])
    character_ledger = _read_json(paths["character_ledger"])
    quality_benchmark = _read_json(paths["dub_benchmark"])

    decisions = {
        "reference": _read_json(paths["reference_decisions"]),
        "merge": _read_json(paths["merge_decisions"]),
        "repair": _read_json(paths["repair_decisions"]),
    }
    latest_decisions = {
        key: _latest_decisions_by_item(payload)
        for key, payload in decisions.items()
    }

    speakers = _build_speakers(
        root=root,
        profiles=profiles,
        reference_plan=reference_plan,
        voice_bank=voice_bank,
        reference_decisions=latest_decisions["reference"],
    )
    repair_items = _build_repair_items(
        root=root,
        repair_queue=repair_queue,
        rewrite_plan=rewrite_plan,
        repair_attempts=repair_attempts,
        repair_decisions=latest_decisions["repair"],
    )
    merge_candidates = _build_merge_candidates(
        root=root,
        merge_plan=merge_plan,
        translation=translation,
        repair_queue=repair_queue,
        merge_decisions=latest_decisions["merge"],
    )
    characters = _build_characters(character_ledger)

    artifact_paths = {
        key: _relative_path(path, root)
        for key, path in paths.items()
        if path is not None and path.exists()
    }
    stats = dict(repair_queue.get("stats") or {}) if isinstance(repair_queue, dict) else {}
    quality_status = quality_benchmark.get("status") if isinstance(quality_benchmark, dict) else None
    quality_score = quality_benchmark.get("score") if isinstance(quality_benchmark, dict) else None
    character_stats = character_ledger.get("stats", {}) if isinstance(character_ledger.get("stats"), dict) else {}
    status = "available" if speakers or repair_items or merge_candidates or characters or quality_benchmark else "missing"

    return {
        "task_id": task_id,
        "target_lang": target_lang,
        "status": status,
        "summary": {
            "speaker_count": len(speakers),
            "merge_candidate_count": len(merge_candidates),
            "repair_item_count": len(repair_items),
            "reference_decision_count": len(latest_decisions["reference"]),
            "merge_decision_count": len(latest_decisions["merge"]),
            "repair_decision_count": len(latest_decisions["repair"]),
            "quality_status": quality_status,
            "quality_score": quality_score,
            "character_review_count": int(character_stats.get("review_count") or 0),
        },
        "stats": stats,
        "artifact_paths": artifact_paths,
        "quality_benchmark": _quality_benchmark_payload(quality_benchmark),
        "characters": characters,
        "speakers": speakers,
        "merge_candidates": merge_candidates,
        "repair_items": repair_items,
        "decisions": {
            key: list(value.values())
            for key, value in latest_decisions.items()
        },
    }


@router.post("/{task_id}/dubbing-review/decisions")
def save_dubbing_review_decision(
    task_id: str,
    req: DubbingReviewDecisionRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    task = _get_task(session, task_id)
    category = req.category.strip().lower()
    if category not in _DECISION_FILES:
        raise HTTPException(status_code=400, detail="Unsupported dubbing review decision category")
    if not req.item_id.strip():
        raise HTTPException(status_code=400, detail="Decision item_id is required")
    if not req.decision.strip():
        raise HTTPException(status_code=400, detail="Decision value is required")

    root = Path(task.output_root).resolve()
    target_lang = task.target_lang or "en"
    path = root / "task-d" / "voice" / f"{_DECISION_FILES[category]}.{target_lang}.json"
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = _read_json(path)
    if not payload:
        payload = {
            "task_id": task_id,
            "target_lang": target_lang,
            "decisions": [],
        }

    now = _now_iso()
    decision_payload = {
        "category": category,
        "item_id": req.item_id.strip(),
        "decision": req.decision.strip(),
        "speaker_id": req.speaker_id,
        "reference_path": req.reference_path,
        "attempt_id": req.attempt_id,
        "payload": req.payload,
        "updated_at": now,
    }

    decisions = [
        row
        for row in payload.get("decisions", [])
        if not (isinstance(row, dict) and str(row.get("item_id") or "") == decision_payload["item_id"])
    ]
    decisions.append(decision_payload)
    payload["task_id"] = task_id
    payload["target_lang"] = target_lang
    payload["updated_at"] = now
    payload["decision_count"] = len(decisions)
    payload["decisions"] = decisions
    _write_json(path, payload)

    return {
        "ok": True,
        "category": category,
        "item_id": decision_payload["item_id"],
        "decision": decision_payload["decision"],
        "path": _relative_path(path, root),
        "decision_count": len(decisions),
    }


def _get_task(session: Session, task_id: str) -> Task:
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


def _review_paths(root: Path, target_lang: str) -> dict[str, Path | None]:
    repair_plan_dir = root / "task-d" / "voice" / "repair-plan"
    repair_run_dir = root / "task-d" / "voice" / "repair-run"
    voice_dir = root / "task-d" / "voice"
    task_b_voice = root / "task-b" / "voice"
    return {
        "profiles": task_b_voice / "speaker_profiles.json",
        "translation": _first_existing([
            root / "task-c" / "voice" / f"translation.{target_lang}.json",
            root / "task-c" / f"translation.{target_lang}.json",
        ]),
        "repair_queue": _first_existing([
            repair_plan_dir / f"repair_queue.{target_lang}.json",
            root / "task-e" / "voice" / f"repair_queue.{target_lang}.json",
        ]),
        "reference_plan": repair_plan_dir / f"reference_plan.{target_lang}.json",
        "rewrite_plan": repair_plan_dir / f"rewrite_plan.{target_lang}.json",
        "merge_plan": repair_plan_dir / f"merge_plan.{target_lang}.json",
        "repair_attempts": repair_run_dir / f"repair_attempts.{target_lang}.json",
        "selected_segments": _first_existing([
            repair_run_dir / f"selected_segments.{target_lang}.json",
            voice_dir / f"selected_segments.{target_lang}.json",
        ]),
        "character_ledger": voice_dir / "character-ledger" / f"character_ledger.{target_lang}.json",
        "dub_benchmark": root / "benchmark" / "voice" / f"dub_benchmark.{target_lang}.json",
        "voice_bank": _first_existing([
            task_b_voice / "voice_bank" / f"voice_bank.{target_lang}.json",
            task_b_voice / "voice_bank" / "voice_bank.json",
        ]),
        "reference_decisions": voice_dir / f"manual_reference_decisions.{target_lang}.json",
        "merge_decisions": voice_dir / f"manual_merge_decisions.{target_lang}.json",
        "repair_decisions": voice_dir / f"manual_repair_decisions.{target_lang}.json",
    }


def _first_existing(paths: list[Path]) -> Path | None:
    return next((path for path in paths if path.exists()), paths[0] if paths else None)


def _read_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists() or not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def _latest_decisions_by_item(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for raw in payload.get("decisions", []):
        if not isinstance(raw, dict):
            continue
        item_id = str(raw.get("item_id") or "")
        if item_id:
            rows[item_id] = raw
    return rows


def _build_speakers(
    *,
    root: Path,
    profiles: dict[str, Any],
    reference_plan: dict[str, Any],
    voice_bank: dict[str, Any],
    reference_decisions: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    profiles_by_speaker = {
        str(profile.get("speaker_id") or ""): profile
        for profile in profiles.get("profiles", [])
        if isinstance(profile, dict) and profile.get("speaker_id")
    }
    plan_by_speaker = {
        str(row.get("speaker_id") or ""): row
        for row in reference_plan.get("speakers", [])
        if isinstance(row, dict) and row.get("speaker_id")
    }
    bank_by_speaker = {
        str(row.get("speaker_id") or ""): row
        for row in voice_bank.get("speakers", [])
        if isinstance(row, dict) and row.get("speaker_id")
    }
    speaker_ids = sorted(set(profiles_by_speaker) | set(plan_by_speaker) | set(bank_by_speaker))
    speakers: list[dict[str, Any]] = []
    for speaker_id in speaker_ids:
        profile = profiles_by_speaker.get(speaker_id, {})
        plan = plan_by_speaker.get(speaker_id, {})
        bank = bank_by_speaker.get(speaker_id, {})
        current_path = str(plan.get("current_reference_path") or "")
        recommended_path = str(plan.get("recommended_reference_path") or "")
        candidates = _reference_candidates(
            root=root,
            profile=profile,
            plan=plan,
            bank=bank,
            current_path=current_path,
            recommended_path=recommended_path,
        )
        speakers.append({
            "speaker_id": speaker_id,
            "profile_id": profile.get("profile_id") or bank.get("profile_id") or "",
            "display_name": profile.get("display_name") or profile.get("source_label") or speaker_id,
            "source_label": profile.get("source_label"),
            "status": profile.get("status") or bank.get("bank_status") or "unknown",
            "total_speech_sec": _round_float(profile.get("total_speech_sec")),
            "segment_count": int(profile.get("segment_count") or 0),
            "reference_clip_count": int(profile.get("reference_clip_count") or len(candidates)),
            "speaker_failed_count": int(plan.get("speaker_failed_count") or 0),
            "repair_item_count": int(plan.get("repair_item_count") or 0),
            "current_reference_path": current_path or None,
            "recommended_reference_path": recommended_path or None,
            "bank_status": bank.get("bank_status"),
            "recommended_reference_id": bank.get("recommended_reference_id"),
            "decision": reference_decisions.get(speaker_id),
            "candidates": candidates,
        })
    return speakers


def _reference_candidates(
    *,
    root: Path,
    profile: dict[str, Any],
    plan: dict[str, Any],
    bank: dict[str, Any],
    current_path: str,
    recommended_path: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in plan.get("candidates", []):
        if isinstance(raw, dict):
            rows.append(_reference_candidate_payload(
                root=root,
                raw=raw,
                source="reference_plan",
                current_path=current_path,
                recommended_path=recommended_path,
            ))
            seen.add(str(raw.get("path") or ""))
    for raw in bank.get("references", []):
        if isinstance(raw, dict) and str(raw.get("audio_path") or "") not in seen:
            rows.append(_reference_candidate_payload(
                root=root,
                raw={**raw, "path": raw.get("audio_path")},
                source=str(raw.get("type") or "voice_bank"),
                current_path=current_path,
                recommended_path=recommended_path,
            ))
            seen.add(str(raw.get("audio_path") or ""))
    if not rows:
        for raw in profile.get("reference_clips", []):
            if isinstance(raw, dict):
                rows.append(_reference_candidate_payload(
                    root=root,
                    raw=raw,
                    source="speaker_profile",
                    current_path=current_path,
                    recommended_path=recommended_path,
                ))
    return rows


def _reference_candidate_payload(
    *,
    root: Path,
    raw: dict[str, Any],
    source: str,
    current_path: str,
    recommended_path: str,
) -> dict[str, Any]:
    path = str(raw.get("path") or raw.get("audio_path") or "")
    artifact_path = _artifact_path(path, root)
    return {
        "reference_id": str(raw.get("reference_id") or Path(path).stem or source),
        "source": source,
        "path": path,
        "artifact_path": artifact_path,
        "duration_sec": _round_float(raw.get("duration_sec", raw.get("duration"))),
        "text": str(raw.get("text") or raw.get("reference_text") or ""),
        "rms": _round_float(raw.get("rms")),
        "quality_score": _round_float(raw.get("quality_score", raw.get("score"))),
        "selection_reason": raw.get("selection_reason"),
        "risk_flags": raw.get("risk_flags") if isinstance(raw.get("risk_flags"), list) else [],
        "is_current": _same_path(path, current_path) or bool(raw.get("is_current")),
        "is_recommended": _same_path(path, recommended_path),
    }


def _build_repair_items(
    *,
    root: Path,
    repair_queue: dict[str, Any],
    rewrite_plan: dict[str, Any],
    repair_attempts: dict[str, Any],
    repair_decisions: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rewrites = {
        str(row.get("segment_id") or ""): row.get("rewrite_candidates", [])
        for row in rewrite_plan.get("items", [])
        if isinstance(row, dict)
    }
    attempts = _attempts_by_segment(repair_attempts)
    items: list[dict[str, Any]] = []
    for raw in repair_queue.get("items", []):
        if not isinstance(raw, dict):
            continue
        segment_id = str(raw.get("segment_id") or "")
        audio_path = str(raw.get("audio_path") or "")
        item_attempts = attempts.get(segment_id, [])
        items.append({
            "segment_id": segment_id,
            "speaker_id": raw.get("speaker_id"),
            "source_text": raw.get("source_text"),
            "target_text": raw.get("target_text"),
            "anchor_start": _round_float(raw.get("anchor_start")),
            "anchor_end": _round_float(raw.get("anchor_end")),
            "source_duration_sec": _round_float(raw.get("source_duration_sec")),
            "generated_duration_sec": _round_float(raw.get("generated_duration_sec")),
            "audio_path": audio_path,
            "audio_artifact_path": _artifact_path(audio_path, root),
            "reference_path": raw.get("reference_path"),
            "queue_class": raw.get("queue_class"),
            "strict_blocker": bool(raw.get("strict_blocker")),
            "priority": raw.get("priority"),
            "priority_score": _round_float(raw.get("priority_score")),
            "failure_reasons": raw.get("failure_reasons") if isinstance(raw.get("failure_reasons"), list) else [],
            "suggested_actions": raw.get("suggested_actions") if isinstance(raw.get("suggested_actions"), list) else [],
            "metrics": raw.get("metrics") if isinstance(raw.get("metrics"), dict) else {},
            "rewrite_candidates": rewrites.get(segment_id, []),
            "attempts": [
                _attempt_payload(root=root, attempt=attempt)
                for attempt in item_attempts
            ],
            "decision": repair_decisions.get(segment_id),
        })
    return sorted(items, key=_repair_sort_key)


def _build_characters(character_ledger: dict[str, Any]) -> list[dict[str, Any]]:
    characters: list[dict[str, Any]] = []
    for raw in character_ledger.get("characters", []):
        if not isinstance(raw, dict):
            continue
        voice_signature = raw.get("voice_signature") if isinstance(raw.get("voice_signature"), dict) else {}
        stats = raw.get("stats") if isinstance(raw.get("stats"), dict) else {}
        characters.append({
            "character_id": str(raw.get("character_id") or ""),
            "display_name": str(raw.get("display_name") or raw.get("character_id") or ""),
            "speaker_ids": raw.get("speaker_ids") if isinstance(raw.get("speaker_ids"), list) else [],
            "source_label": raw.get("source_label"),
            "profile_id": raw.get("profile_id"),
            "reference_path": raw.get("reference_path"),
            "pitch_class": voice_signature.get("pitch_class"),
            "pitch_hz": _round_float(voice_signature.get("pitch_hz")),
            "review_status": raw.get("review_status") or "unknown",
            "risk_flags": raw.get("risk_flags") if isinstance(raw.get("risk_flags"), list) else [],
            "stats": stats,
        })
    return characters


def _quality_benchmark_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    if not payload:
        return None
    return {
        "version": payload.get("version"),
        "status": payload.get("status"),
        "score": payload.get("score"),
        "reasons": payload.get("reasons") if isinstance(payload.get("reasons"), list) else [],
        "metrics": payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {},
        "gates": payload.get("gates") if isinstance(payload.get("gates"), list) else [],
    }


def _attempts_by_segment(repair_attempts: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    rows: dict[str, list[dict[str, Any]]] = {}
    for raw in repair_attempts.get("items", repair_attempts.get("segments", [])):
        if not isinstance(raw, dict):
            continue
        segment_id = str(raw.get("segment_id") or "")
        attempts = raw.get("attempts", [])
        if segment_id and isinstance(attempts, list):
            rows[segment_id] = [attempt for attempt in attempts if isinstance(attempt, dict)]
    return rows


def _attempt_payload(*, root: Path, attempt: dict[str, Any]) -> dict[str, Any]:
    audio_path = str(attempt.get("audio_path") or "")
    return {
        **attempt,
        "audio_artifact_path": _artifact_path(audio_path, root),
    }


def _repair_sort_key(item: dict[str, Any]) -> tuple[int, float, str]:
    priority_rank = {"high": 0, "medium": 1, "low": 2}.get(str(item.get("priority") or ""), 3)
    anchor = float(item.get("anchor_start") or 0.0)
    return (priority_rank, anchor, str(item.get("segment_id") or ""))


def _build_merge_candidates(
    *,
    root: Path,
    merge_plan: dict[str, Any],
    translation: dict[str, Any],
    repair_queue: dict[str, Any],
    merge_decisions: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    groups = merge_plan.get("groups", []) if isinstance(merge_plan.get("groups"), list) else []
    if groups:
        return [
            _merge_group_payload(root=root, raw=raw, decision=merge_decisions.get(str(raw.get("repair_group_id") or raw.get("group_id") or "")))
            for raw in groups
            if isinstance(raw, dict)
        ]
    return _provisional_merge_candidates(
        root=root,
        translation=translation,
        repair_queue=repair_queue,
        merge_decisions=merge_decisions,
    )


def _merge_group_payload(*, root: Path, raw: dict[str, Any], decision: dict[str, Any] | None) -> dict[str, Any]:
    group_id = str(raw.get("repair_group_id") or raw.get("group_id") or "")
    audio_path = str(raw.get("generated_audio_path") or raw.get("audio_path") or "")
    return {
        "group_id": group_id,
        "group_type": raw.get("group_type") or raw.get("action") or "same_speaker_merge_group",
        "status": raw.get("status") or raw.get("decision") or "planned",
        "source": "merge_plan",
        "source_segment_ids": raw.get("source_segment_ids") if isinstance(raw.get("source_segment_ids"), list) else [],
        "speaker_id": raw.get("speaker_id"),
        "anchor_start_sec": _round_float(raw.get("anchor_start_sec", raw.get("anchor_start"))),
        "anchor_end_sec": _round_float(raw.get("anchor_end_sec", raw.get("anchor_end"))),
        "source_text": raw.get("merged_source_text") or raw.get("source_text"),
        "target_text": raw.get("merged_target_text") or raw.get("target_text"),
        "audio_path": audio_path,
        "audio_artifact_path": _artifact_path(audio_path, root),
        "metrics": raw.get("metrics") if isinstance(raw.get("metrics"), dict) else {},
        "decision": decision,
        "children": raw.get("children") if isinstance(raw.get("children"), list) else [],
    }


def _provisional_merge_candidates(
    *,
    root: Path,
    translation: dict[str, Any],
    repair_queue: dict[str, Any],
    merge_decisions: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    segments = [
        row
        for row in translation.get("segments", [])
        if isinstance(row, dict) and row.get("segment_id")
    ]
    segments.sort(key=lambda row: float(row.get("start", row.get("anchor_start", 0.0)) or 0.0))
    repair_items = {
        str(row.get("segment_id") or ""): row
        for row in repair_queue.get("items", [])
        if isinstance(row, dict) and row.get("segment_id")
    }
    merge_ids = {
        segment_id
        for segment_id, row in repair_items.items()
        if "merge_short_segments" in set(row.get("suggested_actions") or [])
    }
    candidates: list[dict[str, Any]] = []
    visited: set[str] = set()
    for index, segment in enumerate(segments):
        segment_id = str(segment.get("segment_id") or "")
        if segment_id not in merge_ids or segment_id in visited:
            continue
        group = [segment]
        cursor = index + 1
        while cursor < len(segments) and len(group) < 4:
            previous = group[-1]
            current = segments[cursor]
            if str(current.get("speaker_id") or "") != str(previous.get("speaker_id") or ""):
                break
            gap = float(current.get("start", 0.0) or 0.0) - float(previous.get("end", 0.0) or 0.0)
            total_duration = float(current.get("end", 0.0) or 0.0) - float(group[0].get("start", 0.0) or 0.0)
            current_id = str(current.get("segment_id") or "")
            current_short = float(current.get("duration", 0.0) or 0.0) <= 1.5
            if gap < -0.08 or gap > 0.35 or total_duration > 6.0 or (current_id not in merge_ids and not current_short):
                break
            group.append(current)
            cursor += 1
        if len(group) < 2:
            continue
        for row in group:
            visited.add(str(row.get("segment_id") or ""))
        group_id = f"pmg-{group[0].get('segment_id')}-{group[-1].get('segment_id')}"
        first = group[0]
        last = group[-1]
        first_repair = repair_items.get(str(first.get("segment_id") or ""), {})
        audio_path = str(first_repair.get("audio_path") or "")
        candidates.append({
            "group_id": group_id,
            "group_type": "same_speaker_merge_group",
            "status": "provisional",
            "source": "derived_from_repair_queue",
            "source_segment_ids": [str(row.get("segment_id") or "") for row in group],
            "speaker_id": first.get("speaker_id"),
            "anchor_start_sec": _round_float(first.get("start")),
            "anchor_end_sec": _round_float(last.get("end")),
            "source_text": " ".join(str(row.get("source_text") or "") for row in group).strip(),
            "target_text": " ".join(str(row.get("target_text") or "") for row in group).strip(),
            "audio_path": audio_path,
            "audio_artifact_path": _artifact_path(audio_path, root),
            "metrics": {
                "combined_source_duration_sec": _round_float(float(last.get("end", 0.0) or 0.0) - float(first.get("start", 0.0) or 0.0)),
                "segment_count": len(group),
            },
            "decision": merge_decisions.get(group_id),
            "children": [
                {
                    "segment_id": row.get("segment_id"),
                    "speaker_id": row.get("speaker_id"),
                    "source_text": row.get("source_text"),
                    "target_text": row.get("target_text"),
                    "start": _round_float(row.get("start")),
                    "end": _round_float(row.get("end")),
                }
                for row in group
            ],
        })
    return candidates


def _same_path(left: str, right: str) -> bool:
    if not left or not right:
        return False
    try:
        return Path(left).expanduser().resolve() == Path(right).expanduser().resolve()
    except Exception:
        return left == right


def _artifact_path(path_value: str, root: Path) -> str | None:
    if not path_value:
        return None
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        return path.as_posix()
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return None


def _relative_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _round_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
