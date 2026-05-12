"""Works (TV shows, movies, etc.) management routes.

These endpoints manage `~/.translip/works.json` — a structured registry of works
(作品) used to disambiguate personas across productions.
"""

from __future__ import annotations

import uuid
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
    counts = _ensure_tmdb_cast_snapshots_imported(payload, works)
    if q:
        needle = q.strip().lower()
        if needle:
            works = [
                w
                for w in works
                if needle in (w.get("title") or "").lower()
                or any(needle in (a or "").lower() for a in (w.get("aliases") or []))
            ]
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
    from ...speaker_review.diagnostics import now_iso
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

    cast_for_import = (
        [m for m in work.get("cast_snapshot", []) if isinstance(m, dict)]
        or [m for m in details.get("cast", []) if isinstance(m, dict)]
    )
    imported_cast, skipped_cast = _import_tmdb_cast_members(
        work_id=str(work["id"]),
        cast=cast_for_import,
    )
    metadata = work.get("metadata") if isinstance(work.get("metadata"), dict) else {}
    metadata["cast_auto_imported_at"] = now_iso()
    metadata["cast_auto_imported_count"] = len(imported_cast)
    work["metadata"] = metadata
    work["persona_count"] = len(imported_cast)
    save_works(payload)
    return {
        "ok": True,
        "work": work,
        "imported_cast": imported_cast,
        "skipped_cast": skipped_cast,
    }


# ---- Cast Import from TMDb ----


class CastImportRequest(BaseModel):
    tmdb_ids: list[int]


class CastPreviewRequest(BaseModel):
    tmdb_id: int
    media_type: str


