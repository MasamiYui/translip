from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from .diagnostics import load_json, now_iso, write_json
from .global_personas import global_personas_dir, load_global_personas, save_global_personas

WORKS_FILENAME = "works.json"
WORK_TYPES_FILENAME = "work_types.json"

BUILTIN_WORK_TYPES: list[dict[str, str]] = [
    {"key": "tv", "label_zh": "电视剧", "label_en": "TV Series"},
    {"key": "movie", "label_zh": "电影", "label_en": "Movie"},
    {"key": "anime", "label_zh": "动漫", "label_en": "Anime"},
    {"key": "documentary", "label_zh": "纪录片", "label_en": "Documentary"},
    {"key": "short", "label_zh": "短片", "label_en": "Short"},
    {"key": "variety", "label_zh": "综艺", "label_en": "Variety"},
    {"key": "audiobook", "label_zh": "有声书", "label_en": "Audiobook"},
    {"key": "game", "label_zh": "游戏", "label_en": "Game"},
    {"key": "other", "label_zh": "其他", "label_en": "Other"},
]
BUILTIN_TYPE_KEYS = {t["key"] for t in BUILTIN_WORK_TYPES}

_TYPE_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


def works_path() -> Path:
    return global_personas_dir() / WORKS_FILENAME


def work_types_path() -> Path:
    return global_personas_dir() / WORK_TYPES_FILENAME


def _empty_works_payload() -> dict[str, Any]:
    return {"version": 1, "works": [], "updated_at": None}


def _empty_work_types_payload() -> dict[str, Any]:
    return {"version": 1, "custom_types": [], "updated_at": None}


def load_works() -> dict[str, Any]:
    path = works_path()
    if not path.exists():
        return _empty_works_payload()
    data = load_json(path) or {}
    if "works" not in data or not isinstance(data.get("works"), list):
        data["works"] = []
    if "version" not in data:
        data["version"] = 1
    return data


def save_works(payload: dict[str, Any]) -> Path:
    path = works_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(payload)
    payload["updated_at"] = now_iso()
    write_json(payload, path)
    return path


def load_work_types() -> dict[str, Any]:
    path = work_types_path()
    if not path.exists():
        return _empty_work_types_payload()
    data = load_json(path) or {}
    if "custom_types" not in data or not isinstance(data.get("custom_types"), list):
        data["custom_types"] = []
    if "version" not in data:
        data["version"] = 1
    return data


def save_work_types(payload: dict[str, Any]) -> Path:
    path = work_types_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(payload)
    payload["updated_at"] = now_iso()
    write_json(payload, path)
    return path


def list_work_types() -> list[dict[str, Any]]:
    """Return builtin + custom types, with `builtin` flag."""
    payload = load_work_types()
    builtin = [{**t, "builtin": True} for t in BUILTIN_WORK_TYPES]
    custom_raw = payload.get("custom_types", []) or []
    custom = []
    for t in custom_raw:
        if not isinstance(t, dict):
            continue
        key = str(t.get("key") or "").strip()
        if not key:
            continue
        custom.append(
            {
                "key": key,
                "label_zh": str(t.get("label_zh") or key),
                "label_en": str(t.get("label_en") or key),
                "builtin": False,
            }
        )
    return builtin + custom


def add_custom_work_type(key: str, label_zh: str, label_en: str) -> dict[str, Any]:
    key = (key or "").strip().lower()
    if not _TYPE_KEY_PATTERN.match(key):
        raise ValueError(
            "type key must match ^[a-z][a-z0-9_]{0,31}$ (lowercase letters/digits/underscore, start with letter)"
        )
    if key in BUILTIN_TYPE_KEYS:
        raise ValueError(f"type key '{key}' conflicts with builtin")
    payload = load_work_types()
    custom_types = payload.setdefault("custom_types", [])
    for t in custom_types:
        if str(t.get("key") or "").strip().lower() == key:
            raise ValueError(f"custom type key '{key}' already exists")
    entry = {
        "key": key,
        "label_zh": (label_zh or key).strip(),
        "label_en": (label_en or key).strip(),
        "created_at": now_iso(),
    }
    custom_types.append(entry)
    save_work_types(payload)
    return entry


def remove_custom_work_type(key: str) -> bool:
    key = (key or "").strip().lower()
    if key in BUILTIN_TYPE_KEYS:
        raise ValueError(f"cannot remove builtin type '{key}'")
    payload = load_work_types()
    custom_types = payload.get("custom_types", [])
    for idx, t in enumerate(custom_types):
        if str(t.get("key") or "").strip().lower() == key:
            custom_types.pop(idx)
            save_work_types(payload)
            return True
    return False


def _slugify(title: str) -> str:
    import unicodedata

    nf = unicodedata.normalize("NFKD", title)
    ascii_part = "".join(c for c in nf if not unicodedata.combining(c))
    ascii_part = re.sub(r"[^a-zA-Z0-9]+", "_", ascii_part).strip("_").lower()
    return ascii_part or "w"


def _new_work_id(title: str) -> str:
    digest = hashlib.sha1(f"{title}|{now_iso()}".encode("utf-8")).hexdigest()[:6]
    return f"work_{_slugify(title)[:24]}_{digest}"


