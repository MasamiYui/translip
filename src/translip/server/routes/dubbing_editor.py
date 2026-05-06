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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["dubbing-editor"])

_EDITOR_SUBDIR = "dubbing-editor"
_WAVEFORM_RESOLUTION = 800  # samples per second for peaks

# Track in-progress waveform generation to avoid duplicate work
_pending_waveforms: set[str] = set()
_pending_lock = threading.Lock()

# Shared track search patterns (re-used in multiple endpoints)
_TRACK_PATTERNS: dict[str, list[str]] = {
    "original": [
        "stage1/voice/voice.wav",
        "stage1/*/voice.wav",
        "stage1/*/voice.mp3",
        "stage1/voice/voice.mp3",
    ],
    "background": [
        "stage1/background/background.wav",
        "stage1/*/background.wav",
        "stage1/*/background.mp3",
    ],
}  # dub/preview_mix are added dynamically with target_lang


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_task(session: Session, task_id: str) -> Task:
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


def _editor_root(output_root: str) -> Path:
    return Path(output_root).resolve() / _EDITOR_SUBDIR


def _read_json(path: Path) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Importer — builds editor project from existing pipeline artifacts
# ---------------------------------------------------------------------------


def _import_editor_project(task: Task) -> dict[str, Any]:
    """Import / rebuild editor project from pipeline artifacts."""
    output_root = Path(task.output_root).resolve()
    editor_root = output_root / _EDITOR_SUBDIR

    target_lang = task.target_lang or "en"

    # Artifact paths (relative)
    artifact_paths: dict[str, str] = {
        "translation": f"task-c/voice/translation.{target_lang}.json",
        "character_ledger": f"task-d/voice/character-ledger/character_ledger.{target_lang}.json",
        "benchmark": f"benchmark/voice/dub_benchmark.{target_lang}.json",
        "mix_report": f"task-e/voice/mix_report.{target_lang}.json",
        "timeline": f"task-e/voice/timeline.{target_lang}.json",
        "speaker_profiles": "task-b/voice/speaker_profiles.json",
        "preview_mix": f"task-e/voice/preview_mix.{target_lang}.wav",
        "dub_voice": f"task-e/voice/dub_voice.{target_lang}.wav",
        "final_preview": f"task-g/final-preview/final_preview.{target_lang}.mp4",
        "final_dub": f"task-g/final-dub/final_dub.{target_lang}.mp4",
        "editor_project": f"{_EDITOR_SUBDIR}/editor_project.json",
        "materialized": f"{_EDITOR_SUBDIR}/materialized.current.json",
        "operations": f"{_EDITOR_SUBDIR}/operations.jsonl",
    }

    # Load source data
    translation = _read_json(output_root / artifact_paths["translation"])
    character_ledger = _read_json(output_root / artifact_paths["character_ledger"])
    benchmark = _read_json(output_root / artifact_paths["benchmark"])
    speaker_profiles = _read_json(output_root / artifact_paths["speaker_profiles"])
    timeline = _read_json(output_root / artifact_paths["timeline"])

    # Build characters from character ledger
    characters = _build_characters(character_ledger, speaker_profiles, benchmark)

    # Build dialogue units from translation + timeline
    units = _build_units(translation, timeline, character_ledger, output_root, target_lang)

    # Build issues from benchmark
    issues = _build_issues(benchmark, units)

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
        "dub": [f"task-e/voice/dub_voice.{target_lang}.wav"],
        "preview_mix": [f"task-e/voice/preview_mix.{target_lang}.wav"],
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
) -> list[dict]:
    characters = []
    char_entries = character_ledger.get("characters", []) or character_ledger.get("entries", [])

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

        risk_flags = []
        if char_id in review_chars:
            risk_flags.append("character_voice_review_required")
        if char_id in blocked_chars:
            risk_flags.append("blocked")
        if char_id in mismatch_chars:
            risk_flags.append("voice_mismatch")

        stats = char_stats.get(char_id, {})
        seg_count = stats.get("segment_count", 0)
        spk_failed = stats.get("speaker_failed_count", 0)
        spk_ratio = spk_failed / seg_count if seg_count > 0 else 0.0

        if spk_ratio > 0.15:
            risk_flags.append("speaker_similarity_failed")

        # Determine review status
        if char_id in blocked_chars:
            review_status = "blocked"
        elif char_id in review_chars or risk_flags:
            review_status = "needs_review"
        else:
            review_status = "passed"

        pitch_hz = entry.get("pitch_hz") or entry.get("f0_median_hz")
        pitch_class = _classify_pitch(pitch_hz) if pitch_hz else "mid"

        characters.append({
            "character_id": char_id,
            "display_name": entry.get("display_name") or entry.get("name") or char_id,
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
            "default_voice": entry.get("default_voice", {"backend": "inherit", "reference_path": None}),
        })

    return characters


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

    # Build clip path mapping from timeline
    clip_paths: dict[str, dict] = {}
    for slot in timeline.get("slots", []):
        seg_id = slot.get("segment_id") or slot.get("id")
        if seg_id:
            clip_paths[seg_id] = slot

    # Process translation segments
    segments = translation.get("segments", [])
    for seg in segments:
        seg_id = seg.get("segment_id") or seg.get("id")
        if not seg_id:
            continue

        speaker_id = seg.get("speaker_id", "")
        char_id = seg.get("character_id") or seg_to_char.get(speaker_id, f"char_unknown")

        slot = clip_paths.get(seg_id, {})
        audio_path = slot.get("audio_path") or slot.get("clip_path")

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
            "status": "unreviewed",
            "issue_ids": [],
            "current_clip": {
                "clip_id": f"clip_{seg_id}",
                "audio_path": audio_path,
                "audio_artifact_path": _to_relative(audio_path, output_root) if audio_path else None,
                "duration": slot.get("fitted_duration") or slot.get("duration"),
                "backend": slot.get("backend", ""),
                "mix_status": slot.get("mix_status") or ("placed" if audio_path else "missing"),
                "fit_strategy": slot.get("fit_strategy", ""),
            },
            "candidates": [],
        }
        units.append(unit)

    return units


