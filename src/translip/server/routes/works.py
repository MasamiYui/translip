"""Works (TV shows, movies, etc.) management routes.

These endpoints manage `~/.translip/works.json` — a structured registry of works
(作品) used to disambiguate personas across productions.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session

from ..database import get_session
from ..models import Task
from ...speaker_review.work_inference import infer_work_from_task
from ...speaker_review.works import (
    add_custom_work_type,
    create_work,
    delete_work,
    find_work,
    list_personas_in_work,
    list_works,
    list_work_types,
    load_works,
    move_personas_to_work,
    remove_custom_work_type,
    save_works,
    update_work,
    works_path,
)

router = APIRouter(prefix="/api/works", tags=["works"])
work_types_router = APIRouter(prefix="/api/work-types", tags=["work-types"])


class WorkCreateRequest(BaseModel):
    title: str
    type: str = Field(default="other")
    year: Optional[int] = None
    aliases: list[str] = Field(default_factory=list)
    cover_emoji: Optional[str] = None
    color: Optional[str] = None
    note: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    default_tts_voice_map: dict[str, Any] = Field(default_factory=dict)
    # External-source fields (optional, set when importing from TMDb / Wikidata)
    external_refs: Optional[dict[str, Any]] = None
    metadata: Optional[dict[str, Any]] = None
    poster_path: Optional[str] = None
    backdrop_path: Optional[str] = None
    synopsis: Optional[str] = None
    synopsis_lang: Optional[str] = None
    origin_country: Optional[list[str]] = None
    original_title: Optional[str] = None
    cast_snapshot: Optional[list[dict[str, Any]]] = None
    external_synced_at: Optional[str] = None
    external_source: Optional[str] = None


class WorkPatchRequest(BaseModel):
    title: Optional[str] = None
    type: Optional[str] = None
    year: Optional[int] = None
    aliases: Optional[list[str]] = None
    cover_emoji: Optional[str] = None
    color: Optional[str] = None
    note: Optional[str] = None
    tags: Optional[list[str]] = None
    default_tts_voice_map: Optional[dict[str, Any]] = None
    external_refs: Optional[dict[str, Any]] = None
    metadata: Optional[dict[str, Any]] = None
    poster_path: Optional[str] = None
    backdrop_path: Optional[str] = None
    synopsis: Optional[str] = None
    synopsis_lang: Optional[str] = None
    origin_country: Optional[list[str]] = None
    original_title: Optional[str] = None
    cast_snapshot: Optional[list[dict[str, Any]]] = None
    external_synced_at: Optional[str] = None
    external_source: Optional[str] = None


class CustomTypeRequest(BaseModel):
    key: str
    label_zh: str
    label_en: str


class MovePersonasRequest(BaseModel):
    persona_ids: list[str]


@router.get("")
def list_works_route(q: Optional[str] = None) -> dict[str, Any]:
    payload = load_works()
    works = list_works(payload)
    if q:
        needle = q.strip().lower()
        if needle:
            works = [
                w
                for w in works
                if needle in (w.get("title") or "").lower()
                or any(needle in (a or "").lower() for a in (w.get("aliases") or []))
            ]
    counts = _persona_counts_by_work(works)
    for w in works:
        w["persona_count"] = counts.get(str(w.get("id")), 0)
    return {
        "ok": True,
        "path": str(works_path()),
        "works": works,
        "unassigned_count": counts.get("__unassigned__", 0),
        "updated_at": payload.get("updated_at"),
        "version": payload.get("version", 1),
    }


@router.post("")
def create_work_route(req: WorkCreateRequest) -> dict[str, Any]:
    payload = load_works()
    try:
        work = create_work(payload, req.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    save_works(payload)
    return {"ok": True, "work": work}


@router.patch("/{work_id}")
def update_work_route(work_id: str, req: WorkPatchRequest) -> dict[str, Any]:
    payload = load_works()
    try:
        work = update_work(payload, work_id, req.model_dump(exclude_unset=True))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"work not found: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    save_works(payload)
    return {"ok": True, "work": work}


@router.delete("/{work_id}")
def delete_work_route(
    work_id: str,
    reassign_to: Optional[str] = Query(default=None),
    cascade: bool = Query(default=False),
) -> dict[str, Any]:
    payload = load_works()
    try:
        result = delete_work(
            payload,
            work_id,
            reassign_to=reassign_to,
            cascade=cascade,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"work not found: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    save_works(payload)
    return {"ok": True, **result}


@router.get("/{work_id}/personas")
def list_personas_in_work_route(work_id: str) -> dict[str, Any]:
    payload = load_works()
    if work_id != "__unassigned__" and find_work(payload, work_id) is None:
        raise HTTPException(status_code=404, detail="work not found")
    target = None if work_id == "__unassigned__" else work_id
    personas = list_personas_in_work(target)
    return {"ok": True, "work_id": target, "personas": personas}


@router.post("/{work_id}/personas/move")
def move_personas_route(work_id: str, req: MovePersonasRequest) -> dict[str, Any]:
    target = None if work_id == "__unassigned__" else work_id
    try:
        result = move_personas_to_work(req.persona_ids, target)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, **result}


# ---- Work types ----


@work_types_router.get("")
def list_work_types_route() -> dict[str, Any]:
    return {"ok": True, "types": list_work_types()}


@work_types_router.post("")
def add_custom_work_type_route(req: CustomTypeRequest) -> dict[str, Any]:
    try:
        entry = add_custom_work_type(req.key, req.label_zh, req.label_en)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "type": entry, "types": list_work_types()}


@work_types_router.delete("/{key}")
def delete_custom_work_type_route(key: str) -> dict[str, Any]:
    try:
        removed = remove_custom_work_type(key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not removed:
        raise HTTPException(status_code=404, detail="custom type not found")
    return {"ok": True, "types": list_work_types()}


# ---- Task ↔ Work binding ----


class BindWorkRequest(BaseModel):
    work_id: Optional[str] = None
    episode_label: Optional[str] = None


@router.post("/bind-task/{task_id}")
def bind_task_to_work_route(
    task_id: str,
    req: BindWorkRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    if req.work_id:
        works_payload = load_works()
        if find_work(works_payload, req.work_id) is None:
            raise HTTPException(status_code=404, detail=f"work '{req.work_id}' not found")
    task.work_id = req.work_id
    task.episode_label = req.episode_label
    session.add(task)
    session.commit()
    session.refresh(task)
    return {
        "ok": True,
        "task": {
            "id": task.id,
            "name": task.name,
            "work_id": task.work_id,
            "episode_label": task.episode_label,
        },
    }


@router.post("/infer-from-task/{task_id}")
def infer_work_from_task_route(
    task_id: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    works_payload = load_works()
    candidates = infer_work_from_task(
        task_name=task.name or "",
        input_path=task.input_path,
        works=list_works(works_payload),
    )
    return {
        "ok": True,
        "task_id": task_id,
        "candidates": candidates,
    }


@router.post("/auto-bind-task/{task_id}")
def auto_bind_task_route(
    task_id: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Run inference and, if the top candidate's score >= 0.85, bind it automatically."""
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    works_payload = load_works()
    candidates = infer_work_from_task(
        task_name=task.name or "",
        input_path=task.input_path,
        works=list_works(works_payload),
    )
    if not candidates:
        return {"ok": True, "bound": False, "candidates": []}
    top = candidates[0]
    if top.get("work_id") and float(top.get("score") or 0) >= 0.85:
        task.work_id = str(top["work_id"])
        task.episode_label = top.get("episode_label")
        session.add(task)
        session.commit()
        session.refresh(task)
        return {
            "ok": True,
            "bound": True,
            "work_id": task.work_id,
            "episode_label": task.episode_label,
            "candidates": candidates,
        }
    return {"ok": True, "bound": False, "candidates": candidates}


