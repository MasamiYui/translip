from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from ...orchestration.graph_export import build_workflow_graph_payload
from ..database import get_session
from ..models import Task, TaskLog, TaskStage
from ..schemas import (
    CreateTaskRequest,
    RerunTaskRequest,
    TaskGraphRead,
    TaskListResponse,
    TaskRead,
    TaskStageRead,
)
from ..task_config import (
    normalize_task_config,
    normalize_task_delivery_config,
    normalize_task_storage,
)
from ..task_read_model import (
    build_asset_summary,
    build_export_readiness,
    build_last_export_summary,
    infer_output_intent,
    infer_quality_preset,
)
from ..task_manager import task_manager

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _task_to_read(task: Task, stages: list[TaskStage]) -> TaskRead:
    pipeline_config = normalize_task_config(task.config)
    delivery_config = normalize_task_delivery_config(task.config)
    output_intent = infer_output_intent(task.config)
    quality_preset = infer_quality_preset(task.config)
    asset_summary = build_asset_summary(task)
    export_readiness = build_export_readiness(
        task,
        output_intent=output_intent,
        asset_summary=asset_summary,
    )
    last_export_summary = build_last_export_summary(
        task,
        asset_summary=asset_summary,
    )
    return TaskRead(
        id=task.id,
        name=task.name,
        status=task.status,
        input_path=task.input_path,
        output_root=task.output_root,
        source_lang=task.source_lang,
        target_lang=task.target_lang,
        output_intent=output_intent,
        quality_preset=quality_preset,
        config=pipeline_config,
        delivery_config=delivery_config,
        asset_summary=asset_summary,
        export_readiness=export_readiness,
        last_export_summary=last_export_summary,
        overall_progress=task.overall_progress,
        current_stage=task.current_stage,
        created_at=task.created_at,
        updated_at=task.updated_at,
        started_at=task.started_at,
        finished_at=task.finished_at,
        elapsed_sec=task.elapsed_sec,
        error_message=task.error_message,
        manifest_path=task.manifest_path,
        parent_task_id=task.parent_task_id,
        stages=[
            TaskStageRead(
                stage_name=s.stage_name,
                status=s.status,
                progress_percent=s.progress_percent,
                current_step=s.current_step,
                cache_hit=s.cache_hit,
                started_at=s.started_at,
                finished_at=s.finished_at,
                elapsed_sec=s.elapsed_sec,
                manifest_path=s.manifest_path,
                error_message=s.error_message,
            )
            for s in sorted(stages, key=lambda x: x.id or 0)
        ],
    )


def _task_graph_payload_from_db(task: Task, stages: list[TaskStage]) -> dict:
    config = normalize_task_config(task.config)
    template_id = config.get("template", "asr-dub-basic")
    return {
        "template_id": template_id,
        "status": task.status,
        "nodes": [
            {
                "node_name": stage.stage_name,
                "stage_name": stage.stage_name,
                "status": stage.status,
                "progress_percent": stage.progress_percent,
                "manifest_path": stage.manifest_path,
                "error_message": stage.error_message,
            }
            for stage in stages
        ],
    }


@router.post("", response_model=TaskRead)
def create_task(req: CreateTaskRequest, session: Session = Depends(get_session)):
    task = task_manager.create_task(session, req)
    stages = list(session.exec(select(TaskStage).where(TaskStage.task_id == task.id)).all())
    return _task_to_read(task, stages)


@router.get("", response_model=TaskListResponse)
def list_tasks(
    status: Optional[str] = Query(None),
    target_lang: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    session: Session = Depends(get_session),
):
    stmt = select(Task)
    if status and status != "all":
        stmt = stmt.where(Task.status == status)
    if target_lang:
        stmt = stmt.where(Task.target_lang == target_lang)
    if search:
        stmt = stmt.where(Task.name.contains(search))
    stmt = stmt.order_by(Task.created_at.desc())

    all_tasks = list(session.exec(stmt).all())
    total = len(all_tasks)
    offset = (page - 1) * size
    tasks_page = all_tasks[offset : offset + size]

    items = []
    for task in tasks_page:
        stages = list(session.exec(select(TaskStage).where(TaskStage.task_id == task.id)).all())
        items.append(_task_to_read(task, stages))

    return TaskListResponse(items=items, total=total, page=page, size=size)


@router.get("/{task_id}", response_model=TaskRead)
def get_task(task_id: str, session: Session = Depends(get_session)):
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    stages = list(session.exec(select(TaskStage).where(TaskStage.task_id == task_id)).all())
    return _task_to_read(task, stages)


@router.delete("/{task_id}")
def delete_task(
    task_id: str,
    delete_artifacts: bool = Query(False),
    session: Session = Depends(get_session),
):
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status == "running":
        raise HTTPException(status_code=400, detail="Cannot delete a running task")

    if delete_artifacts:
        output_root = Path(task.output_root)
        if output_root.exists():
            shutil.rmtree(output_root, ignore_errors=True)

    # Delete related records
    session.exec(select(TaskStage).where(TaskStage.task_id == task_id))
    for stage in session.exec(select(TaskStage).where(TaskStage.task_id == task_id)).all():
        session.delete(stage)
    for log in session.exec(select(TaskLog).where(TaskLog.task_id == task_id)).all():
        session.delete(log)
    session.delete(task)
    session.commit()
    return {"ok": True}