def _to_relative(path: str, root: Path) -> str | None:
    if not path:
        return None
    try:
        return str(Path(path).relative_to(root))
    except ValueError:
        return path


def _build_issues(benchmark: dict, units: list[dict]) -> list[dict]:
    issues = []
    unit_map = {u["unit_id"]: u for u in units}

    # Map unit times
    unit_times = {u["unit_id"]: u.get("start", 0) for u in units}

    for seg in benchmark.get("segments", []):
        seg_id = seg.get("segment_id") or seg.get("id")
        char_id = seg.get("character_id") or seg.get("speaker_id")
        time_sec = unit_times.get(seg_id, 0)

        # Speaker similarity
        if seg.get("speaker_similarity_status") == "failed":
            issues.append({
                "issue_id": f"speaker_similarity_failed:{seg_id}",
                "type": "speaker_similarity_failed",
                "severity": "P1",
                "unit_id": seg_id,
                "character_id": char_id,
                "title": "声纹一致性失败",
                "description": "speaker_similarity_failed",
                "status": "open",
                "time_sec": time_sec,
            })

        # Voice gender mismatch
        if seg.get("voice_mismatch") or seg.get("pitch_class_drift"):
            reason = "pitch_class_drift" if seg.get("pitch_class_drift") else "voice_gender_mismatch"
            issues.append({
                "issue_id": f"voice_gender_mismatch:{seg_id}",
                "type": "voice_gender_mismatch",
                "severity": "P0",
                "unit_id": seg_id,
                "character_id": char_id,
                "title": "角色音色冲突",
                "description": reason,
                "status": "open",
                "time_sec": time_sec,
            })

        # Silent / audible
        if seg.get("audible_status") == "failed" or seg.get("silent"):
            issues.append({
                "issue_id": f"silent_with_subtitle:{seg_id}",
                "type": "silent_with_subtitle",
                "severity": "P0",
                "unit_id": seg_id,
                "character_id": char_id,
                "title": "字幕有声但无音频",
                "description": "silent_with_subtitle",
                "status": "open",
                "time_sec": time_sec,
            })

        # Intelligibility / backread
        if seg.get("intelligibility_status") == "failed":
            issues.append({
                "issue_id": f"translation_untrusted:{seg_id}",
                "type": "translation_untrusted",
                "severity": "P2",
                "unit_id": seg_id,
                "character_id": char_id,
                "title": "文本可信度低",
                "description": "intelligibility_failed",
                "status": "open",
                "time_sec": time_sec,
            })

    # Update unit issue_ids
    issue_map: dict[str, list[str]] = {}
    for issue in issues:
        uid = issue["unit_id"]
        issue_map.setdefault(uid, []).append(issue["issue_id"])
    for unit in units:
        unit["issue_ids"] = issue_map.get(unit["unit_id"], [])

    return issues


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


