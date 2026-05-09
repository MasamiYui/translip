from __future__ import annotations

import json
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
from ...speaker_review.personas import (
    BULK_TEMPLATES,
    append_history,
    append_history_v2,
    apply_bulk_template,
    bind_persona,
    build_by_speaker_index,
    create_persona,
    delete_persona,
    find_name_conflict,
    find_persona,
    history_status,
    load_personas,
    merge_personas_on_speakers,
    redo_with_cursor,
    save_personas,
    snapshot_personas,
    suggest_personas,
    sync_unassigned,
    unbind_persona,
    undo_last,
    undo_with_cursor,
    update_persona,
)
from ...speaker_review.global_personas import (
    add_or_update_global,
    export_task_personas_to_global,
    global_personas_path,
    list_global,
    load_global_personas,
    remove_global,
    save_global_personas,
    smart_match_global,
)
from ..database import get_session
from ..models import Task

router = APIRouter(prefix="/api/tasks", tags=["speaker-review"])
global_personas_router = APIRouter(prefix="/api/global-personas", tags=["global-personas"])


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

    personas_payload = load_personas(review_dir)
    speaker_labels = [str(sp.get("speaker_label") or "") for sp in diagnostics.get("speakers", []) if isinstance(sp, dict)]
    sync_unassigned(personas_payload, [label for label in speaker_labels if label])
    save_personas(review_dir, personas_payload)
    persona_by_speaker = build_by_speaker_index(personas_payload)

    return {
        "task_id": task_id,
        "status": "available",
        "summary": {
            **diagnostics.get("summary", {}),
            "decision_count": len(decisions),
            "corrected_exists": paths["corrected_segments"].exists(),
            "unnamed_speaker_count": len(personas_payload.get("unassigned_bindings", [])),
        },
        "artifact_paths": _existing_artifact_paths(paths, root),
        "speakers": _enrich_speakers(
            _attach_speaker_decisions(diagnostics.get("speakers", []), decisions),
            task_id=task_id,
            persona_by_speaker=persona_by_speaker,
        ),
        "speaker_runs": _enrich_time_items(
            _attach_item_decisions(diagnostics.get("speaker_runs", []), decisions, id_key="run_id"),
            task_id=task_id,
            persona_by_speaker=persona_by_speaker,
        ),
        "segments": _enrich_time_items(
            _attach_segment_decisions(diagnostics.get("segments", []), decisions),
            task_id=task_id,
            persona_by_speaker=persona_by_speaker,
        ),
        "similarity": diagnostics.get("similarity", {}),
        "review_plan": review_plan,
        "decisions": list(decisions.values()),
        "manifest": manifest,
        "personas": {
            "items": personas_payload.get("personas", []),
            "unassigned_bindings": personas_payload.get("unassigned_bindings", []),
            "by_speaker": persona_by_speaker,
        },
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

    # Merge personas for any merge_speaker / relabel decisions before writing
    # the corrected artifacts so the injected persona_name reflects the final
    # speaker mapping.
    personas_payload = load_personas(paths["review_dir"])
    decisions_payload = load_json(paths["decisions"]) if paths["decisions"].exists() else {}
    for decision in decisions_payload.get("decisions", []):
        if not isinstance(decision, dict):
            continue
        action = str(decision.get("decision") or "")
        source_label = str(decision.get("source_speaker_label") or "")
        target_label = str(decision.get("target_speaker_label") or "")
        if not target_label and isinstance(decision.get("payload"), dict):
            target_label = str(decision["payload"].get("target_speaker") or "")
        if not source_label and isinstance(decision.get("payload"), dict):
            source_label = str(decision["payload"].get("source_speaker") or "")
        if action == "merge_speaker" and source_label and target_label:
            merge_personas_on_speakers(personas_payload, source_label, target_label)
    save_personas(paths["review_dir"], personas_payload)
    persona_index = build_by_speaker_index(personas_payload)

    manifest = write_speaker_corrected_artifacts(
        source_segments_path=source_segments_path,
        decisions_path=paths["decisions"],
        output_segments_path=paths["corrected_segments"],
        output_srt_path=paths["corrected_srt"],
        manifest_path=paths["manifest"],
        persona_index=persona_index,
    )
    return {
        "ok": True,
        "path": _relative_path(paths["corrected_segments"], root),
        "srt_path": _relative_path(paths["corrected_srt"], root),
        "manifest_path": _relative_path(paths["manifest"], root),
        "archive_path": _relative_path(archive_path, root) if archive_path else None,
        "summary": manifest.get("summary", {}),
        "personas_count": len(personas_payload.get("personas", [])),
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


# ---------- Persona endpoints ----------


class PersonaCreateRequest(BaseModel):
    name: str
    bindings: list[str] = Field(default_factory=list)
    color: str | None = None
    avatar_emoji: str | None = None
    note: str | None = None
    role: str | None = None
    gender: str | None = None
    age_hint: str | None = None
    pinned: bool | None = None
    is_target: bool | None = None
    confidence: float | None = None
    tts_voice_id: str | None = None
    tts_skip: bool | None = None
    force: bool = False


class PersonaUpdateRequest(BaseModel):
    name: str | None = None
    color: str | None = None
    avatar_emoji: str | None = None
    note: str | None = None
    aliases: list[str] | None = None
    role: str | None = None
    gender: str | None = None
    age_hint: str | None = None
    pinned: bool | None = None
    is_target: bool | None = None
    confidence: float | None = None
    tts_voice_id: str | None = None
    tts_skip: bool | None = None
    force: bool = False


class PersonaApplyPreviewRequest(BaseModel):
    persona_id: str | None = None


class PersonaBindRequest(BaseModel):
    speaker: str


class PersonaBulkRequest(BaseModel):
    template: str


class PersonaSuggestRequest(BaseModel):
    speakers: list[str] | None = None


class GlobalPersonaImportRequest(BaseModel):
    """Full payload replacement for the user-scoped global library."""

    personas: list[dict[str, Any]] = Field(default_factory=list)
    mode: str = "merge"  # "merge" | "replace"


class GlobalPersonaExportFromTaskRequest(BaseModel):
    overwrite: bool = True


class ImportFromGlobalRequest(BaseModel):
    persona_ids: list[str] = Field(default_factory=list)
    bindings_by_id: dict[str, list[str]] = Field(default_factory=dict)


class SuggestFromGlobalRequest(BaseModel):
    speakers: list[dict[str, Any]] | None = None


def _persona_context(session: Session, task_id: str) -> tuple[Task, Path, dict[str, Path], Path, dict[str, Any]]:
    task = _get_task(session, task_id)
    root = Path(task.output_root).resolve()
    paths = _speaker_review_paths(root)
    review_dir = paths["review_dir"]
    review_dir.mkdir(parents=True, exist_ok=True)
    payload = load_personas(review_dir)
    return task, root, paths, review_dir, payload


def _persona_response(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "items": payload.get("personas", []),
        "unassigned_bindings": payload.get("unassigned_bindings", []),
        "by_speaker": build_by_speaker_index(payload),
        "updated_at": payload.get("updated_at"),
    }


def _clone(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value))
    except Exception:  # pragma: no cover
        return value


@router.get("/{task_id}/speaker-review/personas")
def list_speaker_personas(task_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    _task, _root, _paths, _review_dir, payload = _persona_context(session, task_id)
    return _persona_response(payload)


@router.post("/{task_id}/speaker-review/personas")
def create_speaker_persona(
    task_id: str,
    req: PersonaCreateRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    _task, _root, _paths, review_dir, payload = _persona_context(session, task_id)
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="Persona name is required")
    if not req.force:
        conflict = find_name_conflict(payload, req.name)
        if conflict is not None:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "persona_name_conflict",
                    "existing_id": conflict.get("id"),
                    "existing_name": conflict.get("name"),
                    "message": f"Persona name '{req.name.strip()}' already exists",
                },
            )
    snapshot_personas(review_dir)
    persona = create_persona(
        payload,
        name=req.name,
        bindings=req.bindings,
        color=req.color,
        avatar_emoji=req.avatar_emoji,
        note=req.note,
        role=req.role,
        gender=req.gender,
        age_hint=req.age_hint,
        pinned=bool(req.pinned),
        is_target=bool(req.is_target),
        confidence=req.confidence,
        tts_voice_id=req.tts_voice_id,
        tts_skip=bool(req.tts_skip),
    )
    save_personas(review_dir, payload)
    append_history_v2(review_dir, "create", {"after": _clone(persona)})
    return {"ok": True, "persona": persona, "personas": _persona_response(payload)}