@router.post("/{task_id}/rerun", response_model=TaskRead)
def rerun_task(
    task_id: str,
    req: RerunTaskRequest,
    session: Session = Depends(get_session),
):
    original = session.get(Task, task_id)
    if not original:
        raise HTTPException(status_code=404, detail="Task not found")

    from ..schemas import CreateTaskRequest, TaskConfigInput

    normalized = normalize_task_storage(original.config)
    pipeline_config = dict(normalized["pipeline"])
    pipeline_config["run_from_stage"] = req.from_stage
    merged_config = {
        **pipeline_config,
        **dict(normalized["delivery"]),
    }

    new_req = CreateTaskRequest(
        name=original.name + " (重跑)",
        input_path=original.input_path,
        source_lang=original.source_lang,
        target_lang=original.target_lang,
        config=TaskConfigInput(**merged_config),
        output_root=original.output_root,
    )
    new_task = task_manager.create_task(session, new_req)
    new_task.parent_task_id = task_id
    session.add(new_task)
    session.add(TaskLog(task_id=new_task.id, action="rerun", detail=json.dumps({"from": task_id})))
    session.commit()
    session.refresh(new_task)

    stages = list(session.exec(select(TaskStage).where(TaskStage.task_id == new_task.id)).all())
    return _task_to_read(new_task, stages)


@router.post("/{task_id}/stop")
def stop_task(task_id: str, session: Session = Depends(get_session)):
    ok = task_manager.stop_task(session, task_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Task cannot be stopped")
    return {"ok": True}


@router.get("/{task_id}/status")
def get_task_status(task_id: str, session: Session = Depends(get_session)):
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    status_path = Path(task.output_root) / "pipeline-status.json"
    if status_path.exists():
        try:
            return json.loads(status_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    return {
        "status": task.status,
        "overall_progress_percent": task.overall_progress,
        "current_stage": task.current_stage,
    }


@router.get("/{task_id}/manifest")
def get_task_manifest(task_id: str, session: Session = Depends(get_session)):
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    manifest_path = Path(task.output_root) / "pipeline-manifest.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="Manifest not found")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


@router.get("/{task_id}/graph", response_model=TaskGraphRead)
def get_task_graph(task_id: str, session: Session = Depends(get_session)):
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    stages = list(session.exec(select(TaskStage).where(TaskStage.task_id == task_id)).all())
    manifest_path = Path(task.output_root) / "workflow-manifest.json"
    if not manifest_path.exists():
        manifest_path = Path(task.output_root) / "pipeline-manifest.json"
    if manifest_path.exists():
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        if "template_id" not in payload:
            payload = _task_graph_payload_from_db(task, stages)
    else:
        payload = _task_graph_payload_from_db(task, stages)
    return build_workflow_graph_payload(payload)


@router.get("/{task_id}/stages/{stage_name}/manifest")
def get_stage_manifest(task_id: str, stage_name: str, session: Session = Depends(get_session)):
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    output_root = Path(task.output_root)
    input_stem = Path(task.input_path).stem

    stage_map = {
        "stage1": f"stage1/{input_stem}/manifest.json",
        "ocr-detect": "ocr-detect/ocr-detect-manifest.json",
        "task-a": "task-a/voice/task-a-manifest.json",
        "task-b": "task-b/voice/task-b-manifest.json",
        "task-c": "task-c/voice/task-c-manifest.json",
        "ocr-translate": "ocr-translate/ocr-translate-manifest.json",
        "task-d": "task-d/task-d-stage-manifest.json",
        "task-e": "task-e/voice/task-e-manifest.json",
        "subtitle-erase": "subtitle-erase/subtitle-erase-manifest.json",
        "task-g": "task-g/delivery-manifest.json",
    }
    filename = stage_map.get(stage_name)
    if not filename:
        raise HTTPException(status_code=400, detail="Unknown stage")

    path = output_root / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Stage manifest not found")
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/{task_id}/artifacts")
def list_artifacts(task_id: str, session: Session = Depends(get_session)):
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    output_root = Path(task.output_root)
    if not output_root.exists():
        return {"artifacts": []}

    artifacts = []
    for p in sorted(output_root.rglob("*")):
        if p.is_file():
            rel = str(p.relative_to(output_root))
            artifacts.append(
                {
                    "path": rel,
                    "size_bytes": p.stat().st_size,
                    "suffix": p.suffix,
                }
            )
    return {"artifacts": artifacts}


@router.get("/{task_id}/delivery")
def get_delivery(task_id: str, session: Session = Depends(get_session)):
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    delivery_dir = Path(task.output_root) / "delivery"
    if not delivery_dir.exists():
        return {"files": []}

    files = []
    for p in sorted(delivery_dir.rglob("*")):
        if p.is_file():
            files.append(
                {
                    "name": p.name,
                    "path": str(p.relative_to(Path(task.output_root))),
                    "size_bytes": p.stat().st_size,
                    "suffix": p.suffix,
                }
            )
    return {"files": files}