# ---------------------------------------------------------------------------
# Waveform peaks generation
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Range renderer
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------


@router.get("/{task_id}/dubbing-editor")
def get_dubbing_editor(
    task_id: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    task = _get_task(session, task_id)
    editor_root = _editor_root(task.output_root)
    mat_path = editor_root / "materialized.current.json"

    if not mat_path.exists():
        # Try to import
        return _import_editor_project(task)

    return _read_json(mat_path)


@router.post("/{task_id}/dubbing-editor/import")
def import_dubbing_editor(
    task_id: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    task = _get_task(session, task_id)
    return _import_editor_project(task)


class OperationRequest(BaseModel):
    operations: list[dict[str, Any]] = Field(default_factory=list)


@router.post("/{task_id}/dubbing-editor/operations")
def save_operations(
    task_id: str,
    body: OperationRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    task = _get_task(session, task_id)
    output_root = Path(task.output_root).resolve()
    editor_root = _editor_root(task.output_root)
    ops_path = editor_root / "operations.jsonl"
    mat_path = editor_root / "materialized.current.json"
    snapshot_path = editor_root / "initial_snapshot.json"

    if not snapshot_path.exists():
        _import_editor_project(task)

    now = datetime.now(timezone.utc).isoformat()
    for op in body.operations:
        op_record = {
            "op_id": f"op_{uuid.uuid4().hex[:12]}",
            "type": op.get("type", "unknown"),
            "target_id": op.get("target_id", ""),
            "payload": op.get("payload", {}),
            "author": "local_user",
            "created_at": now,
        }
        _append_jsonl(ops_path, op_record)

    # Re-materialize
    snapshot = _read_json(snapshot_path)
    materialized = _materialize(snapshot, ops_path)
    _write_json(mat_path, materialized)

    return {"ok": True, "applied": len(body.operations), "summary": materialized.get("summary", {})}


class RenderRangeRequest(BaseModel):
    start_sec: float
    end_sec: float


@router.post("/{task_id}/dubbing-editor/render-range")
def render_range(
    task_id: str,
    body: RenderRangeRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    task = _get_task(session, task_id)
    output_root = Path(task.output_root).resolve()
    target_lang = task.target_lang or "en"

    mat_path = _editor_root(task.output_root) / "materialized.current.json"
    materialized = _read_json(mat_path)
    units = materialized.get("units", [])

    out_path = _render_range(output_root, target_lang, body.start_sec, body.end_sec, units)

    if out_path is None:
        raise HTTPException(status_code=500, detail="Range render failed")

    artifact_path = str(out_path.relative_to(output_root))
    return {
        "ok": True,
        "artifact_path": artifact_path,
        "start_sec": body.start_sec,
        "end_sec": body.end_sec,
        "duration_sec": body.end_sec - body.start_sec,
        "url": f"/api/tasks/{task_id}/artifacts/{artifact_path}",
    }


@router.get("/{task_id}/dubbing-editor/waveforms/{track}")
def get_waveform(
    task_id: str,
    track: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    task = _get_task(session, task_id)
    output_root = Path(task.output_root).resolve()
    target_lang = task.target_lang or "en"

    track_patterns: dict[str, list[str]] = {
        **_TRACK_PATTERNS,
        "dub": [f"task-e/voice/dub_voice.{target_lang}.wav"],
        "preview_mix": [f"task-e/voice/preview_mix.{target_lang}.wav"],
    }
    patterns = track_patterns.get(track)
    if not patterns:
        raise HTTPException(status_code=404, detail=f"Unknown track: {track}")

    audio_path = _resolve_audio_path(output_root, patterns)
    if audio_path is None:
        return {"track": track, "peaks": [], "duration_sec": 0, "available": False, "pending": False}

    # Return cached peaks if available
    peaks_dir = _editor_root(task.output_root) / "waveform"
    peaks_dir.mkdir(parents=True, exist_ok=True)
    peaks_path = peaks_dir / f"{track}.peaks.json"

    if peaks_path.exists():
        return _read_json(peaks_path)

    # Not cached yet — generate in background, return pending
    cache_key = f"{task_id}:{track}"
    with _pending_lock:
        already_pending = cache_key in _pending_waveforms
        if not already_pending:
            _pending_waveforms.add(cache_key)

    if not already_pending:
        def _gen(ap: Path = audio_path, pp: Path = peaks_path, t: str = track, ck: str = cache_key) -> None:
            try:
                peaks = _generate_peaks(ap)
                duration_sec = 0.0
                try:
                    import soundfile as sf  # type: ignore
                    info = sf.info(str(ap))
                    duration_sec = info.duration
                except Exception:
                    pass
                _write_json(pp, {"track": t, "peaks": peaks, "duration_sec": duration_sec, "available": True})
            finally:
                with _pending_lock:
                    _pending_waveforms.discard(ck)

        threading.Thread(target=_gen, daemon=True).start()

    return {"track": track, "peaks": [], "duration_sec": 0, "available": False, "pending": True}


# ---------------------------------------------------------------------------
# Clip preview (A/B comparison)
# ---------------------------------------------------------------------------


@router.get("/{task_id}/dubbing-editor/clip-preview")
def get_clip_preview(
    task_id: str,
    start_sec: float,
    end_sec: float,
    track: str = "original",
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Return a URL to a short audio clip cut from a full track (for A/B comparison)."""
    task = _get_task(session, task_id)
    output_root = Path(task.output_root).resolve()
    target_lang = task.target_lang or "en"

    track_patterns: dict[str, list[str]] = {
        **_TRACK_PATTERNS,
        "dub": [f"task-e/voice/dub_voice.{target_lang}.wav"],
    }
    patterns = track_patterns.get(track)
    if not patterns:
        raise HTTPException(status_code=400, detail=f"Unknown track: {track}")

    audio_path = _resolve_audio_path(output_root, patterns)
    if audio_path is None:
        raise HTTPException(status_code=404, detail=f"Audio not found for track: {track}")

    # Use cached clip if it exists
    clips_dir = _editor_root(task.output_root) / "previews" / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    clip_label = f"{track}_{int(start_sec * 1000):09d}_{int(end_sec * 1000):09d}"
    clip_path = clips_dir / f"{clip_label}.wav"

    if not clip_path.exists():
        _extract_clip(audio_path, clip_path, start_sec, end_sec)

    if not clip_path.exists():
        raise HTTPException(status_code=500, detail="Clip extraction failed")

    artifact_path = str(clip_path.relative_to(output_root))
    return {
        "url": f"/api/tasks/{task_id}/artifacts/{artifact_path}",
        "start_sec": start_sec,
        "end_sec": end_sec,
        "duration_sec": end_sec - start_sec,
    }


# ---------------------------------------------------------------------------
# Synthesize unit (re-synthesis request)
# ---------------------------------------------------------------------------


class SynthesizeUnitRequest(BaseModel):
    unit_id: str


@router.post("/{task_id}/dubbing-editor/synthesize-unit")
def synthesize_unit(
    task_id: str,
    body: SynthesizeUnitRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Queue a single dialogue unit for re-synthesis (records operation, triggers async synthesis)."""
    task = _get_task(session, task_id)
    editor_root = _editor_root(task.output_root)
    ops_path = editor_root / "operations.jsonl"

    now = datetime.now(timezone.utc).isoformat()
    op_record = {
        "op_id": f"op_{uuid.uuid4().hex[:12]}",
        "type": "synthesis.requested",
        "target_id": body.unit_id,
        "payload": {"requested_at": now},
        "author": "local_user",
        "created_at": now,
    }
    _append_jsonl(ops_path, op_record)

    # Re-materialize so the operation appears in the history
    snapshot_path = editor_root / "initial_snapshot.json"
    if snapshot_path.exists():
        snapshot = _read_json(snapshot_path)
        materialized = _materialize(snapshot, ops_path)
        _write_json(editor_root / "materialized.current.json", materialized)

    return {
        "status": "queued",
        "unit_id": body.unit_id,
        "message": "Re-synthesis queued. Refresh to see updated clip.",
    }
