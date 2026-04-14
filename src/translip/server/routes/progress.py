from __future__ import annotations

import asyncio
from typing import AsyncGenerator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from ..database import get_session
from ..task_manager import task_manager

router = APIRouter(prefix="/api/tasks", tags=["progress"])


@router.get("/{task_id}/progress")
async def stream_progress(task_id: str, session: Session = Depends(get_session)):
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
