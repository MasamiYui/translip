from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query

from ...exceptions import BackendUnavailableError
from ..assistant.executor import run_manager
from ..assistant.models import (
    AssistantRunListResponse,
    ExecuteRequest,
    PlanRequest,
    PlanResult,
    RunState,
)
from ..assistant.planner import generate_plan

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


@router.post("/plan", response_model=PlanResult, summary="规划原子能力调用链路")
def plan_chain(body: PlanRequest) -> PlanResult:
    """用 DeepSeek 把自然语言需求规划成调用链路；信息不足时返回澄清问题（只规划不执行）。"""
    try:
        return generate_plan(
            body.message,
            filenames=body.filenames,
            history=body.history,
            available_files=body.available_files,
        )
    except BackendUnavailableError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/execute", summary="执行调用链路")
def execute_chain(body: ExecuteRequest) -> dict[str, str]:
    """按已确认（可编辑过）的计划顺序执行原子能力链路，立即返回 run_id。"""
    try:
        run_id = run_manager.start_run(
            body.plan,
            upload_file_ids=body.file_ids,
            conversation_id=body.conversation_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"run_id": run_id}


@router.get("/runs", response_model=AssistantRunListResponse, summary="AI 任务列表")
def list_runs(
    status: str | None = Query(None, description="按状态过滤，留空为不过滤"),
    search: str | None = Query(None, description="按关键字搜索（需求/摘要/ID），留空为不过滤"),
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    size: int = Query(20, ge=1, le=100, description="每页条数，取值 1~100"),
) -> AssistantRunListResponse:
    """分页查询经 AI 助手执行的任务（链路运行）列表。"""
    return run_manager.list_runs(status=status, search=search, page=page, size=size)


@router.get("/runs/{run_id}", response_model=RunState, summary="运行状态")
def get_run(run_id: Annotated[str, Path(description="运行 ID")]) -> RunState:
    """返回某次链路执行的实时状态（每步状态/进度/产物，用于链路图实时点亮）。"""
    try:
        return run_manager.get_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@router.post("/runs/{run_id}/cancel", summary="取消运行")
def cancel_run(run_id: Annotated[str, Path(description="运行 ID")]) -> dict[str, bool]:
    """请求取消正在执行的链路。"""
    try:
        ok = run_manager.cancel_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc
    if not ok:
        raise HTTPException(status_code=400, detail="Run cannot be cancelled")
    return {"ok": True}


@router.post("/runs/{run_id}/rerun", summary="重跑任务")
def rerun_run(run_id: Annotated[str, Path(description="运行 ID")]) -> dict[str, str]:
    """以原计划重新执行一次，返回新的 run_id。"""
    try:
        new_run_id = run_manager.rerun_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc
    return {"run_id": new_run_id}


@router.delete("/runs/{run_id}", summary="删除任务记录")
def delete_run(run_id: Annotated[str, Path(description="运行 ID")]) -> dict[str, bool]:
    """删除该 AI 任务记录（不影响底层原子作业及其产物）。"""
    try:
        run_manager.delete_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc
    return {"ok": True}
