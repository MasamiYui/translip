from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlmodel import Session

from ..database import get_session
from ..models import Task

router = APIRouter(prefix="/api/tasks", tags=["artifacts"])


@router.get("/{task_id}/input-file")
def get_task_input_file(
    task_id: str,
    session: Session = Depends(get_session),
):
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


@router.get("/{task_id}/artifacts/{artifact_path:path}")
def get_artifact(
    task_id: str,
    artifact_path: str,
    preview: bool = Query(False),
    session: Session = Depends(get_session),
):
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
