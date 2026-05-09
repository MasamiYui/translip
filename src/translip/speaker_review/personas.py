from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .diagnostics import load_json, now_iso, write_json

PERSONAS_FILE = "speaker-personas.json"
HISTORY_FILE = "speaker-personas.history.jsonl"
HISTORY_CURSOR_FILE = "speaker-personas.history.cursor.json"
SNAPSHOT_DIR = "speaker-personas.snapshots"

DEFAULT_PALETTE = [
    "#f59e0b",
    "#3b82f6",
    "#10b981",
    "#ec4899",
    "#8b5cf6",
    "#06b6d4",
    "#f97316",
    "#84cc16",
    "#ef4444",
    "#14b8a6",
    "#6366f1",
    "#a855f7",
]

BULK_TEMPLATES: dict[str, list[str]] = {
    "role_abc": [f"角色 {chr(0x41 + idx)}" for idx in range(26)],
    "protagonist": ["主角", "配角", "旁白", "群演 1", "群演 2", "群演 3"],
    "by_index": [f"说话人 {idx + 1}" for idx in range(20)],
}


@dataclass(slots=True)
class Persona:
    id: str
    name: str
    bindings: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    color: str | None = None
    avatar_emoji: str | None = None
    gender: str | None = None
    age_hint: str | None = None
    note: str | None = None
    role: str | None = None
    pinned: bool = False
    is_target: bool = False
    confidence: float | None = None
    tts_skip: bool = False
    tts_voice_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "bindings": list(self.bindings),
            "aliases": list(self.aliases),
        }
        for key in (
            "color",
            "avatar_emoji",
            "gender",
            "age_hint",
            "note",
            "tts_voice_id",
            "role",
        ):
            value = getattr(self, key)
            if value is not None:
                payload[key] = value
        if self.tts_skip:
            payload["tts_skip"] = True
        if self.pinned:
            payload["pinned"] = True
        if self.is_target:
            payload["is_target"] = True
        if self.confidence is not None:
            payload["confidence"] = self.confidence
        if self.created_at:
            payload["created_at"] = self.created_at
        if self.updated_at:
            payload["updated_at"] = self.updated_at
        return payload


def personas_path(review_dir: Path) -> Path:
    return review_dir / PERSONAS_FILE


def history_path(review_dir: Path) -> Path:
    return review_dir / HISTORY_FILE


def load_personas(review_dir: Path) -> dict[str, Any]:
    path = personas_path(review_dir)
    if not path.exists():
        return {"version": 1, "updated_at": now_iso(), "personas": [], "unassigned_bindings": []}
    payload = load_json(path)
    if not isinstance(payload, dict):
        return {"version": 1, "updated_at": now_iso(), "personas": [], "unassigned_bindings": []}
    payload.setdefault("version", 1)
    payload.setdefault("personas", [])
    payload.setdefault("unassigned_bindings", [])
    return payload


def save_personas(review_dir: Path, payload: dict[str, Any]) -> Path:
    payload["updated_at"] = now_iso()
    review_dir.mkdir(parents=True, exist_ok=True)
    return write_json(payload, personas_path(review_dir))


