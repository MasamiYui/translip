from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session

from ...speaker_review.decisions import latest_decisions_by_item, write_speaker_corrected_artifacts
from ...speaker_review.diagnostics import (
    build_speaker_diagnostics,
    build_speaker_review_plan,
    load_json,
    now_iso,
    write_json,
)
from ..database import get_session
from ..models import Task

router = APIRouter(prefix="/api/tasks", tags=["speaker-review"])


class SpeakerReviewDecisionRequest(BaseModel):
    item_id: str
    item_type: str
    decision: str
    source_speaker_label: str | None = None
    target_speaker_label: str | None = None
    segment_ids: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)


@router.get("/{task_id}/speaker-review")
def get_speaker_review(task_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    task = _get_task(session, task_id)
    root = Path(task.output_root).resolve()
    paths = _speaker_review_paths(root)
    source_segments_path = _source_segments_path(paths)

    if source_segments_path is None:
        return {
            "task_id": task_id,
            "status": "missing",
            "summary": {
                "segment_count": 0,
                "speaker_count": 0,
                "high_risk_speaker_count": 0,
                "speaker_run_count": 0,
                "high_risk_run_count": 0,
                "review_segment_count": 0,
                "decision_count": 0,
                "corrected_exists": False,
            },
            "artifact_paths": {},
            "speakers": [],
            "speaker_runs": [],
            "segments": [],
            "review_plan": {"items": []},
            "decisions": [],
            "manifest": {},
        }

    review_dir = paths["review_dir"]
    review_dir.mkdir(parents=True, exist_ok=True)
    diagnostics = build_speaker_diagnostics(
        load_json(source_segments_path),
        source_path=_relative_path(source_segments_path, root),
    )
    review_plan = build_speaker_review_plan(diagnostics)
    write_json(diagnostics, paths["diagnostics"])
    write_json(review_plan, paths["review_plan"])

    decisions_payload = load_json(paths["decisions"]) if paths["decisions"].exists() else {}
    decisions = latest_decisions_by_item(decisions_payload)
    manifest = load_json(paths["manifest"]) if paths["manifest"].exists() else {}

    return {
        "task_id": task_id,
        "status": "available",
        "summary": {
            **diagnostics.get("summary", {}),
            "decision_count": len(decisions),
            "corrected_exists": paths["corrected_segments"].exists(),
        },
        "artifact_paths": _existing_artifact_paths(paths, root),
        "speakers": _attach_speaker_decisions(diagnostics.get("speakers", []), decisions),
        "speaker_runs": _attach_item_decisions(diagnostics.get("speaker_runs", []), decisions, id_key="run_id"),
        "segments": _attach_segment_decisions(diagnostics.get("segments", []), decisions),
        "review_plan": review_plan,
        "decisions": list(decisions.values()),
        "manifest": manifest,
    }


@router.post("/{task_id}/speaker-review/decisions")
def save_speaker_review_decision(
    task_id: str,
    req: SpeakerReviewDecisionRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    task = _get_task(session, task_id)
    root = Path(task.output_root).resolve()
    paths = _speaker_review_paths(root)

    item_id = req.item_id.strip()
    decision = req.decision.strip()
    item_type = req.item_type.strip()
    if not item_id:
        raise HTTPException(status_code=400, detail="Decision item_id is required")
    if not item_type:
        raise HTTPException(status_code=400, detail="Decision item_type is required")
    if not decision:
        raise HTTPException(status_code=400, detail="Decision value is required")

    paths["decisions"].parent.mkdir(parents=True, exist_ok=True)
    payload = load_json(paths["decisions"]) if paths["decisions"].exists() else {}
    if not payload:
        payload = {"version": 1, "task_id": task_id, "decisions": []}

    decision_payload = {
        "item_id": item_id,
        "item_type": item_type,
        "decision": decision,
        "source_speaker_label": req.source_speaker_label,
        "target_speaker_label": req.target_speaker_label,
        "segment_ids": req.segment_ids,
        "payload": req.payload,
        "updated_at": now_iso(),
    }
    decisions = [
        row
        for row in payload.get("decisions", [])
        if not (isinstance(row, dict) and str(row.get("item_id") or "") == item_id)
    ]
    decisions.append(decision_payload)
    payload["version"] = 1
    payload["task_id"] = task_id
    payload["updated_at"] = now_iso()
    payload["decision_count"] = len(decisions)
    payload["decisions"] = decisions
    write_json(payload, paths["decisions"])

    return {
        "ok": True,
        "item_id": item_id,
        "decision": decision,
        "path": _relative_path(paths["decisions"], root),
        "decision_count": len(decisions),
    }


@router.post("/{task_id}/speaker-review/apply")
def apply_speaker_review_decisions(task_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    task = _get_task(session, task_id)
    root = Path(task.output_root).resolve()
    paths = _speaker_review_paths(root)
    source_segments_path = _source_segments_path(paths)
    if source_segments_path is None:
        raise HTTPException(status_code=404, detail="Task A segments not found")
    if not paths["decisions"].exists():
        raise HTTPException(status_code=400, detail="No manual speaker decisions found")

    manifest = write_speaker_corrected_artifacts(
        source_segments_path=source_segments_path,
        decisions_path=paths["decisions"],
        output_segments_path=paths["corrected_segments"],
        output_srt_path=paths["corrected_srt"],
        manifest_path=paths["manifest"],
    )
    return {
        "ok": True,
        "path": _relative_path(paths["corrected_segments"], root),
        "srt_path": _relative_path(paths["corrected_srt"], root),
        "manifest_path": _relative_path(paths["manifest"], root),
        "summary": manifest.get("summary", {}),
        "applied_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def _get_task(session: Session, task_id: str) -> Task:
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


def _speaker_review_paths(root: Path) -> dict[str, Path]:
    review_dir = root / "asr-ocr-correct" / "voice"
    return {
        "review_dir": review_dir,
        "raw_segments": root / "task-a" / "voice" / "segments.zh.json",
        "text_corrected_segments": review_dir / "segments.zh.corrected.json",
        "corrected_segments": review_dir / "segments.zh.speaker-corrected.json",
        "corrected_srt": review_dir / "segments.zh.speaker-corrected.srt",
        "diagnostics": review_dir / "speaker_diagnostics.zh.json",
        "review_plan": review_dir / "speaker_review_plan.zh.json",
        "decisions": review_dir / "manual_speaker_decisions.zh.json",
        "manifest": review_dir / "speaker-review-manifest.json",
    }


def _source_segments_path(paths: dict[str, Path]) -> Path | None:
    # Speaker review edits should be based on text-corrected ASR when available,
    # but should not re-edit its own speaker-corrected output.
    for key in ("text_corrected_segments", "raw_segments"):
        path = paths[key]
        if path.exists():
            return path
    return None


def _existing_artifact_paths(paths: dict[str, Path], root: Path) -> dict[str, str]:
    return {
        key: _relative_path(path, root)
        for key, path in paths.items()
        if key != "review_dir" and path.exists()
    }


def _relative_path(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root))
    except ValueError:
        return str(path)


def _attach_speaker_decisions(
    speakers: Any,
    decisions: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in speakers if isinstance(speakers, list) else []:
        if not isinstance(raw, dict):
            continue
        row = dict(raw)
        row["decision"] = decisions.get(f"speaker:{row.get('speaker_label')}") or decisions.get(str(row.get("speaker_label") or ""))
        rows.append(row)
    return rows


def _attach_item_decisions(
    rows: Any,
    decisions: dict[str, dict[str, Any]],
    *,
    id_key: str,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for raw in rows if isinstance(rows, list) else []:
        if not isinstance(raw, dict):
            continue
        row = dict(raw)
        row["decision"] = decisions.get(str(row.get(id_key) or ""))
        result.append(row)
    return result


def _attach_segment_decisions(
    rows: Any,
    decisions: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for raw in rows if isinstance(rows, list) else []:
        if not isinstance(raw, dict):
            continue
        row = dict(raw)
        row["decision"] = decisions.get(f"segment:{row.get('segment_id')}") or decisions.get(str(row.get("segment_id") or ""))
        result.append(row)
    return result
