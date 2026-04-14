from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .database import init_db
from .routes.artifacts import router as artifacts_router
from .routes.config import router as config_router
from .routes.progress import router as progress_router
from .routes.system import router as system_router
from .routes.tasks import router as tasks_router

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Video Voice Separate — Pipeline Manager",
    version="0.1.0",
    description="Management API for the video dubbing pipeline.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_event():
    init_db()
    logger.info("Database initialized")


app.include_router(tasks_router)
app.include_router(progress_router)
app.include_router(config_router)
app.include_router(system_router)
app.include_router(artifacts_router)

# Serve frontend static files if built
_FRONTEND_DIST = Path(__file__).parent.parent.parent.parent.parent / "frontend" / "dist"
if _FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=_FRONTEND_DIST, html=True), name="frontend")


def run_server(host: str = "127.0.0.1", port: int = 8765) -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    uvicorn.run("video_voice_separate.server.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    run_server()
