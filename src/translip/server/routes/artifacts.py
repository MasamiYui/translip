from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path as PathParam, Query
from fastapi.responses import FileResponse
from sqlmodel import Session

from ..database import get_session
from ..models import Task

router = APIRouter(prefix="/api/tasks", tags=["artifacts"])


@router.get("/{task_id}/input-file", summary="获取任务输入文件")
def get_task_input_file(
    task_id: Annotated[str, PathParam(description="任务 ID")],
    session: Session = Depends(get_session),
):
    """下载指定任务的原始输入文件（即创建任务时上传的视频/音频源文件），按文件扩展名推断媒体类型返回。"""
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    input_path = Path(task.input_path).resolve()
    if not input_path.exists() or not input_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    media_type, _ = mimetypes.guess_type(str(input_path))
    return FileResponse(
        path=input_path,
        filename=input_path.name,
        media_type=media_type or "application/octet-stream",
    )


@router.get("/{task_id}/artifacts/{artifact_path:path}", summary="获取任务产物文件")
def get_artifact(
    task_id: Annotated[str, PathParam(description="任务 ID")],
    artifact_path: Annotated[str, PathParam(description="产物相对路径（相对于任务输出根目录）")],
    preview: bool = Query(False, description="是否以预览方式返回：True 时内联展示（inline），False 时作为附件下载（attachment）"),
    session: Session = Depends(get_session),
):
    """下载指定任务的某个流水线产物（artifact）文件。artifact_path 为相对于任务输出根目录的相对路径；会做路径穿越校验，越界访问返回 403。"""
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Prevent path traversal
    output_root = Path(task.output_root).resolve()
    full_path = (output_root / artifact_path).resolve()

    if not full_path.is_relative_to(output_root):
        raise HTTPException(status_code=403, detail="Access denied")

    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    media_type, _ = mimetypes.guess_type(str(full_path))
    return FileResponse(
        path=full_path,
        filename=full_path.name,
        media_type=media_type or "application/octet-stream",
        content_disposition_type="inline" if preview else "attachment",
    )


@router.get("/{task_id}/logs/{node}", summary="获取节点阶段日志")
def get_node_log(
    task_id: Annotated[str, PathParam(description="任务 ID")],
    node: Annotated[str, PathParam(description="节点名，如 separation / transcription / ocr-detect")],
    max_bytes: int = Query(65536, gt=0, le=2_000_000, description="返回日志末尾最多字节数"),
    session: Session = Depends(get_session),
):
    """读取某个流水线节点的运行日志（`<output_root>/logs/<node>.log`）末尾片段，供 UI 内联查看。"""
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    logs_dir = (Path(task.output_root) / "logs").resolve()
    log_path = (logs_dir / f"{node}.log").resolve()
    if not log_path.is_relative_to(logs_dir):
        raise HTTPException(status_code=403, detail="Access denied")
    if not log_path.exists() or not log_path.is_file():
        return {"node": node, "exists": False, "truncated": False, "content": ""}

    data = log_path.read_bytes()
    truncated = len(data) > max_bytes
    tail = data[-max_bytes:] if truncated else data
    return {
        "node": node,
        "exists": True,
        "truncated": truncated,
        "content": tail.decode("utf-8", errors="replace"),
    }
