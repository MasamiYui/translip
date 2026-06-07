from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, Optional

from sqlmodel import Session, select

from ..config import (
    CACHE_ROOT,
    DEFAULT_PIPELINE_OUTPUT_ROOT,
    DEFAULT_RENDER_OUTPUT_SAMPLE_RATE,
)
from ..orchestration.graph import resolve_template_plan
from ..orchestration.nodes import NODE_REGISTRY
from ..types import PipelineRequest, SubtitleStyle
from .database import engine
from .models import Task, TaskLog, TaskStage
from .task_config import (
    normalize_task_config,
    normalize_task_delivery_config,
    normalize_task_storage,
)
from .schemas import CreateTaskRequest, TaskConfigInput

logger = logging.getLogger(__name__)

# Cooperative cancellation: task_id -> Event. stop_task() sets the event and the
# pipeline thread (run_pipeline) polls it via should_cancel to SIGTERM the active
# stage subprocess. Mirrors atomic_tools.job_manager._cancel_events.
_cancel_events: Dict[str, threading.Event] = {}
_cancel_events_lock = threading.Lock()


def _now_task_id() -> str:
    return "task-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _build_pipeline_request(task: Task) -> PipelineRequest:
    cfg: Dict[str, Any] = normalize_task_config(task.config)
    delivery_cfg: Dict[str, Any] = normalize_task_delivery_config(task.config)
    output_root = Path(task.output_root)

    return PipelineRequest(
        input_path=task.input_path,
        output_root=output_root,
        template_id=cfg.get("template", "asr-dub-basic"),
        delivery_policy={
            "video_source": cfg.get("video_source", "original"),
            "audio_source": cfg.get("audio_source", "both"),
            "subtitle_source": cfg.get("subtitle_source", "asr"),
        },
        erase_backend=cfg.get("erase_backend", "sttn"),
        erase_device=cfg.get("erase_device", "auto"),
        erase_max_load=int(cfg.get("erase_max_load", 50)),
        erase_mask_dilate_x=int(cfg.get("erase_mask_dilate_x", 12)),
        erase_mask_dilate_y=int(cfg.get("erase_mask_dilate_y", 8)),
        erase_event_lead_frames=int(cfg.get("erase_event_lead_frames", 3)),
        erase_event_trail_frames=int(cfg.get("erase_event_trail_frames", 8)),
        erase_neighbor_stride=int(cfg.get("erase_neighbor_stride", 5)),
        erase_reference_length=int(cfg.get("erase_reference_length", 10)),
        ocr_sample_interval=float(cfg.get("ocr_sample_interval", 0.25)),
        ocr_position_mode=cfg.get("ocr_position_mode", "auto"),
        ocr_extraction_mode=cfg.get("ocr_extraction_mode", "conservative"),
        target_lang=task.target_lang,
        translation_backend=cfg.get("translation_backend", "local-m2m100"),
        translation_batch_size=int(cfg.get("translation_batch_size", 4)),
        tts_backend=cfg.get("tts_backend", "moss-tts-nano-onnx"),
        device=cfg.get("device", "auto"),
        run_from_stage=cfg.get("run_from_stage", "stage1"),
        run_to_stage=cfg.get("run_to_stage", "task-g"),
        reuse_existing=cfg.get("use_cache", True),
        separation_mode=cfg.get("separation_mode", "dialogue"),
        separation_quality=cfg.get("separation_quality", "balanced"),
        stage1_output_format=cfg.get("stage1_output_format", "mp3"),
        audio_stream_index=int(cfg.get("audio_stream_index", 0)),
        asr_model=cfg.get("asr_model", "paraformer-zh"),
        asr_backend=cfg.get("asr_backend", "funasr"),
        diarizer_backend=cfg.get("diarizer_backend", "ecapa"),
        enable_diarization=bool(cfg.get("enable_diarization", True)),
        generate_srt=bool(cfg.get("generate_srt", True)),
        vad_filter=bool(cfg.get("vad_filter", True)),
        vad_min_silence_duration_ms=int(cfg.get("vad_min_silence_duration_ms", 400)),
        beam_size=int(cfg.get("beam_size", 5)),
        best_of=int(cfg.get("best_of", 5)),
        temperature=float(cfg.get("temperature", 0.0)),
        condition_on_previous_text=bool(cfg.get("condition_on_previous_text", False)),
        transcription_language=task.source_lang,
        top_k=cfg.get("top_k", 3),
        fit_policy=cfg.get("fit_policy", "conservative"),
        fit_backend=cfg.get("fit_backend", "atempo"),
        mix_profile=cfg.get("mix_profile", "preview"),
        ducking_mode=cfg.get("ducking_mode", "static"),
        background_gain_db=cfg.get("background_gain_db", -8.0),
        window_ducking_db=float(cfg.get("window_ducking_db", -3.0)),
        max_compress_ratio=float(cfg.get("max_compress_ratio", 1.45)),
        output_sample_rate=int(cfg.get("output_sample_rate", DEFAULT_RENDER_OUTPUT_SAMPLE_RATE)),
        preview_format=cfg.get("preview_format", "wav"),
        dubbing_workers=cfg.get("dubbing_workers"),
        dubbing_quality_check=cfg.get("dubbing_quality_check", "standard"),
        dub_repair_enabled=bool(cfg.get("dub_repair_enabled", False)),
        dub_repair_backends=cfg.get("dub_repair_backends") or cfg.get("dub_repair_backend") or None,
        dub_repair_max_items=int(cfg.get("dub_repair_max_items", 12)),
        dub_repair_attempts_per_item=int(cfg.get("dub_repair_attempts_per_item", 3)),
        dub_repair_include_risk=bool(cfg.get("dub_repair_include_risk", False)),
        api_base_url=cfg.get("deepseek_base_url"),
        api_model=cfg.get("deepseek_model"),
        condense_mode=cfg.get("condense_mode", "off"),
        glossary_path=cfg.get("translation_glossary"),
        registry_path=cfg.get("existing_registry"),
        subtitle_mode=delivery_cfg.get("subtitle_mode", "none"),
        subtitle_source=delivery_cfg.get("subtitle_render_source", "ocr"),
        subtitle_style=SubtitleStyle(
            font_family=delivery_cfg.get("subtitle_font") or "Noto Sans",
            font_size=int(delivery_cfg.get("subtitle_font_size", 0)),
            primary_color=delivery_cfg.get("subtitle_color", "#FFFFFF"),
            outline_color=delivery_cfg.get("subtitle_outline_color", "#000000"),
            outline_width=float(delivery_cfg.get("subtitle_outline_width", 2.0)),
            shadow_depth=1.0,
            bold=bool(delivery_cfg.get("subtitle_bold", False)),
            position=delivery_cfg.get("subtitle_position", "bottom"),
            margin_v=int(delivery_cfg.get("subtitle_margin_v", 0)),
            margin_h=20,
            alignment=8 if delivery_cfg.get("subtitle_position", "bottom") == "top" else 2,
        ),
        bilingual_chinese_position=delivery_cfg.get("bilingual_chinese_position", "bottom"),
        bilingual_english_position=delivery_cfg.get("bilingual_english_position", "top"),
        bilingual_export_strategy=delivery_cfg.get(
            "bilingual_export_strategy",
            "auto_standard_bilingual",
        ),
        transcription_correction=cfg.get(
            "transcription_correction",
            {
                "enabled": True,
                "preset": "standard",
                "ocr_only_policy": "report_only",
                "llm_arbitration": "off",
            },
        ),
    )


