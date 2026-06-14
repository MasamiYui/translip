"""HTTP routes for the in-browser dubbing editor.

Thin FastAPI layer: each handler parses its request, delegates to
``dubbing_editor_service``, and shapes the response. All helper logic and
models live in :mod:`translip.server.routes.dubbing_editor_service`.
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

from fastapi import APIRouter, Depends, HTTPException, Path as PathParam, Query
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

router = APIRouter(prefix="/api/tasks", tags=["dubbing-editor"])

from .dubbing_editor_service import *  # noqa: E402,F401,F403


@router.get("/{task_id}/dubbing-editor", summary="获取配音编辑器状态")
def get_dubbing_editor(
    task_id: str = PathParam(description="任务 ID"),
    replay_to: int | None = Query(None, description="部分回放：仅应用前 N 条编辑操作并重新物化状态，留空则返回当前完整状态"),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """获取配音编辑器的物化状态（对白单元、说话人、角色等）。

    若编辑工程尚未导入，则先从流水线产物导入；可选 replay_to 用于回放历史操作的某个前缀以预览中间状态。
    """
    task = _get_task(session, task_id)
    output_root = Path(task.output_root).resolve()
    editor_root = _editor_root(task.output_root)
    mat_path = editor_root / "materialized.current.json"

    if not mat_path.exists():
        # Try to import
        result = _import_editor_project(task)
        _patch_unit_audio_paths(result, output_root)
        return result

    if replay_to is not None:
        # Partial replay: only apply operations[0..replay_to]
        snapshot_path = editor_root / "initial_snapshot.json"
        ops_path = editor_root / "operations.jsonl"
        if snapshot_path.exists():
            snapshot = _read_json(snapshot_path)
            # Read all ops and truncate
            all_ops: list[dict[str, Any]] = []
            if ops_path.exists():
                for line in ops_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line:
                        try:
                            all_ops.append(json.loads(line))
                        except Exception:
                            pass
            # Write temp ops file with truncated ops
            import tempfile
            with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tf:
                tmp_path = Path(tf.name)
                for op in all_ops[:replay_to]:
                    tf.write(json.dumps(op, ensure_ascii=False) + "\n")
            try:
                result = _materialize(snapshot, tmp_path)
            finally:
                tmp_path.unlink(missing_ok=True)
            _patch_unit_audio_paths(result, output_root)
            return result

    materialized = _read_json(mat_path)
    _patch_unit_audio_paths(materialized, output_root)
    return materialized

@router.post("/{task_id}/dubbing-editor/import", summary="导入编辑工程")
def import_dubbing_editor(
    task_id: str = PathParam(description="任务 ID"),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """从流水线产物导入并初始化配音编辑工程，生成初始快照与物化状态。"""
    task = _get_task(session, task_id)
    return _import_editor_project(task)

@router.post("/{task_id}/dubbing-editor/operations", summary="保存编辑操作")
def save_operations(
    task_id: str = PathParam(description="任务 ID"),
    body: OperationRequest = ...,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """追加一批编辑操作到操作日志，并基于初始快照重新物化当前状态。

    若编辑工程尚未初始化会先自动导入；返回本次成功应用的操作数与最新状态摘要。
    """
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

@router.post("/{task_id}/dubbing-editor/render-range", summary="渲染时间区间预览")
def render_range(
    task_id: str = PathParam(description="任务 ID"),
    body: RenderRangeRequest = ...,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """对指定时间区间内的对白单元做混音渲染，生成预览音频产物并返回其访问 URL。"""
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

@router.get("/{task_id}/dubbing-editor/waveforms/{track}", summary="获取音轨波形")
def get_waveform(
    task_id: str = PathParam(description="任务 ID"),
    track: str = PathParam(description="音轨名，如 original/background/dub/preview_mix 等"),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """获取指定音轨的波形峰值数据；已缓存则直接返回，未缓存则在后台异步生成并返回 pending 状态。"""
    task = _get_task(session, task_id)
    output_root = Path(task.output_root).resolve()
    target_lang = task.target_lang or "en"

    track_patterns: dict[str, list[str]] = {
        **_TRACK_PATTERNS,
        "dub": [f"render/voice/dub_voice.{target_lang}.wav"],
        "preview_mix": [f"render/voice/preview_mix.{target_lang}.wav"],
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

@router.get("/{task_id}/dubbing-editor/clip-preview", summary="获取片段预览")
def get_clip_preview(
    task_id: str = PathParam(description="任务 ID"),
    start_sec: float = Query(description="片段起始时间（秒）"),
    end_sec: float = Query(description="片段结束时间（秒）"),
    track: str = Query("original", description="音轨名，默认 original，可选 dub/preview_mix/mix 等"),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """从完整音轨中裁出一段短音频用于 A/B 对比，返回该片段产物的访问 URL（结果会缓存复用）。"""
    task = _get_task(session, task_id)
    output_root = Path(task.output_root).resolve()
    target_lang = task.target_lang or "en"

    track_patterns: dict[str, list[str]] = {
        **_TRACK_PATTERNS,
        "dub": [f"render/voice/dub_voice.{target_lang}.wav"],
        "preview_mix": [f"render/voice/preview_mix.{target_lang}.wav"],
        "mix": [f"render/voice/preview_mix.{target_lang}.wav"],
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

@router.post("/{task_id}/dubbing-editor/synthesize-unit", summary="重新合成单元配音")
def synthesize_unit(
    task_id: str = PathParam(description="任务 ID"),
    body: SynthesizeUnitRequest = ...,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """对单个对白单元重新做语音合成（TTS），并把请求记录为编辑操作。

    若随请求带上了改动后的译文，会先以 segment.update_text 操作保存草稿再合成；
    合成完成后更新片段音频文件，返回 audio_artifact_path 与 synthesized_at 供前端做缓存刷新。
    """
    task = _get_task(session, task_id)
    output_root = Path(task.output_root).resolve()
    editor_root = _editor_root(task.output_root)
    ops_path = editor_root / "operations.jsonl"

    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()

    # Auto-save dirty target_text before kicking off TTS. The frontend sends
    # the textarea draft inline whenever it differs from the last saved
    # version; we persist it here as a regular ``segment.update_text`` op so
    # the operation history stays linear and undo/redo keeps working.
    if body.target_text is not None:
        draft = body.target_text.strip()
        if draft:
            update_op = {
                "op_id": f"op_{uuid.uuid4().hex[:12]}",
                "type": "segment.update_text",
                "target_id": body.unit_id,
                "payload": {"target_text": draft},
                "author": "local_user",
                "created_at": now,
            }
            _append_jsonl(ops_path, update_op)

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
    materialized: dict[str, Any] = {}
    if snapshot_path.exists():
        snapshot = _read_json(snapshot_path)
        materialized = _materialize(snapshot, ops_path)
        _write_json(editor_root / "materialized.current.json", materialized)

    # Locate the unit so we know which speaker / target_text / duration to
    # re-synthesize, then drive the TTS backend synchronously. Synchronous
    # execution keeps the inspector flow simple: the audio file on disk is
    # already updated by the time the response returns, so the client only
    # needs to cache-bust to hear the new content.
    matched_unit: dict[str, Any] | None = None
    for unit in materialized.get("units", []) or []:
        if unit.get("unit_id") == body.unit_id:
            matched_unit = unit
            break

    audio_artifact_path: str | None = None
    synthesis_status = "queued"
    synthesis_error: str | None = None

    if matched_unit is None:
        synthesis_error = "unit_not_found"
    else:
        clip = matched_unit.get("current_clip") or {}
        speaker_id = str(matched_unit.get("speaker_id") or "")
        target_text = str(matched_unit.get("target_text") or "")
        target_lang = str(materialized.get("target_lang") or "en")
        duration_budget_sec: float | None = None
        for key in ("duration_budget_sec", "duration", "source_duration_sec"):
            value = matched_unit.get(key) if matched_unit else None
            if isinstance(value, (int, float)) and value > 0:
                duration_budget_sec = float(value)
                break

        synthesized_path, synthesis_error = _resynthesize_segment_to_disk(
            output_root=output_root,
            target_lang=target_lang,
            unit_id=body.unit_id,
            speaker_id=speaker_id,
            target_text=target_text,
            duration_budget_sec=duration_budget_sec,
            speed=body.speed,
        )

        if synthesized_path is not None:
            synthesis_status = "synthesized"
            try:
                audio_artifact_path = str(synthesized_path.relative_to(output_root))
            except ValueError:
                audio_artifact_path = str(synthesized_path)
        else:
            # Synthesis failed (or backend unavailable); fall back to mtime
            # bump so at least the existing wav reloads in the player.
            audio_artifact_path = _resolve_existing_clip_audio(
                output_root,
                clip,
                unit_id=matched_unit.get("unit_id"),
                speaker_id=matched_unit.get("speaker_id"),
            )
            if not audio_artifact_path:
                audio_artifact_path = (
                    clip.get("audio_artifact_path")
                    or clip.get("audio_path")
                )
            if audio_artifact_path:
                candidate = output_root / audio_artifact_path
                try:
                    if candidate.exists():
                        ts = now_dt.timestamp()
                        os.utime(candidate, (ts, ts))
                except OSError as exc:  # pragma: no cover - best-effort
                    logger.warning("Failed to bump mtime for %s: %s", candidate, exc)

    message = (
        "Re-synthesized. The clip preview will refresh to the latest version."
        if synthesis_status == "synthesized"
        else f"Re-synthesis could not be completed: {synthesis_error or 'unknown_error'}."
    )

    return {
        "status": synthesis_status,
        "unit_id": body.unit_id,
        "audio_artifact_path": audio_artifact_path,
        "synthesized_at": now,
        "error": synthesis_error,
        "message": message,
    }

@router.post("/{task_id}/dubbing-editor/assign-character-voice", summary="指派角色音色")
def assign_character_voice(
    task_id: str = PathParam(description="任务 ID"),
    body: AssignCharacterVoiceRequest = ...,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """为某个角色重新指派默认音色参考路径，并把该改动记录为编辑操作、更新物化状态。"""
    task = _get_task(session, task_id)
    editor_root = _editor_root(task.output_root)
    ops_path = editor_root / "operations.jsonl"

    now = datetime.now(timezone.utc).isoformat()
    op_record = {
        "op_id": f"op_{uuid.uuid4().hex[:12]}",
        "type": "character.assign_voice",
        "target_id": body.character_id,
        "payload": {"voice_path": body.voice_path},
        "author": "local_user",
        "created_at": now,
    }
    _append_jsonl(ops_path, op_record)

    snapshot_path = editor_root / "initial_snapshot.json"
    if snapshot_path.exists():
        snapshot = _read_json(snapshot_path)
        materialized = _materialize(snapshot, ops_path)
        # Patch character voice in materialized state
        for char in materialized.get("characters", []):
            if char.get("character_id") == body.character_id:
                if "default_voice" not in char or char["default_voice"] is None:
                    char["default_voice"] = {}
                char["default_voice"]["reference_path"] = body.voice_path
                break
        _write_json(editor_root / "materialized.current.json", materialized)

    return {"ok": True, "character_id": body.character_id, "voice_path": body.voice_path}

@router.get("/{task_id}/dubbing-editor/backtranslate", summary="配音回译校验")
def backtranslate(
    task_id: str = PathParam(description="任务 ID"),
    unit_id: str = Query(description="对白单元 ID"),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """对某个对白单元的配音音频做回译校验：尝试用 ASR 听写并与期望译文比对相似度。

    若本地无可用的 faster-whisper ASR 后端，则回退为占位结果（听写文本等于期望译文、匹配分为满分），便于前端正常渲染。
    """
    task = _get_task(session, task_id)
    editor_root = _editor_root(task.output_root)
    mat_path = editor_root / "materialized.current.json"
    if not mat_path.exists():
        raise HTTPException(status_code=404, detail="Editor project not found")

    project = _read_json(mat_path)
    unit = next((u for u in project.get("units", []) if u.get("unit_id") == unit_id), None)
    if unit is None:
        raise HTTPException(status_code=404, detail=f"Unit {unit_id!r} not found")

    target_text: str = unit.get("target_text", "")

    # Try to load audio and run fast ASR if faster-whisper is available
    heard_text = ""
    match_score = 0.0
    clip = unit.get("current_clip") or {}
    audio_path_rel = clip.get("audio_artifact_path")
    if audio_path_rel:
        audio_abs = Path(task.output_root).resolve() / audio_path_rel
        if audio_abs.exists():
            try:
                from faster_whisper import WhisperModel  # type: ignore

                model = WhisperModel("tiny", device="cpu", compute_type="int8")
                segments, _ = model.transcribe(str(audio_abs), beam_size=1)
                heard_text = " ".join(s.text.strip() for s in segments).strip()
            except Exception as e:
                logger.debug("Back-translation ASR skipped: %s", e)

    if heard_text and target_text:
        # Simple character-level overlap score
        s1, s2 = set(heard_text.lower()), set(target_text.lower())
        overlap = len(s1 & s2) / max(len(s1 | s2), 1)
        match_score = round(overlap, 3)

    return {
        "unit_id": unit_id,
        "expected_text": target_text,
        "heard_text": heard_text or target_text,  # fallback to expected when ASR not available
        "match_score": match_score if heard_text else 1.0,
        "asr_available": bool(heard_text),
    }

@router.get("/{task_id}/dubbing-editor/video-preview", summary="预览源视频")
def get_video_preview(
    task_id: str = PathParam(description="任务 ID"),
    session: Session = Depends(get_session),
) -> FileResponse:
    """以文件流形式返回任务的源视频，供编辑器内预览（按扩展名推断 MIME 类型）。"""
    task = _get_task(session, task_id)
    if not task.input_path:
        raise HTTPException(status_code=404, detail="No source video for this task")
    video_path = Path(task.input_path)
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Source video file not found")
    # Determine MIME type from suffix
    suffix = video_path.suffix.lower()
    media_type_map = {
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
        ".mkv": "video/x-matroska",
        ".webm": "video/webm",
        ".avi": "video/x-msvideo",
    }
    media_type = media_type_map.get(suffix, "video/mp4")
    return FileResponse(str(video_path), media_type=media_type)
