from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
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
        "speakers": _enrich_speakers(
            _attach_speaker_decisions(diagnostics.get("speakers", []), decisions),
            task_id=task_id,
        ),
        "speaker_runs": _enrich_time_items(
            _attach_item_decisions(diagnostics.get("speaker_runs", []), decisions, id_key="run_id"),
            task_id=task_id,
        ),
        "segments": _enrich_time_items(
            _attach_segment_decisions(diagnostics.get("segments", []), decisions),
            task_id=task_id,
        ),
        "similarity": diagnostics.get("similarity", {}),
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

    archive_path: Path | None = None
    if paths["corrected_segments"].exists() or paths["manifest"].exists():
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        archive_path = paths["review_dir"] / "_archive" / timestamp
        archive_path.mkdir(parents=True, exist_ok=True)
        for key in ("corrected_segments", "corrected_srt", "manifest"):
            source = paths[key]
            if source.exists():
                shutil.copy2(source, archive_path / source.name)

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
        "archive_path": _relative_path(archive_path, root) if archive_path else None,
        "summary": manifest.get("summary", {}),
        "applied_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


@router.delete("/{task_id}/speaker-review/decisions/{item_id:path}")
def delete_speaker_review_decision(
    task_id: str,
    item_id: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    task = _get_task(session, task_id)
    root = Path(task.output_root).resolve()
    paths = _speaker_review_paths(root)
    if not paths["decisions"].exists():
        return {"ok": True, "removed": 0, "decision_count": 0}

    payload = load_json(paths["decisions"])
    decisions = [
        row
        for row in payload.get("decisions", [])
        if not (isinstance(row, dict) and str(row.get("item_id") or "") == item_id)
    ]
    removed = len(payload.get("decisions", [])) - len(decisions)
    payload["decisions"] = decisions
    payload["updated_at"] = now_iso()
    payload["decision_count"] = len(decisions)
    write_json(payload, paths["decisions"])
    return {
        "ok": True,
        "removed": removed,
        "decision_count": len(decisions),
    }


@router.get("/{task_id}/speaker-review/similarity")
def get_speaker_similarity(task_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    task = _get_task(session, task_id)
    root = Path(task.output_root).resolve()
    paths = _speaker_review_paths(root)
    source_segments_path = _source_segments_path(paths)
    if source_segments_path is None:
        raise HTTPException(status_code=404, detail="Task A segments not found")
    diagnostics = build_speaker_diagnostics(
        load_json(source_segments_path),
        source_path=_relative_path(source_segments_path, root),
    )
    return diagnostics.get("similarity", {"labels": [], "matrix": [], "threshold_suggest_merge": 0.55})


@router.get("/{task_id}/speaker-review/speakers/{label}/reference-clips")
def get_speaker_reference_clips(
    task_id: str,
    label: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    task = _get_task(session, task_id)
    root = Path(task.output_root).resolve()
    paths = _speaker_review_paths(root)
    source_segments_path = _source_segments_path(paths)
    if source_segments_path is None:
        raise HTTPException(status_code=404, detail="Task A segments not found")
    diagnostics = build_speaker_diagnostics(
        load_json(source_segments_path),
        source_path=_relative_path(source_segments_path, root),
    )
    for speaker in diagnostics.get("speakers", []):
        if str(speaker.get("speaker_label") or "") == label:
            clips = [
                {**clip, "url": _audio_stream_url(task_id, float(clip.get("start") or 0.0), float(clip.get("end") or 0.0))}
                for clip in speaker.get("reference_clips", [])
            ]
            return {
                "speaker_label": label,
                "clips": clips,
                "best_clip_id": speaker.get("best_reference_clip_id"),
            }
    raise HTTPException(status_code=404, detail=f"Speaker {label} not found")


@router.get("/{task_id}/speaker-review/audio")
def stream_speaker_review_audio(
    task_id: str,
    request: Request,
    start: float = 0.0,
    end: float | None = None,
    session: Session = Depends(get_session),
) -> Response:
    task = _get_task(session, task_id)
    root = Path(task.output_root).resolve()
    audio_path = _resolve_audio_path(root)
    if audio_path is None:
        # Fallback: synthesize a short silent WAV so the UI stays functional even
        # when real audio assets are missing. This keeps the review workflow usable
        # on partial or mocked datasets.
        duration = max(0.1, (end or start + 1.0) - start)
        return Response(
            content=_synthesize_silent_wav(duration_sec=duration),
            media_type="audio/wav",
            headers={"X-Audio-Source": "synthesized-silence"},
        )

    file_size = audio_path.stat().st_size
    range_header = request.headers.get("range") or request.headers.get("Range")
    range_match = re.match(r"bytes=(\d+)-(\d*)", range_header or "")
    if range_match:
        range_start = int(range_match.group(1))
        range_end_text = range_match.group(2)
        range_end = int(range_end_text) if range_end_text else file_size - 1
        range_end = min(range_end, file_size - 1)
        length = max(0, range_end - range_start + 1)

        def _iter_range():
            with audio_path.open("rb") as handle:
                handle.seek(range_start)
                remaining = length
                chunk_size = 64 * 1024
                while remaining > 0:
                    chunk = handle.read(min(chunk_size, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        headers = {
            "Content-Range": f"bytes {range_start}-{range_end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(length),
            "X-Audio-Path": _relative_path(audio_path, root),
        }
        return StreamingResponse(_iter_range(), status_code=206, media_type="audio/wav", headers=headers)

    def _iter_full():
        with audio_path.open("rb") as handle:
            while True:
                chunk = handle.read(64 * 1024)
                if not chunk:
                    break
                yield chunk

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(file_size),
        "X-Audio-Path": _relative_path(audio_path, root),
    }
    return StreamingResponse(_iter_full(), media_type="audio/wav", headers=headers)


def _resolve_audio_path(root: Path) -> Path | None:
    candidates = [
        root / "stage1" / "voice" / "voice.wav",
        root / "task-a" / "voice" / "voice.wav",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _audio_stream_url(task_id: str, start: float, end: float) -> str:
    return f"/api/tasks/{task_id}/speaker-review/audio?start={start:.3f}&end={end:.3f}"


def _synthesize_silent_wav(duration_sec: float, sample_rate: int = 16000) -> bytes:
    import struct

    duration_sec = max(0.1, min(duration_sec, 30.0))
    frame_count = int(duration_sec * sample_rate)
    data_size = frame_count * 2
    header = (
        b"RIFF"
        + struct.pack("<I", 36 + data_size)
        + b"WAVE"
        + b"fmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16)
        + b"data"
        + struct.pack("<I", data_size)
    )
    return header + b"\x00" * data_size


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


def _enrich_speakers(speakers: list[dict[str, Any]], *, task_id: str) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for row in speakers:
        clips = list(row.get("reference_clips") or [])
        for clip in clips:
            clip["url"] = _audio_stream_url(
                task_id,
                float(clip.get("start") or 0.0),
                float(clip.get("end") or 0.0),
            )
        row["reference_clips"] = clips
        enriched.append(row)
    return enriched


def _enrich_time_items(rows: list[dict[str, Any]], *, task_id: str) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for row in rows:
        start = float(row.get("start") or 0.0)
        end = float(row.get("end") or start + 1.0)
        if end <= start:
            end = start + 0.5
        row["audio_url"] = _audio_stream_url(task_id, start, end)
        prev_start = max(0.0, start - 1.5)
        if prev_start < start:
            row["prev_context_url"] = _audio_stream_url(task_id, prev_start, start)
        else:
            row["prev_context_url"] = None
        row["next_context_url"] = _audio_stream_url(task_id, end, end + 1.5)
        enriched.append(row)
    return enriched