# ---- TMDb Integration ----


class TMDbSearchRequest(BaseModel):
    query: str
    media_type: Optional[str] = None


class TMDbImportRequest(BaseModel):
    tmdb_id: int
    media_type: str


@router.get("/tmdb/search")
def tmdb_search(q: str, media_type: Optional[str] = Query(default=None)) -> dict[str, Any]:
    from ...speaker_review.works_providers.tmdb import get_tmdb_provider

    provider = get_tmdb_provider()
    if not provider.config.has_credentials():
        return {"ok": False, "error": "TMDb API key not configured", "results": []}
    
    results = provider.search(q, media_type)
    return {"ok": True, "results": results}


@router.get("/tmdb/{tmdb_id}")
def tmdb_get_details(
    tmdb_id: int,
    media_type: str = Query(default="movie"),
) -> dict[str, Any]:
    from ...speaker_review.works_providers.tmdb import get_tmdb_provider

    provider = get_tmdb_provider()
    if not provider.config.has_credentials():
        return {"ok": False, "error": "TMDb API key not configured"}
    
    details = provider.get_details(tmdb_id, media_type)
    if not details:
        return {"ok": False, "error": "Failed to fetch details"}
    
    return {"ok": True, "details": details}


@router.post("/from-tmdb")
def create_work_from_tmdb(req: TMDbImportRequest) -> dict[str, Any]:
    from ...speaker_review.works_providers.tmdb import get_tmdb_provider

    provider = get_tmdb_provider()
    if not provider.config.has_credentials():
        return {"ok": False, "error": "TMDb API key not configured"}
    
    details = provider.get_details(req.tmdb_id, req.media_type)
    if not details:
        return {"ok": False, "error": "Failed to fetch TMDb details"}
    
    work_data = provider.tmdb_to_work(details)
    payload = load_works()
    
    try:
        work = create_work(payload, work_data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    
    save_works(payload)
    return {"ok": True, "work": work}


# ---- Cast Import from TMDb ----


class CastImportRequest(BaseModel):
    tmdb_ids: list[int]


class CastPreviewRequest(BaseModel):
    tmdb_id: int
    media_type: str


@router.get("/{work_id}/cast-preview")
def get_cast_preview(work_id: str, tmdb_id: int = Query(), media_type: str = Query(default="movie")) -> dict[str, Any]:
    """Preview cast members from TMDb before importing."""
    from ...speaker_review.works_providers.tmdb import get_tmdb_provider

    provider = get_tmdb_provider()
    if not provider.config.has_credentials():
        return {"ok": False, "error": "TMDb API key not configured"}
    
    details = provider.get_details(tmdb_id, media_type)
    if not details:
        return {"ok": False, "error": "Failed to fetch cast details"}
    
    payload = load_works()
    work = find_work(payload, work_id)
    if not work:
        raise HTTPException(status_code=404, detail="Work not found")
    
    cast = []
    for member in details.get("cast", []):
        cast.append({
            "tmdb_id": member.get("id"),
            "actor_name": member.get("actor_name", ""),
            "character_name": member.get("character_name", ""),
            "profile_path": member.get("profile_path"),
            "profile_url": provider.get_poster_url(member.get("profile_path", "")),
            "order": member.get("order", 0),
        })
    
    return {"ok": True, "cast": cast[:30]}


@router.post("/{work_id}/import-cast")
def import_cast_to_character_library(work_id: str, req: CastImportRequest) -> dict[str, Any]:
    """Import selected cast members from TMDb to character library."""
    from ...speaker_review.global_personas import create_persona, save_global_personas, load_global_personas
    from ...speaker_review.works_providers.tmdb import get_tmdb_provider

    provider = get_tmdb_provider()
    if not provider.config.has_credentials():
        return {"ok": False, "error": "TMDb API key not configured"}
    
    payload = load_works()
    work = find_work(payload, work_id)
    if not work:
        raise HTTPException(status_code=404, detail="Work not found")
    
    external_refs = work.get("external_refs", {})
    tmdb_type = external_refs.get("tmdb_type", "movie")
    
    details = provider.get_details(int(external_refs.get("tmdb_id", 0)), tmdb_type)
    if not details:
        return {"ok": False, "error": "Failed to fetch cast details"}
    
    global_payload = load_global_personas()
    
    imported = []
    skipped = []
    cast_by_id = {str(m.get("id")): m for m in details.get("cast", [])}
    
    for tmdb_id in req.tmdb_ids:
        member = cast_by_id.get(str(tmdb_id))
        if not member:
            skipped.append({"tmdb_id": tmdb_id, "reason": "not found in cast"})
            continue
        
        actor_name = member.get("actor_name", "")
        character_name = member.get("character_name", "")
        
        if not actor_name and not character_name:
            skipped.append({"tmdb_id": tmdb_id, "reason": "no name provided"})
            continue
        
        persona_data = {
            "name": character_name or actor_name,
            "work_id": work_id,
            "actor_name": actor_name if actor_name != character_name else None,
            "role": None,
            "gender": None,
            "avatar_emoji": None,
            "color": None,
        }
        
        try:
            persona = create_persona(global_payload, persona_data)
            imported.append({
                "persona_id": persona["id"],
                "name": persona["name"],
                "actor_name": persona.get("actor_name"),
            })
        except ValueError as exc:
            skipped.append({"tmdb_id": tmdb_id, "reason": str(exc)})
    
    save_global_personas(global_payload)
    
    return {
        "ok": True,
        "imported": imported,
        "skipped": skipped,
        "work_id": work_id,
    }


# ---- Helpers ----


def _persona_counts_by_work(works: list[dict[str, Any]]) -> dict[str, int]:
    """Return a map of work_id -> persona_count, plus '__unassigned__' key."""
    from ...speaker_review.global_personas import load_global_personas

    global_payload = load_global_personas()
    counts: dict[str, int] = {}
    for p in global_payload.get("personas", []) or []:
        wid = str(p.get("work_id") or "").strip()
        if not wid:
            counts["__unassigned__"] = counts.get("__unassigned__", 0) + 1
        else:
            counts[wid] = counts.get(wid, 0) + 1
    return counts
