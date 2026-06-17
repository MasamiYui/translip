from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path

from ...exceptions import BackendUnavailableError
from ..assistant.executor import run_manager
from ..assistant.models import (
    AssistantPlan,
    ExecuteRequest,
    PlanRequest,
    RunState,
)
from ..assistant.planner import generate_plan

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


@router.post("/plan", response_model=AssistantPlan, summary="规划原子能力调用链路")
def plan_chain(body: PlanRequest) -> AssistantPlan:
    """用 DeepSeek 把自然语言需求规划成一条原子能力调用链路（只规划不执行）。"""
    try:
        return generate_plan(body.message, filenames=body.filenames)
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