@router.patch("/{task_id}/speaker-review/personas/{persona_id}")
def update_speaker_persona(
    task_id: str,
    persona_id: str,
    req: PersonaUpdateRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    _task, _root, _paths, review_dir, payload = _persona_context(session, task_id)
    persona_before = find_persona(payload, persona_id)
    if persona_before is None:
        raise HTTPException(status_code=404, detail="Persona not found")
    before_snapshot = _clone(persona_before)
    updates = req.model_dump(exclude_unset=True)
    force = bool(updates.pop("force", False))
    new_name = updates.get("name")
    if new_name and not force:
        conflict = find_name_conflict(payload, str(new_name), exclude_id=persona_id)
        if conflict is not None:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "persona_name_conflict",
                    "existing_id": conflict.get("id"),
                    "existing_name": conflict.get("name"),
                    "message": f"Persona name '{str(new_name).strip()}' already exists",
                },
            )
    snapshot_personas(review_dir)
    try:
        persona = update_persona(payload, persona_id, **updates)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Persona not found") from exc
    save_personas(review_dir, payload)
    append_history_v2(review_dir, "update", {"before": before_snapshot, "after": _clone(persona)})
    return {"ok": True, "persona": persona, "personas": _persona_response(payload)}


@router.delete("/{task_id}/speaker-review/personas/{persona_id}")
def delete_speaker_persona(
    task_id: str,
    persona_id: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    _task, _root, _paths, review_dir, payload = _persona_context(session, task_id)
    persona_before = find_persona(payload, persona_id)
    if persona_before is None:
        raise HTTPException(status_code=404, detail="Persona not found")
    before_snapshot = _clone(persona_before)
    snapshot_personas(review_dir)
    delete_persona(payload, persona_id)
    save_personas(review_dir, payload)
    append_history_v2(review_dir, "delete", {"before": before_snapshot})
    return {"ok": True, "personas": _persona_response(payload)}


@router.post("/{task_id}/speaker-review/personas/{persona_id}/bind")
def bind_speaker_persona(
    task_id: str,
    persona_id: str,
    req: PersonaBindRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    _task, _root, _paths, review_dir, payload = _persona_context(session, task_id)
    persona_before = find_persona(payload, persona_id)
    if persona_before is None:
        raise HTTPException(status_code=404, detail="Persona not found")
    before_snapshot = _clone(persona_before)
    try:
        persona = bind_persona(payload, persona_id, req.speaker)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Persona not found") from exc
    snapshot_personas(review_dir)
    save_personas(review_dir, payload)
    append_history_v2(review_dir, "bind", {"before": before_snapshot, "after": _clone(persona), "speaker": req.speaker})
    return {"ok": True, "persona": persona, "personas": _persona_response(payload)}


@router.post("/{task_id}/speaker-review/personas/{persona_id}/unbind")
def unbind_speaker_persona(
    task_id: str,
    persona_id: str,
    req: PersonaBindRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    _task, _root, _paths, review_dir, payload = _persona_context(session, task_id)
    persona_before = find_persona(payload, persona_id)
    if persona_before is None:
        raise HTTPException(status_code=404, detail="Persona not found")
    before_snapshot = _clone(persona_before)
    try:
        persona = unbind_persona(payload, persona_id, req.speaker)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Persona not found") from exc
    snapshot_personas(review_dir)
    save_personas(review_dir, payload)
    append_history_v2(review_dir, "unbind", {"before": before_snapshot, "after": _clone(persona), "speaker": req.speaker})
    return {"ok": True, "persona": persona, "personas": _persona_response(payload)}


@router.post("/{task_id}/speaker-review/personas/bulk")
def bulk_create_personas(
    task_id: str,
    req: PersonaBulkRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    _task, _root, paths, review_dir, payload = _persona_context(session, task_id)
    if req.template not in BULK_TEMPLATES:
        raise HTTPException(status_code=400, detail=f"Unknown template: {req.template}")
    source_segments_path = _source_segments_path(paths)
    if source_segments_path is None:
        raise HTTPException(status_code=404, detail="Task A segments not found")
    diagnostics = build_speaker_diagnostics(
        load_json(source_segments_path),
        source_path=_relative_path(source_segments_path, paths["review_dir"].parents[1]),
    )
    speakers = [str(sp.get("speaker_label") or "") for sp in diagnostics.get("speakers", [])]
    snapshot_personas(review_dir)
    created = apply_bulk_template(payload, template=req.template, speakers=[s for s in speakers if s])
    save_personas(review_dir, payload)
    append_history_v2(review_dir, "bulk", {"after": {"created": _clone(created)}, "template": req.template})
    return {"ok": True, "created": created, "personas": _persona_response(payload)}


@router.post("/{task_id}/speaker-review/personas/suggest")
def suggest_speaker_personas(
    task_id: str,
    req: PersonaSuggestRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    _task, root, paths, _review_dir, _payload = _persona_context(session, task_id)
    source_segments_path = _source_segments_path(paths)
    if source_segments_path is None:
        raise HTTPException(status_code=404, detail="Task A segments not found")
    segments = load_json(source_segments_path).get("segments", [])
    if not isinstance(segments, list):
        segments = []
    diagnostics = build_speaker_diagnostics(
        {"segments": segments},
        source_path=_relative_path(source_segments_path, root),
    )
    speakers = req.speakers or [str(sp.get("speaker_label") or "") for sp in diagnostics.get("speakers", [])]
    speakers = [s for s in speakers if s]
    suggestions = suggest_personas(segments, speakers)
    return {"ok": True, "suggestions": suggestions}


@router.post("/{task_id}/speaker-review/personas/undo")
def undo_speaker_personas(task_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    _task, _root, _paths, review_dir, _payload = _persona_context(session, task_id)
    reverted = undo_with_cursor(review_dir)
    if reverted is None:
        # Fall back to legacy single-step undo for backwards compat
        reverted = undo_last(review_dir)
    payload = load_personas(review_dir)
    return {
        "ok": True,
        "reverted": reverted,
        "personas": _persona_response(payload),
        "history": history_status(review_dir),
    }


@router.post("/{task_id}/speaker-review/personas/redo")
def redo_speaker_personas(task_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    _task, _root, _paths, review_dir, _payload = _persona_context(session, task_id)
    replayed = redo_with_cursor(review_dir)
    payload = load_personas(review_dir)
    return {
        "ok": True,
        "replayed": replayed,
        "personas": _persona_response(payload),
        "history": history_status(review_dir),
    }


@router.get("/{task_id}/speaker-review/personas/history")
def get_speaker_personas_history(task_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    _task, _root, _paths, review_dir, _payload = _persona_context(session, task_id)
    return {"ok": True, "history": history_status(review_dir)}


@router.post("/{task_id}/speaker-review/apply-preview")
def preview_speaker_review_apply(
    task_id: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Return a diff preview of what `apply` will change without writing artifacts.

    The preview shows: per-speaker counts, persona attribution stats, and a
    sample of segments whose persona_name will change.
    """
    task = _get_task(session, task_id)
    root = Path(task.output_root).resolve()
    paths = _speaker_review_paths(root)
    source_segments_path = _source_segments_path(paths)
    if source_segments_path is None:
        raise HTTPException(status_code=404, detail="Task A segments not found")

    personas_payload = load_personas(paths["review_dir"])
    persona_index = build_by_speaker_index(personas_payload)
    decisions_payload = (
        load_json(paths["decisions"]) if paths["decisions"].exists() else {"decisions": []}
    )
    decisions = [d for d in decisions_payload.get("decisions", []) if isinstance(d, dict)]

    source_segments = load_json(source_segments_path).get("segments", [])
    if not isinstance(source_segments, list):
        source_segments = []

    # Build a map: source_speaker_label -> target_speaker_label (for merge_speaker)
    merges: dict[str, str] = {}
    for d in decisions:
        if str(d.get("decision") or "") == "merge_speaker":
            src = str(d.get("source_speaker_label") or "")
            tgt = str(d.get("target_speaker_label") or "")
            if not tgt and isinstance(d.get("payload"), dict):
                tgt = str(d["payload"].get("target_speaker") or "")
            if not src and isinstance(d.get("payload"), dict):
                src = str(d["payload"].get("source_speaker") or "")
            if src and tgt:
                merges[src] = tgt

    changes: list[dict[str, Any]] = []
    counts_by_persona: dict[str, int] = {}
    counts_total = 0
    unassigned = 0
    for seg in source_segments:
        if not isinstance(seg, dict):
            continue
        counts_total += 1
        original_speaker = str(seg.get("speaker") or seg.get("speaker_label") or "")
        new_speaker = merges.get(original_speaker, original_speaker)
        original_persona = persona_index.get(original_speaker, {}) if original_speaker else {}
        new_persona = persona_index.get(new_speaker, {}) if new_speaker else {}
        new_persona_name = new_persona.get("name") or new_speaker or "(unassigned)"
        if new_persona.get("id"):
            counts_by_persona[new_persona_name] = counts_by_persona.get(new_persona_name, 0) + 1
        else:
            unassigned += 1
        if (
            original_speaker != new_speaker
            or original_persona.get("name") != new_persona.get("name")
        ):
            if len(changes) < 50:
                changes.append(
                    {
                        "segment_id": seg.get("id"),
                        "start": seg.get("start"),
                        "end": seg.get("end"),
                        "original_speaker": original_speaker,
                        "new_speaker": new_speaker,
                        "original_persona": original_persona.get("name"),
                        "new_persona": new_persona.get("name"),
                    }
                )

    return {
        "ok": True,
        "summary": {
            "total_segments": counts_total,
            "changed_segments": len(changes),
            "unassigned_segments": unassigned,
            "personas_used": counts_by_persona,
            "merges": merges,
        },
        "sample_changes": changes,
    }


# ---------- Global persona library (shared across tasks) ----------


@global_personas_router.get("")
def list_global_personas_route() -> dict[str, Any]:
    payload = load_global_personas()
    return {
        "ok": True,
        "path": str(global_personas_path()),
        "personas": list_global(payload),
        "updated_at": payload.get("updated_at"),
        "version": payload.get("version", 1),
    }


@global_personas_router.post("/import")
def import_global_personas_route(req: GlobalPersonaImportRequest) -> dict[str, Any]:
    """Bulk insert/replace personas in the global library."""
    mode = (req.mode or "merge").lower()
    if mode not in ("merge", "replace"):
        raise HTTPException(status_code=400, detail="mode must be 'merge' or 'replace'")
    if mode == "replace":
        payload: dict[str, Any] = {"version": 1, "personas": []}
    else:
        payload = load_global_personas()
    accepted = 0
    skipped = 0
    for persona in req.personas:
        if not isinstance(persona, dict):
            skipped += 1
            continue
        try:
            add_or_update_global(payload, persona, overwrite=True)
            accepted += 1
        except ValueError:
            skipped += 1
    save_global_personas(payload)
    return {
        "ok": True,
        "accepted": accepted,
        "skipped": skipped,
        "total": len(payload.get("personas", [])),
        "personas": list_global(payload),
    }


@global_personas_router.delete("/{persona_id}")
def delete_global_persona_route(persona_id: str) -> dict[str, Any]:
    payload = load_global_personas()
    removed = remove_global(payload, persona_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Global persona not found")
    save_global_personas(payload)
    return {"ok": True, "personas": list_global(payload)}


@router.post("/{task_id}/speaker-review/global-personas/export-from-task", tags=["global-personas"])
def export_task_personas_to_global_route(
    task_id: str,
    req: GlobalPersonaExportFromTaskRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Push all personas in this task to the user-level global library."""
    _task, _root, _paths, _review_dir, payload = _persona_context(session, task_id)
    result = export_task_personas_to_global(payload, overwrite=bool(req.overwrite))
    return {"ok": True, **result}


@router.post("/{task_id}/speaker-review/personas/import-from-global", tags=["global-personas"])
def import_personas_from_global_route(
    task_id: str,
    req: ImportFromGlobalRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Import a selection of global personas into the current task payload."""
    _task, _root, _paths, review_dir, payload = _persona_context(session, task_id)
    global_payload = load_global_personas()
    imported: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    snapshot_personas(review_dir)
    for pid in req.persona_ids:
        g = next((p for p in global_payload.get("personas", []) if str(p.get("id")) == str(pid)), None)
        if g is None:
            continue
        bindings = req.bindings_by_id.get(pid) or req.bindings_by_id.get(str(pid)) or []
        name = str(g.get("name") or "").strip()
        if not name:
            continue
        conflict = find_name_conflict(payload, name)
        if conflict is not None:
            conflicts.append({
                "persona_id": pid,
                "name": name,
                "existing_id": conflict.get("id"),
            })
            continue
        persona = create_persona(
            payload,
            name=name,
            bindings=list(bindings),
            color=g.get("color"),
            avatar_emoji=g.get("avatar_emoji"),
            note=g.get("note"),
            role=g.get("role"),
            gender=g.get("gender"),
            age_hint=g.get("age_hint"),
            pinned=bool(g.get("pinned", False)),
            is_target=bool(g.get("is_target", False)),
            confidence=g.get("confidence"),
            tts_voice_id=g.get("tts_voice_id"),
            tts_skip=bool(g.get("tts_skip", False)),
        )
        imported.append(persona)
    if imported:
        save_personas(review_dir, payload)
        append_history_v2(
            review_dir,
            "import_from_global",
            {"after": {"imported": _clone(imported)}},
        )
    return {
        "ok": True,
        "imported": imported,
        "conflicts": conflicts,
        "personas": _persona_response(payload),
    }


@router.post("/{task_id}/speaker-review/personas/suggest-from-global", tags=["global-personas"])
def suggest_personas_from_global_route(
    task_id: str,
    req: SuggestFromGlobalRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Return global-persona candidates per speaker in the current task."""
    _task, root, paths, _review_dir, _payload = _persona_context(session, task_id)
    speakers = req.speakers or []
    if not speakers:
        source_segments_path = _source_segments_path(paths)
        if source_segments_path is not None:
            diagnostics = build_speaker_diagnostics(
                load_json(source_segments_path),
                source_path=_relative_path(source_segments_path, root),
            )
            speakers = [
                {
                    "speaker_label": str(sp.get("speaker_label") or ""),
                    "gender": sp.get("gender"),
                    "role": sp.get("role"),
                }
                for sp in diagnostics.get("speakers", [])
                if sp.get("speaker_label")
            ]
    matches = smart_match_global(speakers)
    return {"ok": True, "matches": matches}


# ---------- Helpers ----------


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


def _enrich_speakers(
    speakers: list[dict[str, Any]],
    *,
    task_id: str,
    persona_by_speaker: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
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
        if persona_by_speaker:
            persona = persona_by_speaker.get(str(row.get("speaker_label") or ""))
            if persona:
                row["persona"] = persona
        enriched.append(row)
    return enriched


def _enrich_time_items(
    rows: list[dict[str, Any]],
    *,
    task_id: str,
    persona_by_speaker: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
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
        if persona_by_speaker:
            label = str(row.get("speaker_label") or "")
            persona = persona_by_speaker.get(label)
            if persona:
                row["persona"] = persona
            prev_label = str(row.get("previous_speaker_label") or "")
            next_label = str(row.get("next_speaker_label") or "")
            prev_persona = persona_by_speaker.get(prev_label) if prev_label else None
            next_persona = persona_by_speaker.get(next_label) if next_label else None
            if prev_persona:
                row["previous_persona"] = prev_persona
            if next_persona:
                row["next_persona"] = next_persona
        enriched.append(row)
    return enriched