def _planned_task_nodes(config_dict: Dict[str, Any]) -> list[str]:
    config_dict = normalize_task_config(config_dict)
    template_id = config_dict.get("template", "asr-dub-basic")
    run_from = config_dict.get("run_from_stage", "stage1")
    run_to = config_dict.get("run_to_stage", "task-g")
    plan = resolve_template_plan(template_id)
    start_hint = NODE_REGISTRY[run_from].sequence_hint
    end_hint = NODE_REGISTRY[run_to].sequence_hint
    return [
        node_name
        for node_name in plan.node_order
        if start_hint <= NODE_REGISTRY[node_name].sequence_hint <= end_hint
    ]


def _run_pipeline_in_thread(task_id: str) -> None:
    """Execute the pipeline in a background thread."""
    from ..orchestration.runner import run_pipeline

    with Session(engine) as session:
        task = session.get(Task, task_id)
        if not task:
            return
        task.status = "running"
        task.started_at = datetime.now()
        task.updated_at = datetime.now()
        session.add(TaskLog(task_id=task_id, action="started"))
        session.commit()

    cancel_event = threading.Event()
    with _cancel_events_lock:
        _cancel_events[task_id] = cancel_event

    try:
        with Session(engine) as session:
            task = session.get(Task, task_id)
            if not task:
                return
            pipeline_req = _build_pipeline_request(task)

        result = run_pipeline(pipeline_req.normalized(), should_cancel=cancel_event.is_set)

        pipeline_status = result.report.get("status", "failed")

        with Session(engine) as session:
            task = session.get(Task, task_id)
            if not task:
                return
            task.status = pipeline_status
            if pipeline_status in ("succeeded", "partial_success"):
                task.overall_progress = 100.0
            now = datetime.now()
            task.finished_at = now
            if task.started_at is not None:
                task.elapsed_sec = round((now - task.started_at).total_seconds(), 3)
            task.manifest_path = str(result.manifest_path) if result.manifest_path else None
            task.updated_at = now
            session.add(
                TaskLog(
                    task_id=task_id,
                    action="completed" if task.status in ("succeeded", "partial_success") else "failed",
                    detail=json.dumps({"status": pipeline_status}),
                )
            )
            session.commit()

        # Sync stages from manifest
        _sync_stages_from_manifest(task_id)

    except Exception as exc:
        cancelled = cancel_event.is_set()
        if cancelled:
            logger.info("Pipeline cancelled by user for task %s", task_id)
        else:
            logger.exception("Pipeline execution failed for task %s", task_id)
        with Session(engine) as session:
            task = session.get(Task, task_id)
            if task:
                task.status = "failed"
                task.error_message = "Stopped by user" if cancelled else str(exc)
                now = datetime.now()
                task.finished_at = now
                if task.started_at is not None:
                    task.elapsed_sec = round((now - task.started_at).total_seconds(), 3)
                task.updated_at = now
                session.add(
                    TaskLog(
                        task_id=task_id,
                        action="stopped" if cancelled else "failed",
                        detail=str(exc)[:500],
                    )
                )
                session.commit()
    finally:
        with _cancel_events_lock:
            _cancel_events.pop(task_id, None)