def _normalize_tmdb_person_id(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.startswith("tmdb:"):
        text = text.split(":", 1)[1].strip()
    return text or None


def _cast_member_tmdb_id(member: dict[str, Any]) -> str | None:
    for key in ("id", "tmdb_id", "external_person_id"):
        normalized = _normalize_tmdb_person_id(member.get(key))
        if normalized:
            return normalized
    return None


def _normalize_cast_name(value: Any) -> str:
    return str(value or "").strip()


def _tmdb_profile_url(profile_path: Any) -> str | None:
    value = _normalize_cast_name(profile_path)
    if not value:
        return None
    if value.startswith("http://") or value.startswith("https://"):
        return value
    if value.startswith("/"):
        return f"https://image.tmdb.org/t/p/w342{value}"
    return value


def _cast_member_avatar_url(member: dict[str, Any]) -> str | None:
    for key in ("avatar_url", "profile_url"):
        value = _tmdb_profile_url(member.get(key))
        if value:
            return value
    return _tmdb_profile_url(member.get("profile_path"))


def _find_existing_cast_persona(
    global_payload: dict[str, Any],
    *,
    work_id: str,
    tmdb_person_id: str | None,
    name: str,
    actor_name: str,
) -> dict[str, Any] | None:
    def norm(value: Any) -> str:
        return str(value or "").strip().lower()

    for persona in global_payload.get("personas", []) or []:
        if str(persona.get("work_id") or "") != str(work_id):
            continue
        refs = (
            persona.get("external_refs")
            if isinstance(persona.get("external_refs"), dict)
            else {}
        )
        existing_tmdb_id = _normalize_tmdb_person_id(
            refs.get("tmdb_person_id") or refs.get("tmdb_id") or refs.get("external_person_id")
        )
        if tmdb_person_id and existing_tmdb_id == tmdb_person_id:
            return persona
        if (
            norm(persona.get("name")) == norm(name)
            and norm(persona.get("actor_name")) == norm(actor_name)
        ):
            return persona
    return None


def _upsert_tmdb_cast_persona(
    global_payload: dict[str, Any],
    *,
    work_id: str,
    member: dict[str, Any],
) -> dict[str, Any]:
    from ...speaker_review.diagnostics import now_iso
    from ...speaker_review.personas import next_color

    actor_name = _normalize_cast_name(member.get("actor_name") or member.get("actor"))
    character_name = _normalize_cast_name(member.get("character_name") or member.get("character"))
    name = character_name or actor_name
    if not name:
        raise ValueError("no name provided")

    tmdb_person_id = _cast_member_tmdb_id(member)
    external_refs: dict[str, Any] = {}
    if tmdb_person_id:
        external_refs["tmdb_person_id"] = tmdb_person_id
    if member.get("credit_id"):
        external_refs["tmdb_credit_id"] = str(member["credit_id"])
    profile_path = _normalize_cast_name(member.get("profile_path"))
    if profile_path:
        external_refs["tmdb_profile_path"] = profile_path

    avatar_url = _cast_member_avatar_url(member)

    now = now_iso()
    existing = _find_existing_cast_persona(
        global_payload,
        work_id=work_id,
        tmdb_person_id=tmdb_person_id,
        name=name,
        actor_name=actor_name,
    )
    if existing is not None:
        existing["name"] = name
        existing["work_id"] = work_id
        if actor_name and actor_name != name:
            existing["actor_name"] = actor_name
        else:
            existing.pop("actor_name", None)
        if external_refs:
            refs = (
                existing.get("external_refs")
                if isinstance(existing.get("external_refs"), dict)
                else {}
            )
            existing["external_refs"] = {**refs, **external_refs}
        if avatar_url:
            existing["avatar_url"] = avatar_url
        existing["updated_at"] = now
        return existing

    persona: dict[str, Any] = {
        "id": f"persona_{uuid.uuid4().hex[:10]}",
        "name": name,
        "aliases": [],
        "color": next_color(global_payload),
        "work_id": work_id,
        "created_at": now,
        "updated_at": now,
    }
    if actor_name and actor_name != name:
        persona["actor_name"] = actor_name
    if avatar_url:
        persona["avatar_url"] = avatar_url
    if external_refs:
        persona["external_refs"] = external_refs
    gender = _normalize_cast_name(member.get("gender"))
    if gender:
        persona["gender"] = gender

    global_payload.setdefault("personas", []).append(persona)
    return persona


def _persona_import_summary(persona: dict[str, Any]) -> dict[str, Any]:
    return {
        "persona_id": persona["id"],
        "name": persona["name"],
        "actor_name": persona.get("actor_name"),
        "avatar_url": persona.get("avatar_url"),
    }


def _import_tmdb_cast_members(
    *,
    work_id: str,
    cast: list[dict[str, Any]],
    selected_tmdb_ids: list[int] | None = None,
    create_missing: bool = True,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    from ...speaker_review.global_personas import load_global_personas, save_global_personas

    global_payload = load_global_personas()
    imported: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    if selected_tmdb_ids is None:
        members = cast
    else:
        selected = {_normalize_tmdb_person_id(tmdb_id) for tmdb_id in selected_tmdb_ids}
        selected.discard(None)
        cast_by_id = {
            tmdb_id: member
            for member in cast
            if (tmdb_id := _cast_member_tmdb_id(member))
        }
        members = []
        for raw_id in selected_tmdb_ids:
            tmdb_id = _normalize_tmdb_person_id(raw_id)
            member = cast_by_id.get(tmdb_id or "")
            if member is None:
                skipped.append({"tmdb_id": raw_id, "reason": "not found in cast"})
                continue
            members.append(member)

    for member in members:
        tmdb_id = _cast_member_tmdb_id(member)
        try:
            if not create_missing:
                member_name = _normalize_cast_name(
                    member.get("character_name")
                    or member.get("character")
                    or member.get("actor_name")
                    or member.get("actor")
                )
                existing = _find_existing_cast_persona(
                    global_payload,
                    work_id=work_id,
                    tmdb_person_id=tmdb_id,
                    name=member_name,
                    actor_name=_normalize_cast_name(member.get("actor_name") or member.get("actor")),
                )
                if existing is None:
                    skipped.append({
                        "tmdb_id": int(tmdb_id) if tmdb_id and tmdb_id.isdigit() else tmdb_id,
                        "reason": "not imported",
                    })
                    continue
            persona = _upsert_tmdb_cast_persona(global_payload, work_id=work_id, member=member)
            imported.append(_persona_import_summary(persona))
        except ValueError as exc:
            skipped.append({
                "tmdb_id": int(tmdb_id) if tmdb_id and tmdb_id.isdigit() else tmdb_id,
                "reason": str(exc),
            })

    if imported:
        save_global_personas(global_payload)
    return imported, skipped


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
    from ...speaker_review.works_providers.tmdb import get_tmdb_provider

    provider = get_tmdb_provider()
    if not provider.config.has_credentials():
        return {"ok": False, "error": "TMDb API key not configured"}
    
    payload = load_works()
    work = find_work(payload, work_id)
    if not work:
        raise HTTPException(status_code=404, detail="Work not found")
    
    external_refs = work.get("external_refs", {})
    tmdb_id = external_refs.get("tmdb_id")
    if not tmdb_id:
        return {"ok": False, "error": "Work is not linked to TMDb"}
    tmdb_type = external_refs.get("tmdb_media_type") or external_refs.get("tmdb_type") or "movie"

    details = provider.get_details(int(tmdb_id), str(tmdb_type))
    if not details:
        return {"ok": False, "error": "Failed to fetch cast details"}

    imported, skipped = _import_tmdb_cast_members(
        work_id=work_id,
        cast=[m for m in details.get("cast", []) if isinstance(m, dict)],
        selected_tmdb_ids=req.tmdb_ids,
    )
    
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


def _ensure_tmdb_cast_snapshots_imported(
    payload: dict[str, Any],
    works: list[dict[str, Any]],
) -> dict[str, int]:
    """One-time migration for older TMDb imports that saved cast_snapshot only."""
    from ...speaker_review.diagnostics import now_iso

    counts = _persona_counts_by_work(works)
    changed = False

    for work in works:
        work_id = str(work.get("id") or "")
        if not work_id:
            continue

        metadata = work.get("metadata") if isinstance(work.get("metadata"), dict) else {}
        external_refs = work.get("external_refs") if isinstance(work.get("external_refs"), dict) else {}
        is_tmdb_work = bool(external_refs.get("tmdb_id") or metadata.get("source") == "tmdb")
        cast_snapshot = [m for m in (work.get("cast_snapshot") or []) if isinstance(m, dict)]
        if not is_tmdb_work or not cast_snapshot:
            continue

        current_count = counts.get(work_id, 0)
        if metadata.get("cast_auto_imported_at"):
            _import_tmdb_cast_members(
                work_id=work_id,
                cast=cast_snapshot,
                create_missing=False,
            )
            continue

        if current_count > 0:
            _import_tmdb_cast_members(
                work_id=work_id,
                cast=cast_snapshot,
                create_missing=False,
            )
            metadata["cast_auto_imported_at"] = now_iso()
            metadata["cast_auto_imported_count"] = current_count
            work["metadata"] = metadata
            changed = True
            continue

        imported, skipped = _import_tmdb_cast_members(work_id=work_id, cast=cast_snapshot)
        if imported or skipped:
            metadata["cast_auto_imported_at"] = now_iso()
            metadata["cast_auto_imported_count"] = len(imported)
            work["metadata"] = metadata
            counts[work_id] = len(imported)
            changed = True

    if changed:
        save_works(payload)
    return counts
