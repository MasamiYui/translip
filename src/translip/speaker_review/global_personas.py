from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .diagnostics import load_json, now_iso, write_json

GLOBAL_PERSONAS_DIR_ENV = "TRANSLIP_GLOBAL_PERSONAS_DIR"
GLOBAL_PERSONAS_FILENAME = "personas.json"
DEFAULT_GLOBAL_DIR = Path.home() / ".translip"


def global_personas_dir() -> Path:
    override = os.environ.get(GLOBAL_PERSONAS_DIR_ENV)
    if override:
        return Path(override).expanduser().resolve()
    return DEFAULT_GLOBAL_DIR


def global_personas_path() -> Path:
    return global_personas_dir() / GLOBAL_PERSONAS_FILENAME


def load_global_personas() -> dict[str, Any]:
    path = global_personas_path()
    if not path.exists():
        return {"version": 1, "personas": [], "updated_at": None}
    data = load_json(path) or {}
    if "personas" not in data or not isinstance(data.get("personas"), list):
        data["personas"] = []
    if "version" not in data:
        data["version"] = 1
    return data


def save_global_personas(payload: dict[str, Any]) -> Path:
    path = global_personas_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(payload)
    payload["updated_at"] = now_iso()
    write_json(payload, path)
    return path


def _normalize_name(name: str | None) -> str:
    return (name or "").strip().lower()


def _fingerprint(persona: dict[str, Any]) -> str:
    parts = [
        _normalize_name(persona.get("name")),
        (persona.get("gender") or "").lower(),
        (persona.get("role") or "").lower(),
    ]
    return "|".join(parts)


def _strip_for_global(persona: dict[str, Any]) -> dict[str, Any]:
    """Remove task-local fields (bindings) before storing globally."""
    kept_keys = {
        "id",
        "name",
        "aliases",
        "color",
        "avatar_emoji",
        "gender",
        "age_hint",
        "note",
        "role",
        "actor_name",
        "tags",
        "work_id",
        "guest_work_ids",
        "episodes",
        "external_refs",
        "tts_skip",
        "tts_voice_id",
        "confidence",
        "created_at",
        "updated_at",
    }
    cleaned = {k: v for k, v in persona.items() if k in kept_keys}
    return cleaned


def add_or_update_global(
    payload: dict[str, Any],
    persona: dict[str, Any],
    *,
    overwrite: bool = True,
) -> dict[str, Any]:
    """Insert or update a persona in the global library.

    Matching is by normalized name (case-insensitive). When a match exists and
    `overwrite=True`, the existing record is updated in place; when False the
    existing one wins unchanged.
    """
    stripped = _strip_for_global(persona)
    if not stripped.get("name"):
        raise ValueError("persona.name is required")
    personas = payload.setdefault("personas", [])
    target_fp = _fingerprint(stripped)
    for existing in personas:
        if _fingerprint(existing) == target_fp:
            if overwrite:
                existing.update(stripped)
                existing["updated_at"] = now_iso()
            return existing
    stripped["created_at"] = stripped.get("created_at") or now_iso()
    stripped["updated_at"] = now_iso()
    personas.append(stripped)
    return stripped


def remove_global(payload: dict[str, Any], persona_id: str) -> bool:
    personas = payload.get("personas", [])
    for idx, persona in enumerate(personas):
        if str(persona.get("id")) == str(persona_id):
            personas.pop(idx)
            return True
    return False


def list_global(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return list(payload.get("personas", []))


def export_task_personas_to_global(
    task_personas_payload: dict[str, Any],
    *,
    overwrite: bool = True,
) -> dict[str, Any]:
    """Copy all personas from a task-local payload into the global library.

    Returns {"exported": [persona_name, ...], "skipped": [...]}.
    """
    global_payload = load_global_personas()
    exported: list[str] = []
    skipped: list[str] = []
    for persona in task_personas_payload.get("personas", []):
        if not isinstance(persona, dict):
            continue
        name = (persona.get("name") or "").strip()
        if not name:
            continue
        before_count = len(global_payload.get("personas", []))
        add_or_update_global(global_payload, persona, overwrite=overwrite)
        after_count = len(global_payload.get("personas", []))
        if after_count > before_count or overwrite:
            exported.append(name)
        else:
            skipped.append(name)
    save_global_personas(global_payload)
    return {
        "exported": exported,
        "skipped": skipped,
        "total": len(global_payload.get("personas", [])),
    }


def smart_match_global(
    task_speakers: list[dict[str, Any]],
    global_payload: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Propose global personas for each speaker based on heuristics.

    Current heuristics (simple but effective):
      - Match by role (if speaker has a role hint set)
      - Match by gender (if speaker has gender hint)
      - Fallback: return top-3 pinned / is_target first

    Returns a list of {speaker_label, candidates: [{persona_id, name, score, reason}]}.
    """
    if global_payload is None:
        global_payload = load_global_personas()
    globals_list = global_payload.get("personas", []) or []
    results: list[dict[str, Any]] = []
    for speaker in task_speakers:
        label = str(speaker.get("speaker_label") or speaker.get("label") or "")
        if not label:
            continue
        role_hint = (speaker.get("role") or "").strip().lower()
        gender_hint = (speaker.get("gender") or "").strip().lower()
        candidates: list[dict[str, Any]] = []
        for g in globals_list:
            score = 0.0
            reasons: list[str] = []
            g_role = (g.get("role") or "").strip().lower()
            g_gender = (g.get("gender") or "").strip().lower()
            if role_hint and g_role and role_hint == g_role:
                score += 0.6
                reasons.append(f"role={g_role}")
            if gender_hint and g_gender and gender_hint == g_gender:
                score += 0.3
                reasons.append(f"gender={g_gender}")
            if score > 0:
                candidates.append(
                    {
                        "persona_id": g.get("id"),
                        "name": g.get("name"),
                        "score": round(score, 3),
                        "reason": ", ".join(reasons) or "heuristic",
                        "role": g.get("role"),
                        "gender": g.get("gender"),
                        "tts_voice_id": g.get("tts_voice_id"),
                    }
                )
        candidates.sort(key=lambda c: -c["score"])
        results.append({"speaker_label": label, "candidates": candidates[:3]})
    return results


def find_global_by_id(payload: dict[str, Any], persona_id: str) -> dict[str, Any] | None:
    for p in payload.get("personas", []):
        if str(p.get("id")) == str(persona_id):
            return p
    return None