def _run_delivery_step(task_id: str, pipeline_req: "PipelineRequest") -> None:
    """Run Task G (video delivery/mux) after the main pipeline."""
    from ..delivery.runner import export_video
    from ..types import ExportVideoRequest

    output_root = Path(pipeline_req.output_root)
    delivery_dir = output_root / "task-g"
    task_e_dir = output_root / "task-e" / "voice"  # task-e bundle dir

    request = ExportVideoRequest(
        input_video_path=pipeline_req.input_path,
        pipeline_root=output_root,
        task_e_dir=task_e_dir,
        output_dir=delivery_dir,
        target_lang=pipeline_req.target_lang,
        export_preview=True,
        export_dub=True,
    )
    try:
        result = export_video(request)
        manifest_path = result.artifacts.manifest_path
        elapsed = result.manifest.get("timing", {}).get("elapsed_sec")
        with Session(engine) as session:
            task = session.get(Task, task_id)
            if task:
                stmt = select(TaskStage).where(
                    TaskStage.task_id == task_id,
                    TaskStage.stage_name == "task-g",
                )
                stage_row = session.exec(stmt).first()
                if not stage_row:
                    stage_row = TaskStage(task_id=task_id, stage_name="task-g")
                stage_row.status = "succeeded"
                stage_row.progress_percent = 100.0
                stage_row.current_step = "completed"
                stage_row.elapsed_sec = elapsed
                stage_row.manifest_path = str(manifest_path)
                session.add(stage_row)
                session.commit()
    except Exception as exc:
        logger.exception("Delivery step (task-g) failed for task %s", task_id)
        with Session(engine) as session:
            task = session.get(Task, task_id)
            if task:
                stmt = select(TaskStage).where(
                    TaskStage.task_id == task_id,
                    TaskStage.stage_name == "task-g",
                )
                stage_row = session.exec(stmt).first()
                if not stage_row:
                    stage_row = TaskStage(task_id=task_id, stage_name="task-g")
                stage_row.status = "failed"
                stage_row.error_message = str(exc)
                session.add(stage_row)
                session.commit()


