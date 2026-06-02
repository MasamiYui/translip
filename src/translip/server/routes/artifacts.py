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

    if not str(full_path).startswith(str(output_root)):
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