def _normalize_aliases(aliases: list[str] | None) -> list[str]:
    if not aliases:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for a in aliases:
        s = (a or "").strip()
        if not s:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def list_works(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return list(payload.get("works", []))


def find_work(payload: dict[str, Any], work_id: str) -> dict[str, Any] | None:
    for w in payload.get("works", []):
        if str(w.get("id")) == str(work_id):
            return w
    return None


def find_work_by_title_or_alias(payload: dict[str, Any], title: str) -> dict[str, Any] | None:
    target = (title or "").strip().lower()
    if not target:
        return None
    for w in payload.get("works", []):
        if (w.get("title") or "").strip().lower() == target:
            return w
        for a in w.get("aliases") or []:
            if (a or "").strip().lower() == target:
                return w
    return None


def create_work(payload: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    title = (data.get("title") or "").strip()
    if not title:
        raise ValueError("title is required")
    type_key = (data.get("type") or "other").strip().lower() or "other"
    type_keys_known = {t["key"] for t in list_work_types()}
    if type_key not in type_keys_known:
        raise ValueError(f"unknown work type: {type_key}")
    if find_work_by_title_or_alias(payload, title) is not None:
        raise ValueError(f"work with title or alias '{title}' already exists")
    works = payload.setdefault("works", [])
    work = {
        "id": _new_work_id(title),
        "title": title,
        "type": type_key,
        "year": data.get("year"),
        "aliases": _normalize_aliases(data.get("aliases")),
        "cover_emoji": (data.get("cover_emoji") or "").strip() or None,
        "color": (data.get("color") or "").strip() or None,
        "note": (data.get("note") or "").strip() or None,
        "tags": list(data.get("tags") or []),
        "default_tts_voice_map": dict(data.get("default_tts_voice_map") or {}),
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    works.append(work)
    return work


def update_work(payload: dict[str, Any], work_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    work = find_work(payload, work_id)
    if work is None:
        raise KeyError(work_id)
    if "title" in patch:
        new_title = (patch.get("title") or "").strip()
        if not new_title:
            raise ValueError("title cannot be empty")
        existing = find_work_by_title_or_alias(payload, new_title)
        if existing is not None and str(existing.get("id")) != str(work_id):
            raise ValueError(f"another work already uses title or alias '{new_title}'")
        work["title"] = new_title
    if "type" in patch:
        type_key = (patch.get("type") or "other").strip().lower() or "other"
        type_keys_known = {t["key"] for t in list_work_types()}
        if type_key not in type_keys_known:
            raise ValueError(f"unknown work type: {type_key}")
        work["type"] = type_key
    if "year" in patch:
        work["year"] = patch.get("year")
    if "aliases" in patch:
        work["aliases"] = _normalize_aliases(patch.get("aliases"))
    if "cover_emoji" in patch:
        v = (patch.get("cover_emoji") or "").strip()
        work["cover_emoji"] = v or None
    if "color" in patch:
        v = (patch.get("color") or "").strip()
        work["color"] = v or None
    if "note" in patch:
        v = (patch.get("note") or "").strip()
        work["note"] = v or None
    if "tags" in patch:
        work["tags"] = list(patch.get("tags") or [])
    if "default_tts_voice_map" in patch:
        work["default_tts_voice_map"] = dict(patch.get("default_tts_voice_map") or {})
    work["updated_at"] = now_iso()
    return work


def delete_work(
    payload: dict[str, Any],
    work_id: str,
    *,
    reassign_to: str | None = None,
    cascade: bool = False,
) -> dict[str, Any]:
    """Delete a work; cascade options control persona side-effects.

    Returns a summary {"removed": work, "reassigned": n, "deleted_personas": n}.
    """
    work = find_work(payload, work_id)
    if work is None:
        raise KeyError(work_id)
    if reassign_to and not find_work(payload, reassign_to):
        raise ValueError(f"reassign_to target '{reassign_to}' not found")
    works = payload.get("works", [])
    works[:] = [w for w in works if str(w.get("id")) != str(work_id)]

    global_payload = load_global_personas()
    affected = [
        p for p in global_payload.get("personas", []) if str(p.get("work_id") or "") == str(work_id)
    ]
    reassigned = 0
    deleted_personas = 0
    if cascade:
        global_payload["personas"] = [
            p
            for p in global_payload.get("personas", [])
            if str(p.get("work_id") or "") != str(work_id)
        ]
        deleted_personas = len(affected)
    else:
        for p in affected:
            p["work_id"] = reassign_to or None
            p["updated_at"] = now_iso()
            reassigned += 1
    save_global_personas(global_payload)
    return {
        "removed": work,
        "reassigned": reassigned,
        "deleted_personas": deleted_personas,
    }


def list_personas_in_work(work_id: str | None) -> list[dict[str, Any]]:
    """Return personas whose work_id matches; if work_id is None, returns unassigned ones."""
    global_payload = load_global_personas()
    personas = global_payload.get("personas", []) or []
    if work_id is None:
        return [p for p in personas if not p.get("work_id")]
    return [p for p in personas if str(p.get("work_id") or "") == str(work_id)]


def move_personas_to_work(persona_ids: list[str], target_work_id: str | None) -> dict[str, Any]:
    """Bulk move personas. target_work_id=None means 'unassign'."""
    if target_work_id:
        works_payload = load_works()
        if find_work(works_payload, target_work_id) is None:
            raise ValueError(f"target work '{target_work_id}' not found")
    global_payload = load_global_personas()
    personas = global_payload.get("personas", []) or []
    moved: list[str] = []
    for p in personas:
        if str(p.get("id")) in {str(x) for x in persona_ids}:
            p["work_id"] = target_work_id or None
            p["updated_at"] = now_iso()
            moved.append(str(p.get("id")))
    save_global_personas(global_payload)
    return {"moved": moved, "target_work_id": target_work_id}
