from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .database import init_db
from .atomic_tools.job_manager import job_manager
from .routes.artifacts import router as artifacts_router
from .routes.atomic_tools import router as atomic_tools_router
from .routes.config import router as config_router
from .routes.delivery import router as delivery_router
from .routes.dubbing_editor import router as dubbing_editor_router
from .routes.progress import router as progress_router
from .routes.speaker_review import (
    global_personas_router,
    router as speaker_review_router,
)
from .routes.system import router as system_router
from .routes.tasks import router as tasks_router

logger = logging.getLogger(__name__)


def _find_project_root(start: Path) -> Path:
    for candidate in [start.parent, *start.parents]:
        if (candidate / "pyproject.toml").exists():
            return candidate
    return start.parents[3]


app = FastAPI(
    title="Translip — Pipeline Manager",
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
    job_manager.mark_interrupted_jobs()
    logger.info("Database initialized")


app.include_router(tasks_router)
app.include_router(progress_router)
app.include_router(config_router)
app.include_router(delivery_router)
app.include_router(dubbing_editor_router)
app.include_router(speaker_review_router)
app.include_router(global_personas_router)
app.include_router(system_router)
app.include_router(artifacts_router)
app.include_router(atomic_tools_router)

# Serve frontend static files if built
_FRONTEND_DIST = _find_project_root(Path(__file__).resolve()) / "frontend" / "dist"
if _FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=_FRONTEND_DIST / "assets"), name="frontend-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_frontend(full_path: str):
        candidate = (_FRONTEND_DIST / full_path).resolve()
        try:
            candidate.relative_to(_FRONTEND_DIST)
        except ValueError:
            return FileResponse(_FRONTEND_DIST / "index.html")
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_FRONTEND_DIST / "index.html")


def run_server(host: str = "127.0.0.1", port: int = 8765) -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    uvicorn.run("translip.server.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    run_server()
