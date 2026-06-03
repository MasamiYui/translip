"""One-click auto-fix for dub evaluation.

Takes the auto-fixable segments surfaced by the remediation plan and runs the
real repair pipeline end-to-end in a background thread:

    plan-dub-repair  ->  run-dub-repair (tournament, scoped to the segments)
                     ->  render-dub (--selected-segments, re-mix into task-e)
                     ->  re-evaluate (build_dub_qa)

Each step is an isolated ``python -m translip`` subprocess (so heavy TTS models
are freed on exit and a crash can't poison the server), mirroring how the
pipeline orchestrator shells out. Progress is tracked in the ``analyses`` table
as an ``auto-fix`` row; on success it also writes a fresh ``dub-qa`` analysis for
the improved mix so the evaluation page shows the new (hopefully better) report.
The job result records before/after score so the UI can show the delta.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path as PathParam
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ...quality import DubQaRequest, build_dub_qa
from ..database import engine, get_session
from ..models import Analysis, Task
from .analysis import AnalysisRead, _to_read

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["analysis"])

AUTO_FIX_TYPE = "auto-fix"
_FALLBACK_BACKEND = "voxcpm2"


class AutoFixRequest(BaseModel):
    segment_ids: list[str] = Field(
        default_factory=list,
        description="要修复的片段 id（取自 remediation 的 repair_directive）；为空则由修复引擎按风险队列自动选取。",
    )
    tts_backends: list[str] = Field(
        default_factory=list,
        description="修复使用的 TTS 后端；为空则沿用任务原后端，原后端不可用（如 moss 未安装）时回退到 voxcpm2。",
    )
    attempts_per_item: int = Field(default=3, ge=1, le=6, description="每个片段尝试的候选数（文本×参考×后端）。")
    max_items: int = Field(default=20, ge=1, le=100, description="最多修复的片段数上限。")


@router.post("/{task_id}/auto-fix", response_model=AnalysisRead, summary="一键自动修复")
def create_auto_fix(
    task_id: Annotated[str, PathParam(description="任务 ID")],
    body: AutoFixRequest | None = None,
    session: Session = Depends(get_session),
):
    """对已评测任务的可自动修复片段发起一键修复（重合成 → 重混 → 重评测），后台异步运行。

    若已有 auto-fix 在运行则直接返回该记录。任务无输出时返回 409。
    """
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if not Path(task.output_root).exists():
        raise HTTPException(status_code=409, detail="Task has no output yet; run the pipeline first")

    in_flight = session.exec(
        select(Analysis)
        .where(Analysis.task_id == task_id)
        .where(Analysis.analysis_type == AUTO_FIX_TYPE)
        .where(Analysis.status.in_(("pending", "running")))  # type: ignore[attr-defined]
        .order_by(Analysis.created_at.desc())
    ).first()
    if in_flight is not None:
        return _to_read(in_flight)

    body = body or AutoFixRequest()
    job = Analysis(
        id=f"fix-{uuid.uuid4().hex[:12]}",
        task_id=task_id,
        analysis_type=AUTO_FIX_TYPE,
        status="pending",
        target_lang=task.target_lang,
        source_lang=task.source_lang,
        params=body.model_dump(),
    )
    session.add(job)
    session.commit()
    session.refresh(job)

    import threading

    threading.Thread(target=_run_auto_fix_in_thread, args=(job.id,), daemon=True).start()
    return _to_read(job)


@router.get("/{task_id}/auto-fix/{job_id}", response_model=AnalysisRead, summary="自动修复进度")
def get_auto_fix(
    task_id: Annotated[str, PathParam(description="任务 ID")],
    job_id: Annotated[str, PathParam(description="自动修复任务 ID")],
    session: Session = Depends(get_session),
):
    """轮询一键自动修复的状态与 before/after 汇总。记录不存在或类型不符时返回 404。"""
    job = session.get(Analysis, job_id)
    if not job or job.task_id != task_id or job.analysis_type != AUTO_FIX_TYPE:
        raise HTTPException(status_code=404, detail="Auto-fix job not found")
    return _to_read(job)


# --------------------------------------------------------------------------- #
# Worker
# --------------------------------------------------------------------------- #


def _moss_available() -> bool:
    return bool(os.environ.get("MOSS_TTS_NANO_CLI") or shutil.which("moss-tts-nano"))


def _task_request(output_root: Path) -> dict[str, Any]:
    try:
        return json.loads((output_root / "request.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _choose_backends(override: list[str], task_request: dict[str, Any]) -> list[str]:
    if override:
        return override
    original = task_request.get("tts_backend")
    if original and (original != "moss-tts-nano-onnx" or _moss_available()):
        return [original]
    return [_FALLBACK_BACKEND]


def _run_cli(args: list[Any], log_path: Path) -> None:
    """Run a translip CLI subcommand as an isolated subprocess, streamed to a log."""
    cmd = [sys.executable, "-m", "translip", *[str(a) for a in args]]
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault("HF_HUB_DISABLE_XET", "1")
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"\n$ {' '.join(cmd)}\n")
        log.flush()
        proc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, env=env, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"`{args[0]}` failed (exit {proc.returncode}); see logs/{log_path.name}")


def _log_tail(log_path: Path, lines: int = 12) -> str:
    try:
        return "\n".join(log_path.read_text(encoding="utf-8").splitlines()[-lines:])
    except Exception:  # noqa: BLE001
        return ""


def _render_flags(output_root: Path, target_lang: str) -> list[str]:
    """Preserve the original mix style so the re-render only swaps in repaired audio."""
    try:
        cfg = json.loads(
            (output_root / "task-e" / "voice" / f"mix_report.{target_lang}.json").read_text(encoding="utf-8")
        ).get("config", {})
    except Exception:  # noqa: BLE001
        cfg = {}
    flags: list[str] = []
    mapping = {
        "fit_policy": "--fit-policy",
        "fit_backend": "--fit-backend",
        "mix_profile": "--mix-profile",
        "ducking_mode": "--ducking-mode",
        "max_compress_ratio": "--max-compress-ratio",
        "output_sample_rate": "--output-sample-rate",
        "background_gain_db": "--background-gain-db",
        "window_ducking_db": "--window-ducking-db",
        "quality_gate": "--quality-gate",
    }
    for key, flag in mapping.items():
        if cfg.get(key) is not None:
            flags += [flag, str(cfg[key])]
    return flags


def _latest_dubqa_summary(task_id: str) -> dict[str, Any]:
    with Session(engine) as session:
        row = session.exec(
            select(Analysis)
            .where(Analysis.task_id == task_id)
            .where(Analysis.analysis_type == "dub-qa")
            .where(Analysis.status == "succeeded")
            .order_by(Analysis.created_at.desc())
        ).first()
        return dict(row.result or {}) if row else {}


def _run_auto_fix_in_thread(job_id: str) -> None:
    started = time.monotonic()
    with Session(engine) as session:
        job = session.get(Analysis, job_id)
        if job is None:
            return
        task = session.get(Task, job.task_id)
        if task is None:
            job.status = "failed"
            job.error_message = "Task not found"
            job.updated_at = datetime.now()
            session.add(job)
            session.commit()
            return
        job.status = "running"
        job.started_at = datetime.now()
        job.updated_at = datetime.now()
        session.add(job)
        session.commit()
        task_id = job.task_id
        output_root = Path(task.output_root)
        target_lang = task.target_lang
        source_lang = task.source_lang
        params = dict(job.params or {})

    seg_ids = list(params.get("segment_ids") or [])
    attempts = int(params.get("attempts_per_item") or 3)
    max_items = int(params.get("max_items") or 20)
    task_request = _task_request(output_root)
    backends = _choose_backends(list(params.get("tts_backends") or []), task_request)
    device = "cpu" if _FALLBACK_BACKEND in backends else str(task_request.get("device") or "auto")

    logs_dir = output_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / f"auto-fix-{job_id}.log"

    try:
        translation = output_root / "task-c" / "voice" / f"translation.{target_lang}.json"
        profiles = output_root / "task-b" / "voice" / "speaker_profiles.json"
        segments = output_root / "task-a" / "voice" / "segments.zh.json"
        task_d_reports = sorted((output_root / "task-d" / "voice").glob(f"*/speaker_segments.{target_lang}.json"))
        backgrounds = sorted((output_root / "stage1").glob("*/background.*"))
        ledger = output_root / "task-d" / "voice" / "character-ledger" / f"character_ledger.{target_lang}.json"

        for label, path in (("translation", translation), ("profiles", profiles), ("segments", segments)):
            if not path.exists():
                raise RuntimeError(f"missing {label}: {path}")
        if not task_d_reports:
            raise RuntimeError("no task-d speaker reports found (task not fully dubbed?)")
        if not backgrounds:
            raise RuntimeError("no stage1 background track found")
        background = backgrounds[0]

        before = _latest_dubqa_summary(task_id)
        td_flags: list[str] = []
        for report in task_d_reports:
            td_flags += ["--task-d-report", report]

        plan_dir = output_root / "task-d" / "voice" / "repair-plan"
        run_dir = output_root / "task-d" / "voice" / "repair-run"

        # 1) Plan: build the repair queue / rewrite / reference plans. Force-queue
        #    the QA-flagged segments so defects the evaluation found on the final
        #    mix (but task-d passed) are actually attempted, not silently skipped.
        plan_args: list[Any] = [
            "plan-dub-repair",
            "--translation", translation,
            "--profiles", profiles,
            *td_flags,
            "--output-dir", plan_dir,
            "--target-lang", target_lang,
            "--max-items", max_items,
        ]
        for sid in seg_ids:
            plan_args += ["--include-segment-id", sid]
        _run_cli(plan_args, log_path)

        # 2) Run: tournament-synthesize the flagged segments, select the best.
        run_args: list[Any] = [
            "run-dub-repair",
            "--repair-queue", plan_dir / f"repair_queue.{target_lang}.json",
            "--rewrite-plan", plan_dir / f"rewrite_plan.{target_lang}.json",
            "--reference-plan", plan_dir / f"reference_plan.{target_lang}.json",
            "--output-dir", run_dir,
            "--device", device,
            "--max-items", max_items,
            "--attempts-per-item", attempts,
            "--include-risk",
        ]
        for backend in backends:
            run_args += ["--tts-backend", backend]
        for sid in seg_ids:
            run_args += ["--segment-id", sid]
        if ledger.exists():
            run_args += ["--character-ledger", ledger]
        _run_cli(run_args, log_path)

        selected_path = run_dir / f"selected_segments.{target_lang}.json"
        selected_count = 0
        try:
            selected_count = int(
                json.loads(selected_path.read_text(encoding="utf-8")).get("stats", {}).get("selected_count", 0)
            )
        except Exception:  # noqa: BLE001
            pass

        # Snapshot task-e before overwriting, so a regression can be rolled back —
        # the repair's per-segment accept gate is local, but the benchmark is
        # global, so "fixing more" can still lower the overall score (e.g. timbre
        # drift). Auto-fix must never ship a worse cut than it started with.
        voice_dir = output_root / "task-e" / "voice"
        snap_names = [
            f"dub_voice.{target_lang}.wav",
            f"preview_mix.{target_lang}.wav",
            f"mix_report.{target_lang}.json",
            f"timeline.{target_lang}.json",
            "task-e-manifest.json",
        ]
        backup_dir = voice_dir / f".autofix-backup-{job_id}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        for name in snap_names:
            src = voice_dir / name
            if src.exists():
                shutil.copy2(src, backup_dir / name)

        # 3) Render: re-mix with the repaired audio, overwriting task-e in place.
        _run_cli(
            [
                "render-dub",
                "--background", background,
                "--segments", segments,
                "--translation", translation,
                *td_flags,
                "--selected-segments", selected_path,
                "--output-dir", output_root / "task-e",
                "--target-lang", target_lang,
                *_render_flags(output_root, target_lang),
            ],
            log_path,
        )

        # 4) Re-evaluate the new mix.
        reeval_id = f"ana-{uuid.uuid4().hex[:12]}"
        result = build_dub_qa(
            DubQaRequest(
                pipeline_root=output_root,
                output_dir=output_root / "analysis" / reeval_id,
                target_lang=target_lang,
                source_lang=source_lang,
            )
        )
        after = dict(result.manifest.get("summary", {}))
        try:
            report_rel = str(result.artifacts.report_path.resolve().relative_to(output_root.resolve()))
        except ValueError:
            report_rel = str(result.artifacts.report_path)

        before_score = before.get("score")
        after_score = after.get("score")
        regressed = (
            isinstance(before_score, (int, float))
            and isinstance(after_score, (int, float))
            and after_score < before_score
        )

        if regressed:
            # Restore the better previous cut; keep the prior evaluation as latest.
            for name in snap_names:
                bak = backup_dir / name
                if bak.exists():
                    shutil.copy2(bak, voice_dir / name)
            kept_analysis_id = None
        else:
            # Improvement (or tie): surface the new mix as a fresh dub-qa analysis.
            now = datetime.now()
            with Session(engine) as session:
                session.add(
                    Analysis(
                        id=reeval_id,
                        task_id=task_id,
                        analysis_type="dub-qa",
                        status="succeeded",
                        target_lang=target_lang,
                        source_lang=source_lang,
                        params={"run_translation_judge": False, "via": "auto-fix"},
                        result=after,
                        report_path=report_rel,
                        started_at=now,
                        finished_at=now,
                    )
                )
                session.commit()
            kept_analysis_id = reeval_id
        shutil.rmtree(backup_dir, ignore_errors=True)

        payload = {
            "before_score": before_score,
            "after_score": after_score,
            "before_problem_count": before.get("problem_segment_count"),
            "after_problem_count": after.get("problem_segment_count"),
            "repaired_count": selected_count,
            "requested_count": len(seg_ids),
            "tts_backends": backends,
            "device": device,
            "rolled_back": regressed,
            "new_analysis_id": kept_analysis_id,
        }
        with Session(engine) as session:
            job = session.get(Analysis, job_id)
            if job is None:
                return
            job.status = "succeeded"
            job.result = payload
            job.report_path = report_rel if not regressed else None
            job.finished_at = datetime.now()
            job.updated_at = datetime.now()
            job.elapsed_sec = round(time.monotonic() - started, 3)
            session.add(job)
            session.commit()
    except Exception as exc:  # noqa: BLE001 - persisted as failure status
        logger.exception("Auto-fix %s failed: %s", job_id, exc)
        tail = _log_tail(log_path)
        message = f"{exc}".strip()
        if tail:
            message = f"{message}\n--- log tail ---\n{tail}"
        with Session(engine) as session:
            job = session.get(Analysis, job_id)
            if job is None:
                return
            job.status = "failed"
            job.error_message = message[:1500]
            job.finished_at = datetime.now()
            job.updated_at = datetime.now()
            job.elapsed_sec = round(time.monotonic() - started, 3)
            session.add(job)
            session.commit()
