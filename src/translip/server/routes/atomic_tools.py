from __future__ import annotations

import asyncio
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Path, Query, UploadFile
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


@router.get("/tools", response_model=list[ToolInfo], summary="原子工具列表")
def list_tools() -> list[ToolInfo]:
    """返回所有已注册原子工具的元信息（工具 ID、名称、参数定义等）。"""
    return [ToolInfo(**asdict(spec)) for spec in get_all_tools()]


@router.post("/upload", response_model=FileUploadResponse, summary="上传文件")
async def upload_file(file: UploadFile = File(...)) -> FileUploadResponse:
    """上传一个文件供原子工具作业使用，保存到原子工具存储目录并返回文件标识与路径。"""
    return await job_manager.save_upload(file)


@router.get("/jobs", response_model=AtomicJobListResponse, summary="作业列表")
def list_jobs(
    status: str | None = Query(None, description="按作业状态过滤，留空为不过滤"),
    tool_id: str | None = Query(None, description="按原子工具 ID 过滤，留空为不过滤"),
    search: str | None = Query(None, description="按关键字搜索作业，留空为不过滤"),
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    size: int = Query(20, ge=1, le=100, description="每页条数，取值 1~100"),
) -> AtomicJobListResponse:
    """分页查询原子工具作业列表，支持按状态、工具 ID 和关键字过滤。"""
    return job_manager.list_jobs(
        status=status,
        tool_id=tool_id,
        search=search,
        page=page,
        size=size,
    )


@router.get("/jobs/recent", response_model=list[AtomicJobRead], summary="最近作业")
def list_recent_jobs(
    limit: int = Query(5, ge=1, le=20, description="返回的最近作业数量，取值 1~20"),
) -> list[AtomicJobRead]:
    """返回最近创建的若干个原子工具作业，按时间倒序排列。"""
    return job_manager.list_recent_jobs(limit=limit)


@router.get("/jobs/{job_id}", response_model=AtomicJobDetail, summary="作业详情")
def get_job_detail(job_id: Annotated[str, Path(description="作业 ID")]) -> AtomicJobDetail:
    """根据作业 ID 返回单个原子工具作业的详细信息。"""
    try:
        return job_manager.get_job_detail(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc


@router.delete("/jobs/{job_id}", summary="删除作业")
def delete_job(
    job_id: Annotated[str, Path(description="作业 ID")],
    delete_artifacts: bool = Query(True, description="是否同时删除该作业生成的产物文件，默认删除"),
) -> dict[str, bool]:
    """删除指定原子工具作业；默认连同其产物文件一并删除。"""
    try:
        job_manager.delete_job(job_id, delete_artifacts=delete_artifacts)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc
    return {"ok": True}


@router.post("/jobs/{job_id}/rerun", response_model=JobResponse, summary="重跑作业")
def rerun_job(job_id: Annotated[str, Path(description="作业 ID")]) -> JobResponse:
    """以原作业的参数重新创建并启动一个原子工具作业，返回新作业信息。"""
    try:
        return job_manager.rerun_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/jobs/{job_id}/stop", summary="停止作业")
def stop_job(job_id: Annotated[str, Path(description="作业 ID")]) -> dict[str, bool]:
    """请求停止正在运行的原子工具作业；无法停止时返回错误。"""
    try:
        ok = job_manager.cancel_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc
    if not ok:
        raise HTTPException(status_code=400, detail="Job cannot be stopped")
    return {"ok": True}


@router.post("/{tool_id}/run", response_model=JobResponse, summary="运行原子工具")
async def run_tool(tool_id: Annotated[str, Path(description="工具 ID")], params: dict) -> JobResponse:
    """以请求体中的参数创建指定原子工具的作业，并在后台异步执行，立即返回作业信息。"""
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


@router.get("/{tool_id}/jobs/{job_id}", response_model=JobResponse, summary="作业状态")
def get_job_status(
    tool_id: Annotated[str, Path(description="工具 ID")],
    job_id: Annotated[str, Path(description="作业 ID")],
) -> JobResponse:
    """返回指定原子工具下某个作业的当前状态；校验该作业确属此工具。"""
    return _require_job_for_tool(tool_id, job_id)


@router.get("/{tool_id}/jobs/{job_id}/result", summary="作业结果")
def get_job_result(
    tool_id: Annotated[str, Path(description="工具 ID")],
    job_id: Annotated[str, Path(description="作业 ID")],
) -> dict:
    """返回指定原子工具作业的执行结果；作业未完成时返回错误。"""
    job = _require_job_for_tool(tool_id, job_id)
    if job.status != "completed":
        raise HTTPException(status_code=409, detail="Job is not completed yet")
    return job_manager.get_job_result(job_id) or {}


@router.get(
    "/{tool_id}/jobs/{job_id}/artifacts",
    response_model=list[ArtifactInfo],
    summary="作业产物列表",
)
def list_job_artifacts(
    tool_id: Annotated[str, Path(description="工具 ID")],
    job_id: Annotated[str, Path(description="作业 ID")],
) -> list[ArtifactInfo]:
    """返回指定原子工具作业生成的产物文件列表。"""
    _require_job_for_tool(tool_id, job_id)
    return job_manager.list_artifacts(job_id)


@router.get("/{tool_id}/jobs/{job_id}/artifacts/{artifact_path:path}", summary="下载产物")
def download_artifact(
    tool_id: Annotated[str, Path(description="工具 ID")],
    job_id: Annotated[str, Path(description="作业 ID")],
    artifact_path: Annotated[str, Path(description="产物相对路径")],
):
    """按相对路径下载指定原子工具作业的某个产物文件；文件不存在时返回错误。"""
    _require_job_for_tool(tool_id, job_id)
    path = job_manager.get_artifact_path(job_id, artifact_path)
    if path is None or not path.exists():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(path, filename=path.name)
