"""Task-linked dub-quality analysis (the "评测 / 实验分析" feature).

A dub-QA analysis runs :func:`translip.quality.build_dub_qa` against a finished
task's output directory and persists a lightweight summary in the ``analyses``
table; the full per-segment report is written under
``{output_root}/analysis/{analysis_id}/`` and served back via ``/report``.

The run happens in a daemon thread, mirroring ``task_manager`` so the heavy
(optional) translation-judge calls don't block the request.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Path as PathParam
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ...quality import DubQaRequest, build_dub_qa
from ..database import engine, get_session
from ..models import Analysis, Task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["analysis"])


class CreateAnalysisRequest(BaseModel):
    run_translation_judge: bool = Field(
        default=False,
        description="是否调用翻译评审（translation-judge）对译文质量逐句打分；为可选的付费/耗时步骤，默认关闭。",
    )


class AnalysisRead(BaseModel):
    id: str = Field(description="分析记录 ID（形如 ana-xxxxxxxxxxxx）。")
    task_id: str = Field(description="所属任务（task）ID。")
    analysis_type: str = Field(description="分析类型，当前为 dub-qa（配音质量评测）。")
    status: str = Field(description="分析状态：pending（待运行）/running（运行中）/succeeded（成功）/failed（失败）。")
    target_lang: str = Field(description="目标语言（继承自任务），即配音/译文语言。")
    source_lang: str = Field(description="源语言（继承自任务），即原始视频语言。")
    params: dict[str, Any] = Field(description="本次分析的运行参数，例如 run_translation_judge 是否启用翻译评审。")
    result: Optional[dict[str, Any]] = Field(
        default=None,
        description="轻量汇总结果（评分、问题计数等）；完整逐句报告通过 /report 接口获取。未完成时为空。",
    )
    progress: Optional[dict[str, Any]] = Field(
        default=None,
        description="运行中的阶段进度（仅一键自动修复填充）：step（当前第几步）/ total（总步数）/ phase（阶段标识：plan/repair/render/evaluate）。完成后清空。",
    )
    report_path: Optional[str] = Field(
        default=None,
        description="完整配音质量报告文件相对任务输出根目录的路径；分析成功后填充。",
    )
    error_message: Optional[str] = Field(default=None, description="分析失败时的错误信息（截断至 1000 字符）。")
    created_at: datetime = Field(description="记录创建时间。")
    updated_at: datetime = Field(description="记录最近更新时间。")
    started_at: Optional[datetime] = Field(default=None, description="分析开始运行的时间；尚未开始时为空。")
    finished_at: Optional[datetime] = Field(default=None, description="分析结束（成功或失败）的时间；未结束时为空。")
    elapsed_sec: Optional[float] = Field(default=None, description="分析耗时（秒）；完成后填充。")


def _to_read(analysis: Analysis) -> AnalysisRead:
    return AnalysisRead(
        id=analysis.id,
        task_id=analysis.task_id,
        analysis_type=analysis.analysis_type,
        status=analysis.status,
        target_lang=analysis.target_lang,
        source_lang=analysis.source_lang,
        params=analysis.params or {},
        result=analysis.result,
        progress=analysis.progress,
        report_path=analysis.report_path,
        error_message=analysis.error_message,
        created_at=analysis.created_at,
        updated_at=analysis.updated_at,
        started_at=analysis.started_at,
        finished_at=analysis.finished_at,
        elapsed_sec=analysis.elapsed_sec,
    )


@router.post("/{task_id}/analyses/dub-qa", response_model=AnalysisRead, summary="发起配音质量评测")
def create_dub_qa_analysis(
    task_id: Annotated[str, PathParam(description="任务 ID")],
    body: CreateAnalysisRequest | None = None,
    session: Session = Depends(get_session),
):
    """对已产出的任务发起配音质量（dub-QA）评测，在后台线程异步运行并落库。

    若该任务已有处于 pending/running 的评测在进行，则直接返回那条记录（避免重复运行与重复付费的翻译评审调用）。任务无输出时返回 409。
    """
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if not Path(task.output_root).exists():
        raise HTTPException(status_code=409, detail="Task has no output yet; run the pipeline first")

    # Don't spawn a duplicate run (or duplicate paid judge calls) while one is in
    # flight for this task — return the existing one so the client just polls it.
    in_flight = session.exec(
        select(Analysis)
        .where(Analysis.task_id == task_id)
        .where(Analysis.status.in_(("pending", "running")))  # type: ignore[attr-defined]
        .order_by(Analysis.created_at.desc())
    ).first()
    if in_flight is not None:
        return _to_read(in_flight)

    body = body or CreateAnalysisRequest()
    analysis = Analysis(
        id=f"ana-{uuid.uuid4().hex[:12]}",
        task_id=task_id,
        analysis_type="dub-qa",
        status="pending",
        target_lang=task.target_lang,
        source_lang=task.source_lang,
        params={"run_translation_judge": body.run_translation_judge},
    )
    session.add(analysis)
    session.commit()
    session.refresh(analysis)

    thread = threading.Thread(target=_run_dub_qa_in_thread, args=(analysis.id,), daemon=True)
    thread.start()
    return _to_read(analysis)


@router.get("/{task_id}/analyses", response_model=list[AnalysisRead], summary="任务评测列表")
def list_analyses(
    task_id: Annotated[str, PathParam(description="任务 ID")],
    session: Session = Depends(get_session),
):
    """列出指定任务的全部分析记录，按创建时间倒序返回。任务不存在时返回 404。"""
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    rows = session.exec(
        select(Analysis).where(Analysis.task_id == task_id).order_by(Analysis.created_at.desc())
    ).all()
    return [_to_read(row) for row in rows]


@router.get("/{task_id}/analyses/{analysis_id}", response_model=AnalysisRead, summary="评测详情")
def get_analysis(
    task_id: Annotated[str, PathParam(description="任务 ID")],
    analysis_id: Annotated[str, PathParam(description="评测记录 ID")],
    session: Session = Depends(get_session),
):
    """获取指定任务下某条分析记录的状态与汇总信息（用于轮询运行进度）。记录不存在或不属于该任务时返回 404。"""
    analysis = session.get(Analysis, analysis_id)
    if not analysis or analysis.task_id != task_id:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return _to_read(analysis)


@router.get("/{task_id}/analyses/{analysis_id}/report", summary="评测完整报告")
def get_analysis_report(
    task_id: Annotated[str, PathParam(description="任务 ID")],
    analysis_id: Annotated[str, PathParam(description="评测记录 ID")],
    session: Session = Depends(get_session),
):
    """读取并返回该分析的完整逐句配音质量报告（JSON）。仅当分析成功且报告文件存在时可用，否则返回 409/404。

    报告路径会被限制在任务输出根目录内，越界访问返回 403。
    """
    analysis = session.get(Analysis, analysis_id)
    if not analysis or analysis.task_id != task_id:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if analysis.status != "succeeded" or not analysis.report_path:
        raise HTTPException(status_code=409, detail=f"Analysis not ready (status={analysis.status})")
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    output_root = Path(task.output_root).resolve()
    report_path = (output_root / analysis.report_path).resolve()
    if not report_path.is_relative_to(output_root):
        raise HTTPException(status_code=403, detail="Access denied")
    if not report_path.exists() or not report_path.is_file():
        raise HTTPException(status_code=404, detail="Report file not found")
    try:
        return json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Failed to read report: {exc}") from exc


@router.delete("/{task_id}/analyses/{analysis_id}", summary="删除评测记录")
def delete_analysis(
    task_id: Annotated[str, PathParam(description="任务 ID")],
    analysis_id: Annotated[str, PathParam(description="评测记录 ID")],
    session: Session = Depends(get_session),
):
    """删除指定任务下的一条分析记录（仅删除数据库记录）。记录不存在或不属于该任务时返回 404。"""
    analysis = session.get(Analysis, analysis_id)
    if not analysis or analysis.task_id != task_id:
        raise HTTPException(status_code=404, detail="Analysis not found")
    session.delete(analysis)
    session.commit()
    return {"deleted": analysis_id}


def _run_dub_qa_in_thread(analysis_id: str) -> None:
    with Session(engine) as session:
        analysis = session.get(Analysis, analysis_id)
        if analysis is None:
            return
        task = session.get(Task, analysis.task_id)
        if task is None:
            analysis.status = "failed"
            analysis.error_message = "Task not found"
            session.add(analysis)
            session.commit()
            return
        analysis.status = "running"
        analysis.started_at = datetime.now()
        analysis.updated_at = datetime.now()
        session.add(analysis)
        session.commit()
        output_root = Path(task.output_root)
        target_lang = task.target_lang
        source_lang = task.source_lang
        run_translation_judge = bool((analysis.params or {}).get("run_translation_judge"))

    out_dir = output_root / "analysis" / analysis_id

    def _set_phase(step: int, total: int, phase: str) -> None:
        """Persist the active evaluation phase so the UI can render a stepper.

        Best-effort: a failed progress write must never abort the evaluation.
        """
        try:
            with Session(engine) as s:
                row = s.get(Analysis, analysis_id)
                if row is None:
                    return
                row.progress = {"step": step, "total": total, "phase": phase}
                row.updated_at = datetime.now()
                s.add(row)
                s.commit()
        except Exception:  # noqa: BLE001 - progress is non-critical
            logger.debug("Failed to persist dub-qa phase for %s", analysis_id, exc_info=True)

    try:
        result = build_dub_qa(
            DubQaRequest(
                pipeline_root=output_root,
                output_dir=out_dir,
                target_lang=target_lang,
                source_lang=source_lang,
                run_translation_judge=run_translation_judge,
            ),
            on_phase=_set_phase,
        )
        try:
            report_rel = str(result.artifacts.report_path.resolve().relative_to(output_root.resolve()))
        except ValueError:
            report_rel = str(result.artifacts.report_path)
        summary = dict(result.manifest.get("summary", {}))
        elapsed = result.manifest.get("timing", {}).get("elapsed_sec")
        with Session(engine) as session:
            analysis = session.get(Analysis, analysis_id)
            if analysis is None:
                return
            analysis.status = "succeeded"
            analysis.result = summary
            analysis.report_path = report_rel
            analysis.progress = None
            analysis.finished_at = datetime.now()
            analysis.updated_at = datetime.now()
            analysis.elapsed_sec = elapsed
            session.add(analysis)
            session.commit()
    except Exception as exc:  # noqa: BLE001 - persisted as failure status
        logger.exception("Dub QA analysis %s failed: %s", analysis_id, exc)
        with Session(engine) as session:
            analysis = session.get(Analysis, analysis_id)
            if analysis is None:
                return
            analysis.status = "failed"
            analysis.error_message = str(exc)[:1000]
            analysis.progress = None
            analysis.finished_at = datetime.now()
            analysis.updated_at = datetime.now()
            session.add(analysis)
            session.commit()
