from __future__ import annotations

import asyncio
from typing import Annotated, AsyncGenerator

from fastapi import APIRouter, Depends, Path
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from ..database import get_session
from ..task_manager import task_manager

router = APIRouter(prefix="/api/tasks", tags=["progress"])


@router.get("/{task_id}/progress", summary="任务进度流")
async def stream_progress(
    task_id: Annotated[str, Path(description="任务 ID")],
    session: Session = Depends(get_session),
):
    """以 SSE（text/event-stream）方式实时推送指定任务的流水线进度，持续返回各阶段进度事件直至任务结束。"""

    async def event_generator() -> AsyncGenerator[str, None]:
        async for chunk in task_manager.stream_progress(task_id):
            yield chunk

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
