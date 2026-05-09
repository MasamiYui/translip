from __future__ import annotations

import asyncio
from dataclasses import asdict

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

import translip.server.atomic_tools as atomic_tools  # noqa: F401

from ..atomic_tools.job_manager import job_manager
from ..atomic_tools.registry import TOOL_REGISTRY, get_all_tools
from ..atomic_tools.schemas import (
    ArtifactInfo,
    AtomicJobDetail,
    AtomicJobListResponse,
    AtomicJobRead,
    FileUploadResponse,
    JobResponse,
    ToolInfo,
)

router = APIRouter(prefix="/api/atomic-tools", tags=["atomic-tools"])


def _require_job_for_tool(tool_id: str, job_id: str) -> JobResponse:
    if tool_id not in TOOL_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Unknown tool: {tool_id}")
    try:
        job = job_manager.get_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc
    if job.tool_id != tool_id:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/tools", response_model=list[ToolInfo])
def list_tools() -> list[ToolInfo]:
    return [ToolInfo(**asdict(spec)) for spec in get_all_tools()]


@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(file: UploadFile = File(...)) -> FileUploadResponse:
    return await job_manager.save_upload(file)


@router.get("/jobs", response_model=AtomicJobListResponse)
def list_jobs(
    status: str | None = Query(None),
    tool_id: str | None = Query(None),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
) -> AtomicJobListResponse:
    return job_manager.list_jobs(
        status=status,
        tool_id=tool_id,
        search=search,
        page=page,
        size=size,
    )


@router.get("/jobs/recent", response_model=list[AtomicJobRead])
def list_recent_jobs(limit: int = Query(5, ge=1, le=20)) -> list[AtomicJobRead]:
    return job_manager.list_recent_jobs(limit=limit)


@router.get("/jobs/{job_id}", response_model=AtomicJobDetail)
def get_job_detail(job_id: str) -> AtomicJobDetail:
    try:
        return job_manager.get_job_detail(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc


@router.delete("/jobs/{job_id}")
def delete_job(
    job_id: str,
    delete_artifacts: bool = Query(True),
) -> dict[str, bool]:
    try:
        job_manager.delete_job(job_id, delete_artifacts=delete_artifacts)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc
    return {"ok": True}


@router.post("/jobs/{job_id}/rerun", response_model=JobResponse)
def rerun_job(job_id: str) -> JobResponse:
    try:
        return job_manager.rerun_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/jobs/{job_id}/stop")
def stop_job(job_id: str) -> dict[str, bool]:
    try:
        ok = job_manager.cancel_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc
    if not ok:
        raise HTTPException(status_code=400, detail="Job cannot be stopped")
    return {"ok": True}


@router.post("/{tool_id}/run", response_model=JobResponse)
async def run_tool(tool_id: str, params: dict) -> JobResponse:
    if tool_id not in TOOL_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Unknown tool: {tool_id}")
    try:
        job = job_manager.create_job(tool_id, params)
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    asyncio.get_running_loop().create_task(job_manager.execute_job(job.job_id))
    return job


@router.get("/{tool_id}/jobs/{job_id}", response_model=JobResponse)
def get_job_status(tool_id: str, job_id: str) -> JobResponse:
    return _require_job_for_tool(tool_id, job_id)


@router.get("/{tool_id}/jobs/{job_id}/result")
def get_job_result(tool_id: str, job_id: str) -> dict:
    job = _require_job_for_tool(tool_id, job_id)
    if job.status != "completed":
        raise HTTPException(status_code=409, detail="Job is not completed yet")
    return job_manager.get_job_result(job_id) or {}


@router.get("/{tool_id}/jobs/{job_id}/artifacts", response_model=list[ArtifactInfo])
def list_job_artifacts(tool_id: str, job_id: str) -> list[ArtifactInfo]:
    _require_job_for_tool(tool_id, job_id)
    return job_manager.list_artifacts(job_id)


@router.get("/{tool_id}/jobs/{job_id}/artifacts/{artifact_path:path}")
def download_artifact(tool_id: str, job_id: str, artifact_path: str):
    _require_job_for_tool(tool_id, job_id)
    path = job_manager.get_artifact_path(job_id, artifact_path)
    if path is None or not path.exists():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(path, filename=path.name)