def append_history(review_dir: Path, op: str, details: dict[str, Any]) -> None:
    path = history_path(review_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"ts": now_iso(), "op": op, **details}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_history(review_dir: Path) -> list[dict[str, Any]]:
    path = history_path(review_dir)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def rewrite_history(review_dir: Path, rows: list[dict[str, Any]]) -> None:
    path = history_path(review_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def sync_unassigned(payload: dict[str, Any], known_speakers: Iterable[str]) -> dict[str, Any]:
    """Ensure unassigned_bindings reflects known speakers minus bound ones."""
    bound: set[str] = set()
    for persona in payload.get("personas", []):
        if isinstance(persona, dict):
            bound.update(str(b) for b in persona.get("bindings", []) if b)
    unassigned = [label for label in dict.fromkeys(known_speakers) if label and label not in bound]
    payload["unassigned_bindings"] = unassigned
    return payload


def build_by_speaker_index(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for persona in payload.get("personas", []):
        if not isinstance(persona, dict):
            continue
        brief = {
            "persona_id": persona.get("id"),
            "name": persona.get("name"),
            "color": persona.get("color"),
            "avatar_emoji": persona.get("avatar_emoji"),
        }
        for speaker in persona.get("bindings", []):
            if speaker:
                index[str(speaker)] = brief
    return index


def find_persona(payload: dict[str, Any], persona_id: str) -> dict[str, Any] | None:
    for persona in payload.get("personas", []):
        if isinstance(persona, dict) and str(persona.get("id")) == persona_id:
            return persona
    return None


def detach_binding(payload: dict[str, Any], speaker_label: str) -> dict[str, Any] | None:
    """Remove a binding from any persona that owns it. Returns the affected persona dict."""
    for persona in payload.get("personas", []):
        if not isinstance(persona, dict):
            continue
        bindings = [str(b) for b in persona.get("bindings", []) if b]
        if speaker_label in bindings:
            persona["bindings"] = [b for b in bindings if b != speaker_label]
            persona["updated_at"] = now_iso()
            return persona
    return None


def next_color(payload: dict[str, Any]) -> str:
    used = {
        str(persona.get("color") or "").lower()
        for persona in payload.get("personas", [])
        if isinstance(persona, dict)
    }
    for color in DEFAULT_PALETTE:
        if color.lower() not in used:
            return color
    return DEFAULT_PALETTE[len(payload.get("personas", [])) % len(DEFAULT_PALETTE)]


def create_persona(
    payload: dict[str, Any],
    *,
    name: str,
    bindings: list[str] | None = None,
    color: str | None = None,
    avatar_emoji: str | None = None,
    note: str | None = None,
    role: str | None = None,
    gender: str | None = None,
    age_hint: str | None = None,
    pinned: bool = False,
    is_target: bool = False,
    confidence: float | None = None,
    tts_voice_id: str | None = None,
    tts_skip: bool = False,
) -> dict[str, Any]:
    persona_id = f"persona_{uuid.uuid4().hex[:10]}"
    now = now_iso()
    persona: dict[str, Any] = {
        "id": persona_id,
        "name": name.strip(),
        "bindings": [],
        "aliases": [],
        "color": color or next_color(payload),
        "avatar_emoji": avatar_emoji,
        "note": note,
        "role": role,
        "gender": gender,
        "age_hint": age_hint,
        "tts_voice_id": tts_voice_id,
        "created_at": now,
        "updated_at": now,
    }
    if pinned:
        persona["pinned"] = True
    if is_target:
        persona["is_target"] = True
    if tts_skip:
        persona["tts_skip"] = True
    if confidence is not None:
        persona["confidence"] = float(confidence)
    for empty_key in ("avatar_emoji", "note", "role", "gender", "age_hint", "tts_voice_id"):
        if not persona.get(empty_key):
            persona.pop(empty_key, None)
    payload.setdefault("personas", []).append(persona)
    for speaker in bindings or []:
        if not speaker:
            continue
        detach_binding(payload, str(speaker))
        if str(speaker) not in persona["bindings"]:
            persona["bindings"].append(str(speaker))
    return persona


def update_persona(
    payload: dict[str, Any],
    persona_id: str,
    **updates: Any,
) -> dict[str, Any]:
    persona = find_persona(payload, persona_id)
    if persona is None:
        raise KeyError(persona_id)
    for key, value in updates.items():
        if value is None:
            continue
        if key == "name":
            persona["name"] = str(value).strip()
        elif key in {
            "color",
            "avatar_emoji",
            "note",
            "gender",
            "age_hint",
            "tts_voice_id",
            "role",
        }:
            persona[key] = value
        elif key == "aliases" and isinstance(value, list):
            persona["aliases"] = [str(x).strip() for x in value if str(x).strip()]
        elif key in {"tts_skip", "pinned", "is_target"}:
            persona[key] = bool(value)
        elif key == "confidence":
            persona["confidence"] = float(value)
    persona["updated_at"] = now_iso()
    return persona


def find_name_conflict(
    payload: dict[str, Any],
    name: str,
    *,
    exclude_id: str | None = None,
) -> dict[str, Any] | None:
    """Return the existing persona dict that already uses this name (case-insensitive),
    excluding `exclude_id` if provided. Returns None if no conflict.
    """
    needle = (name or "").strip().lower()
    if not needle:
        return None
    for persona in payload.get("personas", []):
        if not isinstance(persona, dict):
            continue
        if str(persona.get("id")) == exclude_id:
            continue
        existing = str(persona.get("name") or "").strip().lower()
        if existing and existing == needle:
            return persona
    return None


def snapshot_personas(review_dir: Path) -> Path | None:
    """Save a timestamped copy of speaker-personas.json under SNAPSHOT_DIR."""
    src = personas_path(review_dir)
    if not src.exists():
        return None
    dst_dir = review_dir / SNAPSHOT_DIR
    dst_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime_now_compact()
    dst = dst_dir / f"{ts}.json"
    payload = load_json(src)
    write_json(payload, dst)
    return dst


def datetime_now_compact() -> str:
    from datetime import datetime as _dt

    return _dt.now().strftime("%Y%m%d-%H%M%S-%f")


# ---- History v2: undo/redo stack with cursor ----


def history_cursor_path(review_dir: Path) -> Path:
    return review_dir / HISTORY_CURSOR_FILE


def load_history_cursor(review_dir: Path) -> int:
    """Cursor points to the index that the next undo will revert.
    cursor == len(history) means we're at the latest state (no redo available).
    """
    path = history_cursor_path(review_dir)
    if not path.exists():
        return _initial_cursor(review_dir)
    try:
        payload = load_json(path)
        cursor = int(payload.get("cursor", 0))
        return max(0, cursor)
    except Exception:
        return _initial_cursor(review_dir)


def _initial_cursor(review_dir: Path) -> int:
    return len(read_history(review_dir))


def save_history_cursor(review_dir: Path, cursor: int) -> None:
    write_json({"cursor": int(cursor), "updated_at": now_iso()}, history_cursor_path(review_dir))


def history_status(review_dir: Path) -> dict[str, Any]:
    rows = read_history(review_dir)
    cursor = load_history_cursor(review_dir)
    cursor = min(max(0, cursor), len(rows))
    return {
        "total": len(rows),
        "cursor": cursor,
        "can_undo": cursor > 0,
        "can_redo": cursor < len(rows),
        "last_undo_op": rows[cursor - 1].get("op") if cursor > 0 else None,
        "next_redo_op": rows[cursor].get("op") if cursor < len(rows) else None,
    }


def append_history_v2(review_dir: Path, op: str, details: dict[str, Any]) -> None:
    """Append a new history entry, truncating any redo-able tail.

    This wraps `append_history` and updates the cursor to len(history) so that
    redo is reset after a fresh action (classic undo/redo behavior).
    """
    rows = read_history(review_dir)
    cursor = load_history_cursor(review_dir)
    cursor = min(max(0, cursor), len(rows))
    if cursor < len(rows):
        rows = rows[:cursor]
        rewrite_history(review_dir, rows)
    append_history(review_dir, op, details)
    save_history_cursor(review_dir, cursor + 1)


def _apply_history_undo(payload: dict[str, Any], entry: dict[str, Any]) -> None:
    op = entry.get("op")
    before = entry.get("before")
    after = entry.get("after")
    if op == "create" and after:
        payload["personas"] = [
            p for p in payload.get("personas", []) if p.get("id") != after.get("id")
        ]
    elif op == "delete" and before:
        payload.setdefault("personas", []).append(before)
    elif op in {"update", "rename", "bind", "unbind"} and before:
        personas = [p for p in payload.get("personas", []) if p.get("id") != before.get("id")]
        personas.append(before)
        payload["personas"] = personas
    elif op == "bulk" and after:
        created_ids = {p.get("id") for p in (after.get("created") or [])}
        payload["personas"] = [p for p in payload.get("personas", []) if p.get("id") not in created_ids]


def _apply_history_redo(payload: dict[str, Any], entry: dict[str, Any]) -> None:
    op = entry.get("op")
    before = entry.get("before")
    after = entry.get("after")
    if op == "create" and after:
        payload.setdefault("personas", []).append(after)
    elif op == "delete" and before:
        payload["personas"] = [
            p for p in payload.get("personas", []) if p.get("id") != before.get("id")
        ]
    elif op in {"update", "rename", "bind", "unbind"} and after:
        personas = [p for p in payload.get("personas", []) if p.get("id") != after.get("id")]
        personas.append(after)
        payload["personas"] = personas
    elif op == "bulk" and after:
        for created in after.get("created") or []:
            if isinstance(created, dict):
                payload.setdefault("personas", []).append(created)


def undo_with_cursor(review_dir: Path) -> dict[str, Any] | None:
    """Step the history cursor back by one and apply the inverse of that entry.

    Returns the entry that was reverted, or None if there's nothing to undo.
    """
    rows = read_history(review_dir)
    cursor = load_history_cursor(review_dir)
    cursor = min(max(0, cursor), len(rows))
    if cursor <= 0:
        return None
    entry = rows[cursor - 1]
    payload = load_personas(review_dir)
    _apply_history_undo(payload, entry)
    save_personas(review_dir, payload)
    save_history_cursor(review_dir, cursor - 1)
    return entry


def redo_with_cursor(review_dir: Path) -> dict[str, Any] | None:
    """Move cursor forward and reapply the entry. Returns the entry replayed."""
    rows = read_history(review_dir)
    cursor = load_history_cursor(review_dir)
    cursor = min(max(0, cursor), len(rows))
    if cursor >= len(rows):
        return None
    entry = rows[cursor]
    payload = load_personas(review_dir)
    _apply_history_redo(payload, entry)
    save_personas(review_dir, payload)
    save_history_cursor(review_dir, cursor + 1)
    return entry


def delete_persona(payload: dict[str, Any], persona_id: str) -> dict[str, Any]:
    personas = payload.get("personas", [])
    for idx, persona in enumerate(personas):
        if isinstance(persona, dict) and str(persona.get("id")) == persona_id:
            removed = personas.pop(idx)
            payload["personas"] = personas
            return removed
    raise KeyError(persona_id)


def bind_persona(payload: dict[str, Any], persona_id: str, speaker_label: str) -> dict[str, Any]:
    persona = find_persona(payload, persona_id)
    if persona is None:
        raise KeyError(persona_id)
    # Remove binding from any other persona first.
    for other in payload.get("personas", []):
        if not isinstance(other, dict) or str(other.get("id")) == persona_id:
            continue
        bindings = [b for b in other.get("bindings", []) if b != speaker_label]
        if len(bindings) != len(other.get("bindings", [])):
            other["bindings"] = bindings
            other["updated_at"] = now_iso()
    bindings = list(persona.get("bindings", []))
    if speaker_label not in bindings:
        bindings.append(speaker_label)
    persona["bindings"] = bindings
    persona["updated_at"] = now_iso()
    return persona


def unbind_persona(payload: dict[str, Any], persona_id: str, speaker_label: str) -> dict[str, Any]:
    persona = find_persona(payload, persona_id)
    if persona is None:
        raise KeyError(persona_id)
    persona["bindings"] = [b for b in persona.get("bindings", []) if b != speaker_label]
    persona["updated_at"] = now_iso()
    return persona


def merge_personas_on_speakers(payload: dict[str, Any], source_label: str, target_label: str) -> None:
    """When a speaker label merges into another (e.g. via apply decisions),
    fold the source persona's bindings into the target persona if they differ.
    """
    if source_label == target_label:
        return
    source_persona = None
    target_persona = None
    for persona in payload.get("personas", []):
        if not isinstance(persona, dict):
            continue
        if source_label in persona.get("bindings", []):
            source_persona = persona
        if target_label in persona.get("bindings", []):
            target_persona = persona
    if source_persona is None:
        return
    # Remove source binding from source persona.
    source_persona["bindings"] = [b for b in source_persona.get("bindings", []) if b != source_label]
    source_persona["updated_at"] = now_iso()
    if target_persona is None:
        # Re-attach source_label to source_persona's renamed role? No - just leave unassigned.
        return
    if source_label not in target_persona.get("bindings", []):
        target_persona.setdefault("bindings", []).append(source_label)
        target_persona["updated_at"] = now_iso()
    # If source_persona has no more bindings, remove it entirely.
    if not source_persona.get("bindings"):
        payload["personas"] = [p for p in payload.get("personas", []) if p is not source_persona]


def apply_bulk_template(
    payload: dict[str, Any],
    *,
    template: str,
    speakers: list[str],
) -> list[dict[str, Any]]:
    names = BULK_TEMPLATES.get(template)
    if not names:
        raise ValueError(f"Unknown bulk template: {template}")
    # Determine which speakers are currently unassigned (preserve existing bindings).
    assigned: set[str] = set()
    for persona in payload.get("personas", []):
        if isinstance(persona, dict):
            assigned.update(str(b) for b in persona.get("bindings", []) if b)
    targets = [s for s in speakers if s and s not in assigned]
    created: list[dict[str, Any]] = []
    for idx, speaker in enumerate(targets):
        name = names[idx % len(names)] if idx < len(names) else f"{names[-1]} {idx - len(names) + 2}"
        persona = create_persona(payload, name=name, bindings=[speaker])
        created.append(persona)
    return created


_HONORIFIC_HINTS = (
    "，你",
    "，您",
    "！",
    "？",
    "：",
)


def suggest_personas(
    segments: list[dict[str, Any]],
    speakers: Iterable[str],
    *,
    limit: int = 3,
) -> dict[str, list[dict[str, Any]]]:
    """Lightweight rule-based suggestion. Returns mapping speaker_label -> candidates."""
    suggestions: dict[str, list[dict[str, Any]]] = {}
    for speaker in speakers:
        texts: list[str] = []
        others_calling: list[str] = []
        self_intro: list[str] = []
        for seg in segments:
            if not isinstance(seg, dict):
                continue
            label = str(seg.get("speaker_label") or "")
            text = str(seg.get("text") or seg.get("source_text") or "").strip()
            if not text:
                continue
            if label == speaker:
                texts.append(text)
                # "我是 X" / "我叫 X"
                match = re.search(r"我(?:是|叫)([\u4e00-\u9fffA-Za-z]{1,6})", text)
                if match:
                    self_intro.append(match.group(1))
            else:
                # Looking for "X，你..." style calling the current speaker.
                for hint in _HONORIFIC_HINTS:
                    if hint in text:
                        head = text.split(hint, 1)[0].strip()
                        cleaned = re.sub(r"[^\u4e00-\u9fffA-Za-z]", "", head)[-4:]
                        if 1 < len(cleaned) <= 4:
                            others_calling.append(cleaned)
                            break
        # Score candidates
        counter: dict[str, float] = {}
        for name in self_intro:
            counter[name] = counter.get(name, 0) + 1.2
        for name in others_calling:
            counter[name] = counter.get(name, 0) + 0.6
        ranked = sorted(counter.items(), key=lambda kv: kv[1], reverse=True)[:limit]
        total = max(1.0, sum(v for _, v in ranked))
        suggestions[speaker] = [
            {
                "name": name,
                "confidence": round(min(0.95, score / total + 0.2), 2),
                "source": "rule",
            }
            for name, score in ranked
        ]
    return suggestions


def undo_last(review_dir: Path) -> dict[str, Any] | None:
    """Pop the last history entry and attempt to invert it.

    Returns the entry that was reverted (as {op, payload}) or None if no-op.
    """
    rows = read_history(review_dir)
    if not rows:
        return None
    last = rows.pop()
    payload = load_personas(review_dir)
    op = last.get("op")
    before = last.get("before")
    after = last.get("after")
    try:
        if op == "create" and after:
            payload["personas"] = [p for p in payload.get("personas", []) if p.get("id") != after.get("id")]
        elif op == "delete" and before:
            payload.setdefault("personas", []).append(before)
        elif op in {"update", "rename", "bind", "unbind"} and before:
            personas = [p for p in payload.get("personas", []) if p.get("id") != before.get("id")]
            personas.append(before)
            payload["personas"] = personas
        elif op == "bulk" and after:
            # Remove created persona ids.
            created_ids = {p.get("id") for p in (after.get("created") or [])}
            payload["personas"] = [p for p in payload.get("personas", []) if p.get("id") not in created_ids]
    finally:
        save_personas(review_dir, payload)
        rewrite_history(review_dir, rows)
    return last
