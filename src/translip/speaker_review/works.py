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


EXTERNAL_FIELDS: tuple[str, ...] = (
    "external_refs",
    "metadata",
    "cast_snapshot",
)

# Recognised top-level external-source keys we accept on input. The canonical
# storage shape is `external_refs` + `metadata` (matching the existing
# `~/.translip/works.json` layout written by earlier syncs). For ergonomics we
# also accept a few synonyms used by the design draft and gracefully migrate
# them at write time:
#   poster_path / poster_url        -> metadata.poster_url
#   backdrop_path / backdrop_url    -> metadata.backdrop_url
#   synopsis / overview             -> metadata.overview
#   synopsis_lang                   -> metadata.overview_lang
#   origin_country (top-level)      -> metadata.origin_country
#   original_title (top-level)      -> metadata.original_title
#   external_source                 -> metadata.source
#   external_synced_at              -> metadata.last_synced_at

_METADATA_SYNONYMS: dict[str, str] = {
    "poster_path": "poster_url",
    "poster_url": "poster_url",
    "backdrop_path": "backdrop_url",
    "backdrop_url": "backdrop_url",
    "synopsis": "overview",
    "overview": "overview",
    "synopsis_lang": "overview_lang",
    "overview_lang": "overview_lang",
    "original_title": "original_title",
    "external_source": "source",
    "external_synced_at": "last_synced_at",
}


def _clean_optional_string(value: Any) -> str | None:
    if isinstance(value, str):
        v = value.strip()
        return v or None
    return value if value is not None else None


def _normalize_cast_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Accept both the canonical shape (actor_name / character_name / profile_url)
    and the design-draft shape (actor / character / profile_path), normalising
    both into the canonical shape.
    """
    actor_name = (
        str(entry.get("actor_name") or entry.get("actor") or "").strip()
    )
    character_name = (
        str(entry.get("character_name") or entry.get("character") or "").strip()
    )
    profile_url = entry.get("profile_url") or entry.get("profile_path") or None
    cleaned: dict[str, Any] = {
        "external_person_id": str(entry.get("external_person_id") or "").strip() or None,
        "actor_name": actor_name,
        "character_name": character_name,
        "profile_url": profile_url,
        "gender": entry.get("gender") or None,
        "order": int(entry.get("order") or 0),
        "source": (entry.get("source") or "tmdb"),
    }
    if entry.get("key"):
        cleaned["key"] = str(entry["key"])
    if entry.get("credit_id"):
        cleaned["credit_id"] = str(entry["credit_id"])
    if "episode_count" in entry:
        cleaned["episode_count"] = entry.get("episode_count")
    actor_aliases = entry.get("actor_aliases") or []
    if isinstance(actor_aliases, list) and actor_aliases:
        cleaned["actor_aliases"] = [str(a).strip() for a in actor_aliases if str(a).strip()]
    character_aliases = entry.get("character_aliases") or []
    if isinstance(character_aliases, list) and character_aliases:
        cleaned["character_aliases"] = [
            str(a).strip() for a in character_aliases if str(a).strip()
        ]
    return cleaned


def _normalize_external_fields(data: dict[str, Any]) -> dict[str, Any]:
    """Map any of the accepted external-source keys onto the canonical
    `external_refs` + `metadata` + `cast_snapshot` storage shape.

    Returns only the keys present in `data`; callers should `dict.update`.
    """
    out: dict[str, Any] = {}

    # external_refs (passes through as-is, lightly cleaned)
    if "external_refs" in data and data.get("external_refs") is not None:
        refs = data.get("external_refs") or {}
        if isinstance(refs, dict):
            cleaned_refs: dict[str, Any] = {}
            tmdb_media_type = refs.get("tmdb_media_type") or refs.get("tmdb_type")
            if tmdb_media_type not in (None, "", []):
                cleaned_refs["tmdb_media_type"] = tmdb_media_type
            for key in (
                "tmdb_id",
                "tmdb_external_id",
                "imdb_id",
                "wikidata_id",
            ):
                v = refs.get(key)
                if v not in (None, "", []):
                    cleaned_refs[key] = v
            out["external_refs"] = cleaned_refs

    # metadata: merge top-level synonyms + nested `metadata` object
    incoming_meta: dict[str, Any] = {}
    nested_meta = data.get("metadata")
    if isinstance(nested_meta, dict):
        for k, v in nested_meta.items():
            if v is None:
                continue
            incoming_meta[k] = v
    for top_key, meta_key in _METADATA_SYNONYMS.items():
        if top_key in data:
            v = data.get(top_key)
            if isinstance(v, str):
                v = v.strip() or None
            if v is not None:
                incoming_meta[meta_key] = v
    if "origin_country" in data:
        v = data.get("origin_country")
        if isinstance(v, list):
            cleaned = [str(x).strip() for x in v if str(x).strip()]
            if cleaned:
                incoming_meta["origin_country"] = cleaned
    if incoming_meta:
        out["metadata"] = incoming_meta

    # cast_snapshot — only surface when non-empty list provided
    if "cast_snapshot" in data:
        cs = data.get("cast_snapshot")
        if isinstance(cs, list) and cs:
            normalized = [_normalize_cast_entry(e) for e in cs if isinstance(e, dict)]
            if normalized:
                out["cast_snapshot"] = normalized
    return out


def _merge_metadata(existing: dict[str, Any] | None, patch: dict[str, Any]) -> dict[str, Any]:
    """Merge incoming metadata patch over existing, preserving fields not in the
    patch (e.g. user-set `genres` shouldn't be wiped by a sync that only carries
    `overview`)."""
    base = dict(existing or {})
    for k, v in patch.items():
        base[k] = v
    return base


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
    external = _normalize_external_fields(data)
    work.update(external)
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
    external = _normalize_external_fields(patch)
    if external:
        # `metadata` must be deep-merged so a partial sync (e.g. only `overview`)
        # never wipes earlier fields like `genres` / `release_date`.
        if "metadata" in external:
            work["metadata"] = _merge_metadata(work.get("metadata"), external.pop("metadata"))
        # `external_refs` is shallow-merged so a partial update (e.g. adding
        # `imdb_id`) doesn't lose `tmdb_id`.
        if "external_refs" in external:
            base_refs = dict(work.get("external_refs") or {})
            base_refs.update(external.pop("external_refs"))
            work["external_refs"] = base_refs
        work.update(external)
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
