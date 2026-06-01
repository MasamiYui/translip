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
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ...quality import DubQaRequest, build_dub_qa
from ..database import engine, get_session
from ..models import Analysis, Task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["analysis"])


class CreateAnalysisRequest(BaseModel):
    run_translation_judge: bool = False


class AnalysisRead(BaseModel):
    id: str
    task_id: str
    analysis_type: str
    status: str
    target_lang: str
    source_lang: str
    params: dict[str, Any]
    result: Optional[dict[str, Any]] = None
    report_path: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    elapsed_sec: Optional[float] = None


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
        report_path=analysis.report_path,
        error_message=analysis.error_message,
        created_at=analysis.created_at,
        updated_at=analysis.updated_at,
        started_at=analysis.started_at,
        finished_at=analysis.finished_at,
        elapsed_sec=analysis.elapsed_sec,
    )


@router.post("/{task_id}/analyses/dub-qa", response_model=AnalysisRead)
def create_dub_qa_analysis(
    task_id: str,
    body: CreateAnalysisRequest | None = None,
    session: Session = Depends(get_session),
):
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


@router.get("/{task_id}/analyses", response_model=list[AnalysisRead])
def list_analyses(task_id: str, session: Session = Depends(get_session)):
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    rows = session.exec(
        select(Analysis).where(Analysis.task_id == task_id).order_by(Analysis.created_at.desc())
    ).all()
    return [_to_read(row) for row in rows]


@router.get("/{task_id}/analyses/{analysis_id}", response_model=AnalysisRead)
def get_analysis(task_id: str, analysis_id: str, session: Session = Depends(get_session)):
    analysis = session.get(Analysis, analysis_id)
    if not analysis or analysis.task_id != task_id:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return _to_read(analysis)


@router.get("/{task_id}/analyses/{analysis_id}/report")
def get_analysis_report(task_id: str, analysis_id: str, session: Session = Depends(get_session)):
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
    if not str(report_path).startswith(str(output_root)):
        raise HTTPException(status_code=403, detail="Access denied")
    if not report_path.exists() or not report_path.is_file():
        raise HTTPException(status_code=404, detail="Report file not found")
    try:
        return json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Failed to read report: {exc}") from exc


@router.delete("/{task_id}/analyses/{analysis_id}")
def delete_analysis(task_id: str, analysis_id: str, session: Session = Depends(get_session)):
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
    try:
        result = build_dub_qa(
            DubQaRequest(
                pipeline_root=output_root,
                output_dir=out_dir,
                target_lang=target_lang,
                source_lang=source_lang,
                run_translation_judge=run_translation_judge,
            )
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
            analysis.finished_at = datetime.now()
            analysis.updated_at = datetime.now()
            session.add(analysis)
            session.commit()