def _sync_stages_from_manifest(task_id: str) -> None:
    """Sync stage info from pipeline-manifest.json into DB."""
    with Session(engine) as session:
        task = session.get(Task, task_id)
        if not task:
            return
        manifest_path = Path(task.output_root) / "pipeline-manifest.json"
        if not manifest_path.exists():
            return
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            return

        for stage_data in payload.get("nodes", payload.get("stages", [])):
            if not isinstance(stage_data, dict):
                continue
            stage_name = stage_data.get("node_name") or stage_data.get("stage_name", "")
            if not stage_name:
                continue
            stmt = select(TaskStage).where(
                TaskStage.task_id == task_id,
                TaskStage.stage_name == stage_name,
            )
            stage_row = session.exec(stmt).first()
            if not stage_row:
                stage_row = TaskStage(task_id=task_id, stage_name=stage_name)
            stage_row.status = stage_data.get("status", "pending")
            stage_row.cache_hit = stage_data.get("cache_hit", False)
            stage_row.elapsed_sec = stage_data.get("elapsed_sec")
            stage_row.manifest_path = stage_data.get("manifest_path")
            stage_row.error_message = stage_data.get("error_message")
            session.add(stage_row)
        session.commit()


def _sync_status_to_db(task_id: str, status_path: Path) -> None:
    """Background thread: periodically sync pipeline-status.json to DB."""
    while True:
        time.sleep(3)
        if not status_path.exists():
            with Session(engine) as session:
                task = session.get(Task, task_id)
                if task and task.status not in ("running", "pending"):
                    break
            continue
        try:
            payload = json.loads(status_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        with Session(engine) as session:
            task = session.get(Task, task_id)
            if not task:
                break
            task.overall_progress = payload.get("overall_progress_percent", task.overall_progress)
            task.current_stage = payload.get("current_stage", task.current_stage)
            payload_status = payload.get("status")
            if payload_status in ("succeeded", "partial_success", "failed"):
                task.status = payload_status
                if task.finished_at is None:
                    task.finished_at = datetime.now()
                if task.elapsed_sec is None and task.started_at is not None:
                    task.elapsed_sec = round(
                        (task.finished_at - task.started_at).total_seconds(), 3
                    )
            task.updated_at = datetime.now()

            for stage_data in payload.get("nodes", payload.get("stages", [])):
                if not isinstance(stage_data, dict):
                    continue
                sn = stage_data.get("node_name") or stage_data.get("stage_name", "")
                if not sn:
                    continue
                stmt = select(TaskStage).where(
                    TaskStage.task_id == task_id,
                    TaskStage.stage_name == sn,
                )
                row = session.exec(stmt).first()
                if not row:
                    row = TaskStage(task_id=task_id, stage_name=sn)
                row.status = stage_data.get("status", row.status)
                row.progress_percent = stage_data.get("progress_percent", row.progress_percent)
                row.current_step = stage_data.get("current_step", row.current_step)
                session.add(row)
            session.commit()

        if payload.get("status") in ("succeeded", "partial_success", "failed"):
            _sync_stages_from_manifest(task_id)
            break


def mark_interrupted_tasks() -> int:
    """Reconcile orphaned pipeline tasks left ``running``/``pending`` by a previous
    process. No pipeline thread survives a restart, so any such row is stale and is
    flipped to ``interrupted``. Mirrors atomic_tools.job_manager.mark_interrupted_jobs.
    """
    count = 0
    now = datetime.now()
    with Session(engine) as session:
        tasks = list(
            session.exec(select(Task).where(Task.status.in_(["pending", "running"]))).all()
        )
        for task in tasks:
            task.status = "interrupted"
            task.error_message = "Interrupted by service restart"
            task.finished_at = now
            task.updated_at = now
            if task.started_at is not None:
                task.elapsed_sec = round((now - task.started_at).total_seconds(), 3)
            session.add(task)
            session.add(TaskLog(task_id=task.id, action="interrupted"))
            count += 1
        session.commit()
    return count


class TaskManager:
    """Manages task lifecycle: creation, execution, progress tracking."""

    def create_task(self, session: Session, req: CreateTaskRequest) -> Task:
        task_id = _now_task_id()
        # Use provided output_root if given (e.g. rerun sharing parent's output), else default
        if getattr(req, "output_root", None):
            output_root = str(req.output_root)
        else:
            output_root = str(CACHE_ROOT / "output-pipeline" / task_id)

        config_dict = normalize_task_storage(req.config.model_dump() if req.config else {})

        task = Task(
            id=task_id,
            name=req.name,
            status="pending",
            input_path=req.input_path,
            output_root=output_root,
            source_lang=req.source_lang,
            target_lang=req.target_lang,
            config=config_dict,
        )
        session.add(task)
        session.add(TaskLog(task_id=task_id, action="created"))

        for node_name in _planned_task_nodes(config_dict):
            session.add(TaskStage(task_id=task_id, stage_name=node_name))

        session.commit()
        session.refresh(task)

        # Launch pipeline in background thread
        pipeline_thread = threading.Thread(
            target=_run_pipeline_in_thread, args=(task_id,), daemon=True
        )
        pipeline_thread.start()

        # Launch status sync thread
        status_path = Path(output_root) / "pipeline-status.json"
        sync_thread = threading.Thread(
            target=_sync_status_to_db, args=(task_id, status_path), daemon=True
        )
        sync_thread.start()

        return task

    def stop_task(self, session: Session, task_id: str) -> bool:
        task = session.get(Task, task_id)
        if not task or task.status not in ("pending", "running"):
            return False
        # Signal the running pipeline thread to cancel; this SIGTERMs the active
        # stage subprocess via run_pipeline's should_cancel hook.
        with _cancel_events_lock:
            cancel_event = _cancel_events.get(task_id)
        if cancel_event is not None:
            cancel_event.set()
        task.status = "failed"
        task.error_message = "Stopped by user"
        now = datetime.now()
        task.finished_at = now
        if task.started_at is not None:
            task.elapsed_sec = round((now - task.started_at).total_seconds(), 3)
        task.updated_at = now
        session.add(TaskLog(task_id=task_id, action="stopped"))
        session.commit()
        return True

    async def stream_progress(self, task_id: str) -> AsyncGenerator[str, None]:
        """Yield SSE-formatted strings from pipeline-status.json."""
        with Session(engine) as session:
            task = session.get(Task, task_id)
            if not task:
                yield _sse_event("error", {"message": "Task not found"})
                return
            status_path = Path(task.output_root) / "pipeline-status.json"

        last_payload: Optional[Dict[str, Any]] = None
        max_wait = 300  # seconds
        elapsed = 0
        interval = 1.5

        while elapsed < max_wait:
            await asyncio.sleep(interval)
            elapsed += interval

            if status_path.exists():
                try:
                    payload = json.loads(status_path.read_text(encoding="utf-8"))
                except Exception:
                    continue

                if payload != last_payload:
                    last_payload = payload
                    stage = payload.get("current_stage", "")
                    pct = payload.get("overall_progress_percent", 0)
                    status = payload.get("status", "running")
                    yield _sse_event(
                        "progress",
                        {
                            "stage": stage,
                            "overall_percent": pct,
                            "status": status,
                            "stages": payload.get("stages", []),
                        },
                    )
                    if status in ("succeeded", "partial_success", "failed"):
                        yield _sse_event("done", {"status": status, "overall_percent": pct})
                        return
            else:
                # Check DB for final status
                with Session(engine) as session:
                    task = session.get(Task, task_id)
                    if task and task.status in ("succeeded", "partial_success", "failed"):
                        yield _sse_event(
                            "done",
                            {"status": task.status, "overall_percent": task.overall_progress},
                        )
                        return

        yield _sse_event("timeout", {"message": "Progress stream timed out"})


def _sse_event(event: str, data: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# Singleton instance
task_manager = TaskManager()
