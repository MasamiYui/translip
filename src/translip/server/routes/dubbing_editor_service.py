"""Service layer for the dubbing editor route module.

Holds the request/response models, module constants, and all helper logic
(project import, waveform/clip generation, unit/character/issue building,
segment resynthesis, backtranslation). The thin router in
``dubbing_editor.py`` star-imports from here so route handlers call these
helpers as bare names.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlmodel import Session

from ..database import get_session
from ..models import Task
from ...utils.io import append_jsonl, read_json, write_json as _write_json_impl
from ...speaker_review.personas import (
    build_by_speaker_index as _build_persona_by_speaker,
    load_personas as _load_personas,
)
from ...dubbing.backend import (
    ReferencePackage as _ReferencePackage,
    SynthSegmentInput as _SynthSegmentInput,
)

logger = logging.getLogger(__name__)

_EDITOR_SUBDIR = "dubbing-editor"
_WAVEFORM_RESOLUTION = 800  # samples per second for peaks
_pending_lock = threading.Lock()

# Static source-track glob patterns (relative to a task output root). The
# ``dub``/``preview_mix``/``mix`` tracks are added dynamically with target_lang
# at each call site, so they are intentionally absent here.
_TRACK_PATTERNS: dict[str, list[str]] = {
    "original": [
        "separation/voice/voice.wav",
        "separation/*/voice.wav",
        "separation/*/voice.mp3",
        "separation/voice/voice.mp3",
    ],
    "background": [
        "separation/background/background.wav",
        "separation/*/background.wav",
        "separation/*/background.mp3",
    ],
}


def _get_task(session: Session, task_id: str) -> Task:
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

def _editor_root(output_root: str) -> Path:
    return Path(output_root).resolve() / _EDITOR_SUBDIR

def _read_json(path: Path) -> dict[str, Any]:
    if path.exists():
        return read_json(path)
    return {}

def _write_json(path: Path, data: Any) -> None:
    _write_json_impl(data, path, atomic=False)

def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    append_jsonl(record, path)

def _import_editor_project(task: Task) -> dict[str, Any]:
    """Import / rebuild editor project from pipeline artifacts."""
    output_root = Path(task.output_root).resolve()
    editor_root = output_root / _EDITOR_SUBDIR

    target_lang = task.target_lang or "en"

    # Artifact paths (relative)
    artifact_paths: dict[str, str] = {
        "translation": f"translation/voice/translation.{target_lang}.json",
        "character_ledger": f"synthesis/voice/character-ledger/character_ledger.{target_lang}.json",
        "benchmark": f"benchmark/voice/dub_benchmark.{target_lang}.json",
        "mix_report": f"render/voice/mix_report.{target_lang}.json",
        "timeline": f"render/voice/timeline.{target_lang}.json",
        "speaker_profiles": "speaker-registry/voice/speaker_profiles.json",
        "preview_mix": f"render/voice/preview_mix.{target_lang}.wav",
        "dub_voice": f"render/voice/dub_voice.{target_lang}.wav",
        "final_preview": f"delivery/final-preview/final_preview.{target_lang}.mp4",
        "final_dub": f"delivery/final-dub/final_dub.{target_lang}.mp4",
        "editor_project": f"{_EDITOR_SUBDIR}/editor_project.json",
        "materialized": f"{_EDITOR_SUBDIR}/materialized.current.json",
        "operations": f"{_EDITOR_SUBDIR}/operations.jsonl",
    }

    # Load source data
    translation = _read_json(output_root / artifact_paths["translation"])
    character_ledger = _read_json(output_root / artifact_paths["character_ledger"])
    benchmark = _read_json(output_root / artifact_paths["benchmark"])
    mix_report = _read_json(output_root / artifact_paths["mix_report"])
    speaker_profiles = _read_json(output_root / artifact_paths["speaker_profiles"])
    timeline = _read_json(output_root / artifact_paths["timeline"])

    # Build characters from character ledger
    characters = _build_characters(character_ledger, speaker_profiles, benchmark, output_root=output_root)

    # Build dialogue units from translation + timeline
    units = _build_units(translation, timeline, character_ledger, output_root, target_lang, mix_report)

    # Build issues from per-segment quality rows plus benchmark aggregates
    issues = _build_issues(benchmark, units, timeline, mix_report)

    now = datetime.now(timezone.utc).isoformat()

    snapshot = {
        "version": "dubbing-editor-v0",
        "created_at": now,
        "task_id": task.id,
        "target_lang": target_lang,
        "status": "available",
        "source_video_path": task.input_path,
        "artifact_paths": artifact_paths,
        "quality_benchmark": benchmark,
        "characters": characters,
        "units": units,
        "issues": issues,
    }

    # Write initial snapshot
    editor_root.mkdir(parents=True, exist_ok=True)
    snapshot_path = editor_root / "initial_snapshot.json"
    _write_json(snapshot_path, snapshot)

    # Write editor project
    project = {
        "version": "dubbing-editor-v0",
        "created_at": now,
        "task_id": task.id,
        "target_lang": target_lang,
        "source_video_path": task.input_path,
        "duration_sec": None,
        "paths": {
            "initial_snapshot": f"{_EDITOR_SUBDIR}/initial_snapshot.json",
            "operations": f"{_EDITOR_SUBDIR}/operations.jsonl",
            "materialized": f"{_EDITOR_SUBDIR}/materialized.current.json",
        },
    }
    _write_json(editor_root / "editor_project.json", project)

    # Initialize operations log if not exists
    ops_path = editor_root / "operations.jsonl"
    if not ops_path.exists():
        ops_path.touch()

    # Materialize current state
    materialized = _materialize(snapshot, ops_path)
    _write_json(editor_root / "materialized.current.json", materialized)

    # Pre-generate waveform peaks in background (non-blocking)
    bg_thread = threading.Thread(
        target=_pregenerate_waveforms_bg,
        args=(output_root, target_lang, editor_root),
        daemon=True,
    )
    bg_thread.start()

    return materialized

def _resolve_audio_path(output_root: Path, patterns: list[str]) -> Path | None:
    """Resolve the first matching audio file given a list of path patterns."""
    for pattern in patterns:
        if "*" in pattern:
            matches = list(output_root.glob(pattern))
            if matches:
                return matches[0]
        else:
            candidate = output_root / pattern
            if candidate.exists():
                return candidate
    return None

def _pregenerate_waveforms_bg(output_root: Path, target_lang: str, editor_root: Path) -> None:
    """Pre-generate waveform peaks for all tracks in a background thread."""
    peaks_dir = editor_root / "waveform"
    peaks_dir.mkdir(parents=True, exist_ok=True)

    track_patterns: dict[str, list[str]] = {
        **_TRACK_PATTERNS,
        "dub": [f"render/voice/dub_voice.{target_lang}.wav"],
        "preview_mix": [f"render/voice/preview_mix.{target_lang}.wav"],
    }

    for track, patterns in track_patterns.items():
        peaks_path = peaks_dir / f"{track}.peaks.json"
        if peaks_path.exists():
            continue
        audio_path = _resolve_audio_path(output_root, patterns)
        if audio_path is None:
            continue
        try:
            peaks = _generate_peaks(audio_path)
            duration_sec = 0.0
            try:
                import soundfile as sf  # type: ignore
                info = sf.info(str(audio_path))
                duration_sec = info.duration
            except Exception:
                pass
            result = {"track": track, "peaks": peaks, "duration_sec": duration_sec, "available": True}
            _write_json(peaks_path, result)
            logger.info("Pre-generated waveform peaks for track: %s", track)
        except Exception as exc:
            logger.warning("Failed to pre-generate peaks for %s: %s", track, exc)

def _extract_clip(source: Path, dest: Path, start_sec: float, end_sec: float) -> None:
    """Extract a time-range slice from an audio file and save to dest."""
    try:
        import soundfile as sf  # type: ignore
        import numpy as np  # type: ignore

        data, sr = sf.read(str(source), dtype="float32", always_2d=False)
        if data.ndim > 1:
            data = data.mean(axis=1)
        start_sample = int(start_sec * sr)
        end_sample = min(int(end_sec * sr), len(data))
        clip = data[start_sample:end_sample]
        if len(clip) > 0:
            sf.write(str(dest), clip, sr)
    except Exception as exc:
        logger.warning("Clip extraction failed for %s: %s", source, exc)

def _build_characters(
    character_ledger: dict,
    speaker_profiles: dict,
    benchmark: dict,
    output_root: Path | None = None,
) -> list[dict]:
    characters = []
    char_entries = character_ledger.get("characters", []) or character_ledger.get("entries", [])

    # Load personas (speaker -> persona mapping) so we can inject
    # persona.tts_skip / name / avatar_emoji into character cards.
    persona_by_speaker: dict[str, dict] = {}
    if output_root is not None:
        try:
            review_dir = output_root / "transcription" / "voice" / "speaker-review"
            if not review_dir.exists():
                review_dir = output_root / "separation" / "voice" / "speaker-review"
            if review_dir.exists():
                personas_payload = _load_personas(review_dir)
                persona_by_speaker = _build_persona_by_speaker(personas_payload) or {}
        except Exception:  # pragma: no cover - defensive
            persona_by_speaker = {}

    # Build benchmark stats per character
    char_stats: dict[str, dict] = {}
    for seg in benchmark.get("segments", []):
        char_id = seg.get("character_id") or seg.get("speaker_id")
        if not char_id:
            continue
        s = char_stats.setdefault(char_id, {
            "segment_count": 0,
            "speaker_failed_count": 0,
            "overall_failed_count": 0,
            "voice_mismatch_count": 0,
        })
        s["segment_count"] += 1
        if seg.get("speaker_similarity_status") == "failed":
            s["speaker_failed_count"] += 1
        if seg.get("overall_status") == "failed":
            s["overall_failed_count"] += 1
        if seg.get("voice_mismatch"):
            s["voice_mismatch_count"] += 1

    # Determine review characters from benchmark
    review_chars = set()
    blocked_chars = set()
    mismatch_chars = set()
    for c in benchmark.get("character_results", []):
        char_id = c.get("character_id")
        if c.get("status") == "review":
            review_chars.add(char_id)
        elif c.get("status") == "blocked":
            blocked_chars.add(char_id)
        if c.get("voice_mismatch"):
            mismatch_chars.add(char_id)

    for entry in char_entries:
        char_id = entry.get("character_id") or entry.get("id")
        if not char_id:
            continue

        risk_flags = list(entry.get("risk_flags", []) or [])
        if char_id in review_chars:
            risk_flags.append("character_voice_review_required")
        if char_id in blocked_chars:
            risk_flags.append("blocked")
        if char_id in mismatch_chars:
            risk_flags.append("voice_mismatch")
        risk_flags = list(dict.fromkeys(risk_flags))

        stats = entry.get("stats") if isinstance(entry.get("stats"), dict) else char_stats.get(char_id, {})
        seg_count = stats.get("segment_count", 0)
        spk_failed = stats.get("speaker_failed_count", 0)
        spk_ratio = spk_failed / seg_count if seg_count > 0 else 0.0

        if spk_ratio > 0.15 and "speaker_similarity_failed" not in risk_flags:
            risk_flags.append("speaker_similarity_failed")

        # Determine review status
        raw_review_status = entry.get("review_status") or entry.get("status")
        if raw_review_status:
            review_status = _normalize_review_status(raw_review_status)
        elif char_id in blocked_chars:
            review_status = "blocked"
        elif char_id in review_chars or risk_flags:
            review_status = "needs_review"
        else:
            review_status = "passed"

        voice_signature = entry.get("voice_signature") if isinstance(entry.get("voice_signature"), dict) else {}
        pitch_hz = entry.get("pitch_hz") or entry.get("f0_median_hz") or voice_signature.get("pitch_hz")
        pitch_class = (
            entry.get("pitch_class")
            or voice_signature.get("pitch_class")
            or (_classify_pitch(pitch_hz) if pitch_hz else "mid")
        )

        # Resolve persona attached to any of this character's speaker_ids.
        persona_attached: dict | None = None
        for sid in entry.get("speaker_ids", []) or []:
            p = persona_by_speaker.get(str(sid))
            if p:
                persona_attached = p
                break

        # Compute display_name: prefer persona.name to provide the friendly
        # speaker nickname inside the dubbing editor.
        display_name = entry.get("display_name") or entry.get("name") or char_id
        if persona_attached and persona_attached.get("name"):
            display_name = persona_attached["name"]

        # default_voice: carries the editor's current reference path.
        default_voice = dict(entry.get("default_voice", {"backend": "inherit", "reference_path": None}))

        char_card = {
            "character_id": char_id,
            "display_name": display_name,
            "speaker_ids": entry.get("speaker_ids", []),
            "review_status": review_status,
            "risk_flags": risk_flags,
            "pitch_class": pitch_class,
            "pitch_hz": pitch_hz,
            "stats": {
                "segment_count": seg_count,
                "speaker_failed_count": spk_failed,
                "overall_failed_count": stats.get("overall_failed_count", 0),
                "voice_mismatch_count": stats.get("voice_mismatch_count", 0),
                "speaker_failed_ratio": round(spk_ratio, 4),
            },
            "voice_lock": entry.get("voice_lock", False),
            "default_voice": default_voice,
        }
        if persona_attached:
            char_card["persona"] = {
                "id": persona_attached.get("id"),
                "name": persona_attached.get("name"),
                "color": persona_attached.get("color"),
                "avatar_emoji": persona_attached.get("avatar_emoji"),
                "tts_skip": bool(persona_attached.get("tts_skip")),
                "role": persona_attached.get("role"),
                "is_target": bool(persona_attached.get("is_target")),
            }
        characters.append(char_card)

    return characters

def _normalize_review_status(status: str) -> str:
    if status == "blocked":
        return "blocked"
    if status in {"review", "needs_review"}:
        return "needs_review"
    return "passed"

def _classify_pitch(hz: float) -> str:
    if hz < 130:
        return "low"
    elif hz < 200:
        return "mid-low"
    elif hz < 280:
        return "mid"
    elif hz < 360:
        return "high"
    return "very-high"

def _build_units(
    translation: dict,
    timeline: dict,
    character_ledger: dict,
    output_root: Path,
    target_lang: str,
    mix_report: dict | None = None,
) -> list[dict]:
    units = []

    # Build segment-to-character mapping
    seg_to_char: dict[str, str] = {}
    seg_to_speaker: dict[str, str] = {}
    for entry in (character_ledger.get("characters", []) or character_ledger.get("entries", [])):
        char_id = entry.get("character_id") or entry.get("id")
        for spk in entry.get("speaker_ids", []):
            seg_to_char[spk] = char_id
            seg_to_speaker[spk] = spk

    # Build clip / quality mapping from current timeline schema, with mix report fallback.
    clip_paths = _segment_rows_by_id(timeline, mix_report or {})

    # Process translation segments
    segments = translation.get("segments", [])
    for seg in segments:
        seg_id = seg.get("segment_id") or seg.get("id")
        if not seg_id:
            continue

        speaker_id = seg.get("speaker_id", "")
        char_id = seg.get("character_id") or seg_to_char.get(speaker_id, f"char_unknown")

        slot = clip_paths.get(seg_id, {})
        # NOTE: prefer the permanent synthesis ``audio_path`` over the transient
        # ``fitted_audio_path`` (which lives under ``render/.work/<job>/fit/``
        # and is wiped after the pipeline run). This keeps the inspector
        # preview playable long after the pipeline finishes.
        audio_path = slot.get("audio_path") or slot.get("fitted_audio_path") or slot.get("clip_path")

        unit = {
            "unit_id": seg_id,
            "source_segment_ids": [seg_id],
            "speaker_id": speaker_id,
            "character_id": char_id,
            "start": seg.get("start", 0),
            "end": seg.get("end", 0),
            "duration": seg.get("duration") or (seg.get("end", 0) - seg.get("start", 0)),
            "source_text": seg.get("source_text") or seg.get("text", ""),
            "target_text": seg.get("target_text") or seg.get("translation", ""),
            "status": _unit_status_from_quality(slot),
            "issue_ids": [],
            "current_clip": {
                "clip_id": f"clip_{seg_id}",
                "audio_path": audio_path,
                "audio_artifact_path": _to_relative(audio_path, output_root) if audio_path else None,
                "duration": (
                    slot.get("fitted_duration_sec")
                    or slot.get("fitted_duration")
                    or slot.get("duration")
                    or slot.get("generated_duration_sec")
                ),
                "generated_duration": slot.get("generated_duration_sec"),
                "source_duration": (
                    slot.get("source_duration_sec")
                    or seg.get("duration")
                    or (seg.get("end", 0) - seg.get("start", 0))
                ),
                "backend": slot.get("backend", ""),
                "mix_status": slot.get("mix_status") or ("placed" if audio_path else "missing"),
                "fit_strategy": slot.get("fit_strategy", ""),
            },
            "candidates": [],
        }
        units.append(unit)

    return units

def _unit_status_from_quality(row: dict[str, Any]) -> str:
    statuses = [
        row.get("overall_status"),
        row.get("task_d_status"),
        row.get("duration_status"),
        row.get("speaker_status"),
        row.get("intelligibility_status"),
    ]
    if any(status == "failed" for status in statuses):
        return "needs_review"
    return "unreviewed"

def _to_relative(path: str, root: Path) -> str | None:
    if not path:
        return None
    try:
        return str(Path(path).relative_to(root))
    except ValueError:
        return path

def _resolve_existing_clip_audio(
    output_root: Path,
    clip: dict[str, Any] | None,
    *,
    unit_id: str | None = None,
    speaker_id: str | None = None,
    target_lang: str = "en",
) -> str | None:
    """Return a relative artifact path that actually exists on disk.

    Older materialized projects stored ``render/.work/<job>/fit/<seg>.wav``
    (the transient *fitted* clip) which is wiped after the pipeline run, so
    the inspector preview ended up requesting a 404'd file. This helper
    tries the recorded paths first, then falls back to the permanent
    per-segment wav under ``synthesis/voice/<speaker>/segments/<unit_id>.wav``.
    """
    if not output_root:
        return None

    candidates: list[str] = []
    if clip:
        for key in ("audio_artifact_path", "audio_path", "fitted_audio_path", "clip_path"):
            value = clip.get(key)
            if value:
                candidates.append(str(value))

    for raw in candidates:
        # Resolve to absolute, then check existence.
        p = Path(raw)
        if not p.is_absolute():
            p = output_root / raw
        try:
            if p.exists() and p.is_file():
                return _to_relative(str(p), output_root)
        except OSError:
            continue

    # Fallback 1: permanent synthesis wav using known speaker_id.
    if unit_id and speaker_id:
        td = output_root / "synthesis" / "voice" / speaker_id / "segments" / f"{unit_id}.wav"
        if td.exists() and td.is_file():
            return _to_relative(str(td), output_root)

    # Fallback 2: glob across all speakers under synthesis.
    if unit_id:
        try:
            for hit in (output_root / "synthesis" / "voice").glob(f"*/segments/{unit_id}.wav"):
                if hit.is_file():
                    return _to_relative(str(hit), output_root)
        except OSError:
            pass

    return None

def _resynthesize_segment_to_disk(
    *,
    output_root: Path,
    target_lang: str,
    unit_id: str,
    speaker_id: str,
    target_text: str,
    duration_budget_sec: float | None,
    speed: float | None = None,
) -> tuple[Path | None, str | None]:
    """Run the TTS backend for a single segment and overwrite the synthesis wav.

    Returns ``(audio_path, error)``. ``audio_path`` is the final wav location
    (absolute) when synthesis succeeds, ``error`` carries a short reason when
    we cannot synthesize (so the API can degrade gracefully instead of 500).
    """
    if not target_text or not target_text.strip():
        return None, "empty_target_text"
    if not speaker_id:
        return None, "missing_speaker_id"

    speaker_dir = output_root / "synthesis" / "voice" / speaker_id
    speaker_segments_path = speaker_dir / f"speaker_segments.{target_lang}.json"
    if not speaker_segments_path.exists():
        # Fallback: glob in case target_lang differs.
        matches = list(speaker_dir.glob("speaker_segments.*.json"))
        if not matches:
            return None, "speaker_segments_not_found"
        speaker_segments_path = matches[0]

    try:
        speaker_data = json.loads(speaker_segments_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read %s: %s", speaker_segments_path, exc)
        return None, "speaker_segments_unreadable"

    seg_record: dict[str, Any] | None = None
    for item in speaker_data.get("segments", []) or []:
        if str(item.get("segment_id")) == unit_id:
            seg_record = item
            break
    if seg_record is None:
        return None, "segment_not_in_speaker_report"

    reference_path_raw = seg_record.get("reference_path")
    if not reference_path_raw:
        return None, "missing_reference_path"
    reference_path = Path(str(reference_path_raw))
    if not reference_path.exists():
        return None, "reference_audio_missing"

    backend_name_raw = (
        seg_record.get("backend")
        or speaker_data.get("backend")
        or "moss-tts-nano-onnx"
    )
    if isinstance(backend_name_raw, dict):
        backend_name = str(
            backend_name_raw.get("tts_backend")
            or backend_name_raw.get("name")
            or "moss-tts-nano-onnx"
        )
    else:
        backend_name = str(backend_name_raw or "moss-tts-nano-onnx")

    # Build the TTS backend lazily so we don't pay the import cost when
    # synthesize-unit is never called. Tests can monkey-patch
    # ``_TTS_BACKEND_FACTORIES`` to inject a fake.
    factory = _TTS_BACKEND_FACTORIES.get(backend_name)
    if factory is None:
        return None, f"unsupported_backend:{backend_name}"
    try:
        backend = factory()
    except Exception as exc:  # pragma: no cover - depends on local install
        logger.warning("Failed to build TTS backend %s: %s", backend_name, exc)
        return None, "backend_unavailable"

    # Re-prepare the reference into a stable cache directory so subsequent
    # re-synth requests for the same speaker can skip the prep work.
    refs_cache_dir = output_root / _EDITOR_SUBDIR / "refs" / speaker_id
    refs_cache_dir.mkdir(parents=True, exist_ok=True)
    prepared_path = refs_cache_dir / f"{reference_path.stem}_prepared.wav"
    if not prepared_path.exists():
        try:
            from ...dubbing.reference import (
                ReferenceCandidate as _ReferenceCandidate,
                prepare_reference_package as _prepare_reference_package,
            )
            candidate = _ReferenceCandidate(
                profile_id=str(seg_record.get("profile_id") or speaker_id),
                speaker_id=speaker_id,
                path=reference_path,
                text="",
                duration_sec=0.0,
                rms=0.0,
                score=0.0,
                selection_reason="dubbing_editor_resynth",
            )
            _prepare_reference_package(candidate, output_path=prepared_path)
        except Exception as exc:  # pragma: no cover - reference prep edge case
            logger.warning("Failed to prepare reference for %s: %s", unit_id, exc)
            return None, "reference_prep_failed"

    reference_package = _ReferencePackage(
        speaker_id=speaker_id,
        profile_id=str(seg_record.get("profile_id") or speaker_id),
        original_audio_path=reference_path,
        prepared_audio_path=prepared_path,
        text="",
        duration_sec=0.0,
        score=0.0,
        selection_reason="dubbing_editor_resynth",
    )

    source_duration = float(seg_record.get("source_duration_sec") or 0.0)

    # Speed → modify duration_budget. Speed > 1 means "speak faster", which
    # translates to a *shorter* target window for the TTS engine. We clamp to
    # the [0.5, 2.0] range so an ill-chosen value cannot produce nonsensical
    # budgets, and keep ``speed_hint`` in metadata so backends that cannot
    # honour duration (e.g. moss-tts-nano-onnx CLI) at least see the intent.
    speed_factor: float | None = None
    if speed is not None:
        try:
            candidate = float(speed)
        except (TypeError, ValueError):
            candidate = 1.0
        if candidate > 0:
            speed_factor = max(0.5, min(2.0, candidate))

    effective_budget = duration_budget_sec
    if speed_factor and speed_factor != 1.0 and effective_budget and effective_budget > 0:
        effective_budget = effective_budget / speed_factor

    metadata: dict[str, Any] = {"trigger": "dubbing_editor_synthesize_unit"}
    if speed_factor is not None and speed_factor != 1.0:
        metadata["speed_hint"] = speed_factor

    segment_input = _SynthSegmentInput(
        segment_id=unit_id,
        speaker_id=speaker_id,
        target_lang=target_lang,
        target_text=target_text.strip(),
        source_duration_sec=source_duration,
        duration_budget_sec=effective_budget,
        qa_flags=[],
        metadata=metadata,
    )

    final_audio_path = speaker_dir / "segments" / f"{unit_id}.wav"
    final_audio_path.parent.mkdir(parents=True, exist_ok=True)

    # Backends always write to the supplied output_path; first synthesize to a
    # temp file, then atomically replace the existing wav so any in-flight
    # streamed reads see either the old or the new bytes (never partial).
    tmp_audio_path = final_audio_path.with_suffix(".wav.tmp")
    try:
        backend.synthesize(
            reference=reference_package,
            segment=segment_input,
            output_path=tmp_audio_path,
        )
    except Exception as exc:  # pragma: no cover - depends on local TTS
        logger.warning("TTS synthesis failed for %s: %s", unit_id, exc)
        if tmp_audio_path.exists():
            try:
                tmp_audio_path.unlink()
            except OSError:
                pass
        return None, "tts_synthesis_failed"

    if not tmp_audio_path.exists():
        return None, "tts_no_output"

    try:
        os.replace(tmp_audio_path, final_audio_path)
    except OSError as exc:
        logger.warning("Failed to replace %s: %s", final_audio_path, exc)
        return None, "rename_failed"

    return final_audio_path, None

def _build_moss_backend() -> Any:
    from ...dubbing.moss_tts_nano_backend import MossTtsNanoOnnxBackend
    return MossTtsNanoOnnxBackend(requested_device="auto")

def _build_qwen_backend() -> Any:
    from ...dubbing.qwen_tts_backend import QwenTTSBackend
    return QwenTTSBackend(requested_device="auto")

def _build_voxcpm_backend() -> Any:
    from ...dubbing.voxcpm_tts_backend import VoxCPMTTSBackend
    return VoxCPMTTSBackend(requested_device="auto")

def _build_issues(
    benchmark: dict,
    units: list[dict],
    timeline: dict | None = None,
    mix_report: dict | None = None,
) -> list[dict]:
    issues = []
    unit_map = {u["unit_id"]: u for u in units}

    # Map unit times
    unit_times = {u["unit_id"]: u.get("start", 0) for u in units}
    metric_rows = _segment_rows_by_id(timeline or {}, mix_report or {}, benchmark)
    audible_failed_ids = set((benchmark.get("metrics", {}) or {}).get("audible_failed_segment_ids", []) or [])
    seen_issue_ids: set[str] = set()

    def add_issue(
        issue_id: str,
        issue_type: str,
        severity: str,
        seg_id: str,
        title: str,
        description: str,
    ) -> None:
        if issue_id in seen_issue_ids or seg_id not in unit_map:
            return
        seen_issue_ids.add(issue_id)
        unit = unit_map[seg_id]
        time_sec = unit_times.get(seg_id, 0)
        issues.append({
            "issue_id": issue_id,
            "type": issue_type,
            "severity": severity,
            "unit_id": seg_id,
            "character_id": unit.get("character_id"),
            "title": title,
            "description": description,
            "status": "open",
            "time_sec": time_sec,
        })

    for seg_id, seg in metric_rows.items():
        if seg_id not in unit_map:
            continue

        # Speaker similarity
        if seg.get("speaker_similarity_status") == "failed" or seg.get("speaker_status") == "failed":
            add_issue(
                f"speaker_similarity_failed:{seg_id}",
                "speaker_similarity_failed",
                "P1",
                seg_id,
                "声纹一致性失败",
                "speaker_similarity_failed",
            )

        if seg.get("duration_status") == "failed":
            add_issue(
                f"duration_fit_failed:{seg_id}",
                "duration_overrun",
                "P1",
                seg_id,
                "时长适配失败",
                seg.get("fit_strategy") or "duration_failed",
            )

        # Voice gender mismatch
        if seg.get("voice_mismatch") or seg.get("pitch_class_drift"):
            reason = "pitch_class_drift" if seg.get("pitch_class_drift") else "voice_gender_mismatch"
            add_issue(
                f"voice_gender_mismatch:{seg_id}",
                "voice_gender_mismatch",
                "P0",
                seg_id,
                "角色音色冲突",
                reason,
            )

        # Silent / audible
        if seg_id in audible_failed_ids or seg.get("audible_status") == "failed" or seg.get("silent"):
            add_issue(
                f"silent_with_subtitle:{seg_id}",
                "silent_with_subtitle",
                "P0",
                seg_id,
                "字幕有声但无音频",
                "silent_with_subtitle",
            )

        mix_status = str(seg.get("mix_status") or "")
        notes = seg.get("notes") if isinstance(seg.get("notes"), list) else []
        if mix_status.startswith("skipped") or "subtitle_window_not_rendered" in notes:
            add_issue(
                f"render_skipped:{seg_id}",
                "overlap_conflict",
                "P0",
                seg_id,
                "配音片段未渲染",
                mix_status or "subtitle_window_not_rendered",
            )

        # Intelligibility / backread
        if seg.get("intelligibility_status") == "failed":
            add_issue(
                f"translation_untrusted:{seg_id}",
                "translation_untrusted",
                "P2",
                seg_id,
                "文本可信度低",
                "intelligibility_failed",
            )

        if seg.get("overall_status") == "failed":
            row_issue_ids = [issue["issue_id"] for issue in issues if issue["unit_id"] == seg_id]
            if not row_issue_ids:
                add_issue(
                    f"quality_gate_failed:{seg_id}",
                    "translation_untrusted",
                    "P2",
                    seg_id,
                    "质量门禁失败",
                    "overall_status_failed",
                )

    for seg_id in audible_failed_ids:
        add_issue(
            f"silent_with_subtitle:{seg_id}",
            "silent_with_subtitle",
            "P0",
            seg_id,
            "字幕有声但无音频",
            "silent_with_subtitle",
        )

    # Update unit issue_ids
    issue_map: dict[str, list[str]] = {}
    for issue in issues:
        uid = issue["unit_id"]
        issue_map.setdefault(uid, []).append(issue["issue_id"])
    for unit in units:
        unit["issue_ids"] = issue_map.get(unit["unit_id"], [])

    return issues

def _segment_rows_by_id(*payloads: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for payload in payloads:
        for row in _iter_segment_rows(payload):
            seg_id = row.get("segment_id") or row.get("unit_id") or row.get("id")
            if not seg_id:
                continue
            existing = rows.setdefault(seg_id, {})
            existing.update(row)
    return rows

def _iter_segment_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in ("segments", "segment_results", "items", "slots", "placed_segments", "skipped_segments"):
        value = payload.get(key)
        if isinstance(value, list):
            rows.extend(row for row in value if isinstance(row, dict))
    return rows

def _materialize(snapshot: dict, ops_path: Path) -> dict:
    """Apply operations on top of snapshot to produce current state."""
    # Deep copy snapshot fields
    materialized = {k: v for k, v in snapshot.items() if k != "operations"}

    # Parse operations
    ops: list[dict] = []
    if ops_path.exists():
        for line in ops_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    ops.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    # Build mutable structures
    units = {u["unit_id"]: dict(u) for u in materialized.get("units", [])}
    issues = {i["issue_id"]: dict(i) for i in materialized.get("issues", [])}
    characters = {c["character_id"]: dict(c) for c in materialized.get("characters", [])}

    # Apply operations
    for op in ops:
        op_type = op.get("type", "")
        target_id = op.get("target_id", "")
        payload = op.get("payload", {})

        if op_type == "review.set_status":
            unit = units.get(target_id)
            if unit:
                unit["status"] = payload.get("status", unit.get("status"))
            # Also update related issues
            for issue in issues.values():
                if issue.get("unit_id") == target_id and payload.get("status") == "approved":
                    issue["status"] = "resolved"

        elif op_type == "segment.update_text":
            unit = units.get(target_id)
            if unit:
                if "source_text" in payload:
                    unit["source_text"] = payload["source_text"]
                if "target_text" in payload:
                    unit["target_text"] = payload["target_text"]

        elif op_type == "segment.assign_character":
            unit = units.get(target_id)
            if unit:
                unit["character_id"] = payload.get("to_character_id", unit["character_id"])

        elif op_type == "character.rename":
            char = characters.get(target_id)
            if char:
                char["display_name"] = payload.get("name", char["display_name"])

        elif op_type == "character.set_voice":
            char = characters.get(target_id)
            if char:
                char["default_voice"] = payload.get("voice", char["default_voice"])
                char["voice_lock"] = payload.get("voice_lock", char["voice_lock"])

        elif op_type == "issue.set_status":
            issue = issues.get(target_id)
            if issue:
                issue["status"] = payload.get("status", issue["status"])

    # Count stats
    approved_count = sum(1 for u in units.values() if u.get("status") == "approved")

    materialized["units"] = list(units.values())
    materialized["issues"] = list(issues.values())
    materialized["characters"] = list(characters.values())
    materialized["operations"] = ops

    # Summary
    open_issues = [i for i in issues.values() if i.get("status") == "open"]
    p0 = sum(1 for i in open_issues if i.get("severity") == "P0")
    char_review = sum(1 for c in characters.values() if c.get("review_status") == "needs_review")
    bm = materialized.get("quality_benchmark", {})

    materialized["summary"] = {
        "unit_count": len(units),
        "character_count": len(characters),
        "issue_count": len(open_issues),
        "p0_count": p0,
        "candidate_count": 0,
        "approved_count": approved_count,
        "char_review_count": char_review,
        "quality_status": bm.get("status", "unknown"),
        "quality_score": bm.get("score", 0.0),
    }

    return materialized

def _generate_peaks(audio_path: Path, resolution: int = _WAVEFORM_RESOLUTION) -> list[float]:
    """Generate simplified waveform peaks for display."""
    try:
        import numpy as np  # type: ignore

        try:
            import soundfile as sf  # type: ignore
            data, sr = sf.read(str(audio_path), dtype="float32", always_2d=False)
        except Exception:
            try:
                import librosa  # type: ignore
                data, sr = librosa.load(str(audio_path), sr=None, mono=True)
            except Exception:
                return []

        if data.ndim > 1:
            data = data.mean(axis=1)

        # Compute RMS peaks
        hop = max(1, len(data) // resolution)
        peaks = []
        for i in range(0, len(data), hop):
            chunk = data[i : i + hop]
            if len(chunk) == 0:
                break
            rms = float(np.sqrt(np.mean(chunk**2)))
            peaks.append(round(rms, 4))

        if len(peaks) > resolution:
            peaks = peaks[:resolution]

        # Normalize
        max_val = max(peaks) if peaks else 1.0
        if max_val > 0:
            peaks = [round(p / max_val, 4) for p in peaks]

        return peaks
    except Exception as e:
        logger.debug("Peaks generation failed: %s", e)
        return []

def _render_range(
    output_root: Path,
    target_lang: str,
    start_sec: float,
    end_sec: float,
    units: list[dict],
) -> Path | None:
    """Render a preview mix for the given time range."""
    try:
        import numpy as np  # type: ignore
        import soundfile as sf  # type: ignore

        sr = 44100
        duration = end_sec - start_sec
        if duration <= 0:
            return None

        buffer = np.zeros(int(duration * sr), dtype=np.float32)

        for unit in units:
            u_start = unit.get("start", 0)
            u_end = unit.get("end", 0)
            # Only include units overlapping our range
            if u_end < start_sec or u_start > end_sec:
                continue

            clip = unit.get("current_clip", {})
            audio_rel = clip.get("audio_artifact_path") or clip.get("audio_path")
            if not audio_rel:
                continue

            audio_path = output_root / audio_rel if not Path(audio_rel).is_absolute() else Path(audio_rel)
            if not audio_path.exists():
                continue

            try:
                clip_data, clip_sr = sf.read(str(audio_path), dtype="float32", always_2d=False)
                if clip_data.ndim > 1:
                    clip_data = clip_data.mean(axis=1)

                # Resample if needed
                if clip_sr != sr:
                    import math
                    ratio = sr / clip_sr
                    new_len = int(len(clip_data) * ratio)
                    indices = np.linspace(0, len(clip_data) - 1, new_len)
                    clip_data = np.interp(indices, np.arange(len(clip_data)), clip_data).astype(np.float32)

                # Place in buffer
                clip_offset_sec = u_start - start_sec
                clip_offset_samples = int(clip_offset_sec * sr)
                if clip_offset_samples < 0:
                    clip_data = clip_data[-clip_offset_samples:]
                    clip_offset_samples = 0

                end_sample = min(clip_offset_samples + len(clip_data), len(buffer))
                clip_end = end_sample - clip_offset_samples
                if clip_offset_samples < len(buffer) and clip_end > 0:
                    buffer[clip_offset_samples:end_sample] += clip_data[:clip_end]
            except Exception as e:
                logger.debug("Failed to load clip %s: %s", audio_path, e)

        # Normalize
        max_val = np.abs(buffer).max()
        if max_val > 0.9:
            buffer = buffer * (0.9 / max_val)

        # Write output
        previews_dir = output_root / _EDITOR_SUBDIR / "previews" / "ranges"
        previews_dir.mkdir(parents=True, exist_ok=True)

        range_label = f"{int(start_sec * 1000):09d}-{int(end_sec * 1000):09d}"
        out_path = previews_dir / f"{range_label}.wav"
        sf.write(str(out_path), buffer, sr)

        # Write manifest
        manifest = {
            "start_sec": start_sec,
            "end_sec": end_sec,
            "duration_sec": duration,
            "path": str(out_path.relative_to(output_root)),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        manifest_path = previews_dir / "render-range-manifest.json"
        existing = []
        if manifest_path.exists():
            try:
                existing = json.loads(manifest_path.read_text())
                if not isinstance(existing, list):
                    existing = []
            except Exception:
                existing = []
        existing.append(manifest)
        manifest_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2))

        return out_path

    except Exception as e:
        logger.warning("Range render failed: %s", e)
        return None

def _patch_unit_audio_paths(project: dict[str, Any], output_root: Path) -> None:
    """Rewrite each unit's ``current_clip.audio_artifact_path`` to a path
    that *currently exists on disk*, falling back to the permanent synthesis
    wav when the recorded fitted-clip path has been cleaned up.

    This is applied at response time so older projects keep working without
    forcing a re-import / re-run of the pipeline.
    """
    for unit in project.get("units", []) or []:
        clip = unit.get("current_clip")
        if not isinstance(clip, dict):
            continue
        resolved = _resolve_existing_clip_audio(
            output_root,
            clip,
            unit_id=unit.get("unit_id"),
            speaker_id=unit.get("speaker_id"),
        )
        if resolved:
            clip["audio_artifact_path"] = resolved

class OperationRequest(BaseModel):
    operations: list[dict[str, Any]] = Field(
        default_factory=list,
        description="一批针对配音时间轴的编辑操作；每个操作为 dict，含 type 及其参数",
    )

class RenderRangeRequest(BaseModel):
    start_sec: float = Field(description="渲染区间起点（秒）")
    end_sec: float = Field(description="渲染区间终点（秒）")

class SynthesizeUnitRequest(BaseModel):
    unit_id: str = Field(description="要重新合成的配音单元 ID")
    # Optional inline target_text. When the editor's text box is dirty the
    # client should pass the latest draft here so the backend can persist it
    # (as a synthetic ``segment.update_text`` op) *before* running TTS. This
    # makes "click resynth" implicitly auto-save the draft -- no race against
    # the operations mutation.
    target_text: str | None = Field(
        default=None,
        description="可选的最新译文草稿；传入时会在合成前先持久化，实现“点击重合成即自动保存”",
    )
    # Optional per-segment speed hint, e.g. 0.85x ~ 1.20x. The route maps this
    # to a corrected ``duration_budget_sec = source / speed`` so duration-aware
    # backends (Qwen) speed up or slow down naturally without resorting to
    # post-hoc time stretching, while pure CLI backends still receive
    # ``metadata.speed_hint`` for diagnostics.
    speed: float | None = Field(
        default=None, ge=0.5, le=2.0,
        description="可选语速倍率（约 0.5–2.0），映射为时长预算让时长感知后端自然变速",
    )

class AssignCharacterVoiceRequest(BaseModel):
    character_id: str = Field(description="角色 ID")
    voice_path: str = Field(description="该角色绑定的参考音色文件路径")


__all__ = [
    'OperationRequest',
    'RenderRangeRequest',
    'SynthesizeUnitRequest',
    'AssignCharacterVoiceRequest',
    '_EDITOR_SUBDIR',
    '_WAVEFORM_RESOLUTION',
    '_TRACK_PATTERNS',
    '_pending_lock',
    '_get_task',
    '_editor_root',
    '_read_json',
    '_write_json',
    '_append_jsonl',
    '_import_editor_project',
    '_resolve_audio_path',
    '_pregenerate_waveforms_bg',
    '_extract_clip',
    '_build_characters',
    '_normalize_review_status',
    '_classify_pitch',
    '_build_units',
    '_unit_status_from_quality',
    '_to_relative',
    '_resolve_existing_clip_audio',
    '_resynthesize_segment_to_disk',
    '_build_moss_backend',
    '_build_qwen_backend',
    '_build_voxcpm_backend',
    '_build_issues',
    '_segment_rows_by_id',
    '_iter_segment_rows',
    '_materialize',
    '_generate_peaks',
    '_render_range',
    '_patch_unit_audio_paths',
]
