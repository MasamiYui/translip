"""One-click, *iterative* auto-fix for dub evaluation.

Takes the auto-fixable segments surfaced by the remediation plan and runs the
real repair pipeline end-to-end, in a background thread, **for up to N rounds**:

    round r:  plan-dub-repair  ->  run-dub-repair (tournament, scoped to targets)
                              ->  render-dub (--selected-segments, re-mix render)
                              ->  re-evaluate (build_dub_qa)  ->  keep | rollback

Each round targets the segments the *current* report still flags as
auto-fixable, minus any segment already attempted (so the loop chips through a
large problem set across rounds and never oscillates — a segment is attempted at
most once). A round is kept only if the global score improves (or ties with
fewer problems); otherwise its render is rolled back and the loop tries the
remaining segments. Accepted repairs accumulate via a cumulative
``selected_segments`` set so a later round's re-render never drops an earlier
round's fixes. The loop stops when the report has no more auto-fixable segments
or the round budget is exhausted — i.e. it iterates toward convergence rather
than taking a single shot.

Each step is an isolated ``python -m translip`` subprocess (so heavy TTS models
are freed on exit and a crash can't poison the server), mirroring how the
pipeline orchestrator shells out. Progress is tracked in the ``analyses`` table
as an ``auto-fix`` row; on net improvement it also writes a fresh ``dub-qa``
analysis for the best mix so the evaluation page shows the new report. The job
result records the per-round trajectory plus overall before/after score.
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

# Minimum score gain for a round to be kept. Below this a round is treated as
# noise (TTS is partly stochastic) and rolled back so we never ship a cut that
# is not clearly better than where the round started.
_ACCEPT_EPS = 0.5


class AutoFixRequest(BaseModel):
    segment_ids: list[str] = Field(
        default_factory=list,
        description="要修复的片段 id（取自 remediation 的 repair_directive）；为空则由评测报告按风险自动选取。仅用于第 1 轮，后续轮次从最新报告重新推导剩余问题段。",
    )
    tts_backends: list[str] = Field(
        default_factory=list,
        description="修复使用的 TTS 后端；为空则沿用任务原后端，原后端不可用（如 moss 未安装）时回退到 voxcpm2。",
    )
    attempts_per_item: int = Field(default=3, ge=1, le=6, description="每个片段尝试的候选数（文本×参考×后端）。")
    max_items: int = Field(default=20, ge=1, le=100, description="每轮最多修复的片段数上限。")
    max_rounds: int = Field(default=3, ge=1, le=6, description="最多迭代修复的轮数；每轮针对当前报告剩余的可自动修复片段，逐轮收敛。")


@router.post("/{task_id}/auto-fix", response_model=AnalysisRead, summary="一键自动修复")
def create_auto_fix(
    task_id: Annotated[str, PathParam(description="任务 ID")],
    body: AutoFixRequest | None = None,
    session: Session = Depends(get_session),
):
    """对已评测任务的可自动修复片段发起一键迭代修复（重合成 → 重混 → 重评测，多轮收敛），后台异步运行。

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
# Pure decision helpers (unit-tested without any I/O)
# --------------------------------------------------------------------------- #


def _auto_fix_targets(report: dict[str, Any], attempted: set[str], max_items: int) -> list[str]:
    """The next round's targets: auto-fixable, repair-driven segment ids from a
    dub-qa ``report``, minus segments already attempted, de-duplicated and capped.

    Reads ``report["remediation"]["repair_directive"]["segment_ids"]`` — the
    exact handoff the remediation planner produces for ``run-dub-repair``.
    """
    remediation = report.get("remediation") if isinstance(report, dict) else None
    directive = (remediation or {}).get("repair_directive") if isinstance(remediation, dict) else None
    ids = (directive or {}).get("segment_ids") if isinstance(directive, dict) else None
    out: list[str] = []
    seen: set[str] = set()
    for raw in ids or []:
        sid = str(raw)
        if not sid or sid in attempted or sid in seen:
            continue
        seen.add(sid)
        out.append(sid)
        if len(out) >= max_items:
            break
    return out


def _round_accepted(
    before_score: Any,
    after_score: Any,
    before_problems: Any,
    after_problems: Any,
    eps: float = _ACCEPT_EPS,
) -> bool:
    """Keep a round only when it is clearly better than where it started.

    Score gain >= ``eps`` wins. A near-tie on score is kept only if the problem
    count strictly dropped. When scores are unavailable, fall back to the
    problem count. This is the per-round gate that guarantees the loop is
    monotonic (it never ships a worse cut).
    """
    bs = before_score if isinstance(before_score, (int, float)) else None
    as_ = after_score if isinstance(after_score, (int, float)) else None
    bp = before_problems if isinstance(before_problems, (int, float)) else None
    ap = after_problems if isinstance(after_problems, (int, float)) else None
    if bs is not None and as_ is not None:
        if as_ >= bs + eps:
            return True
        if as_ <= bs - eps:
            return False
        # Near-tie on score → only accept if it removed problems.
        if bp is not None and ap is not None:
            return ap < bp
        return False
    if bp is not None and ap is not None:
        return ap < bp
    return False


def _merge_selected_segments(base_segments: list[dict[str, Any]], round_path: Path) -> list[dict[str, Any]]:
    """Union accepted repairs with a round's fresh ``selected_segments`` payload.

    Keyed by ``segment_id`` (the latest attempt wins, though segments are
    attempted at most once). The cumulative set is what each re-render consumes,
    so a later round never drops an earlier round's accepted fix.
    """
    by_id: dict[str, dict[str, Any]] = {}
    for seg in base_segments:
        sid = str(seg.get("segment_id") or "")
        if sid:
            by_id[sid] = seg
    fresh = _read_json(round_path).get("segments") if round_path.exists() else None
    for seg in fresh or []:
        if isinstance(seg, dict) and seg.get("segment_id"):
            by_id[str(seg["segment_id"])] = seg
    return list(by_id.values())


# --------------------------------------------------------------------------- #
# I/O helpers
# --------------------------------------------------------------------------- #


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    return payload if isinstance(payload, dict) else {}


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


_PHASES_PER_ROUND = 4


def _set_phase(job_id: str, step: int, phase: str, round_idx: int, total_rounds: int) -> None:
    """Record which step of which round is running so the UI can show progress.

    Per round: plan(1) -> repair(2) -> render(3) -> evaluate(4). ``round`` /
    ``total_rounds`` let the UI render "round 2/3". Cleared on terminal status.
    Keeps the legacy ``step``/``total`` keys so older UI builds still work.
    """
    with Session(engine) as session:
        job = session.get(Analysis, job_id)
        if job is None:
            return
        job.progress = {
            "step": step,
            "total": _PHASES_PER_ROUND,
            "phase": phase,
            "round": round_idx,
            "total_rounds": total_rounds,
        }
        job.updated_at = datetime.now()
        session.add(job)
        session.commit()


def _log_tail(log_path: Path, lines: int = 12) -> str:
    try:
        return "\n".join(log_path.read_text(encoding="utf-8").splitlines()[-lines:])
    except Exception:  # noqa: BLE001
        return ""


def _render_flags(output_root: Path, target_lang: str) -> list[str]:
    """Preserve the original mix style so the re-render only swaps in repaired audio."""
    try:
        cfg = json.loads(
            (output_root / "render" / "voice" / f"mix_report.{target_lang}.json").read_text(encoding="utf-8")
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


def _latest_dubqa_report(task_id: str, output_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return ``(summary, report)`` for the latest succeeded dub-qa analysis.

    ``summary`` is the lightweight DB row result (score / problem count);
    ``report`` is the full on-disk report (segments + remediation) used to pick
    the first round's targets. Either may be ``{}`` if unavailable.
    """
    with Session(engine) as session:
        row = session.exec(
            select(Analysis)
            .where(Analysis.task_id == task_id)
            .where(Analysis.analysis_type == "dub-qa")
            .where(Analysis.status == "succeeded")
            .order_by(Analysis.created_at.desc())
        ).first()
        if row is None:
            return {}, {}
        summary = dict(row.result or {})
        report_path = row.report_path
    report: dict[str, Any] = {}
    if report_path:
        report = _read_json(output_root / report_path)
    return summary, report


# --------------------------------------------------------------------------- #
# Worker
# --------------------------------------------------------------------------- #


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

    seg_ids_req = list(params.get("segment_ids") or [])
    attempts = int(params.get("attempts_per_item") or 3)
    max_items = int(params.get("max_items") or 20)
    max_rounds = int(params.get("max_rounds") or 3)
    task_request = _task_request(output_root)
    backends = _choose_backends(list(params.get("tts_backends") or []), task_request)
    device = "cpu" if _FALLBACK_BACKEND in backends else str(task_request.get("device") or "auto")

    logs_dir = output_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / f"auto-fix-{job_id}.log"

    try:
        translation = output_root / "translation" / "voice" / f"translation.{target_lang}.json"
        profiles = output_root / "speaker-registry" / "voice" / "speaker_profiles.json"
        segments = output_root / "transcription" / "voice" / "segments.zh.json"
        task_d_reports = sorted((output_root / "synthesis" / "voice").glob(f"*/speaker_segments.{target_lang}.json"))
        backgrounds = sorted((output_root / "separation").glob("*/background.*"))
        ledger = output_root / "synthesis" / "voice" / "character-ledger" / f"character_ledger.{target_lang}.json"

        for label, path in (("translation", translation), ("profiles", profiles), ("segments", segments)):
            if not path.exists():
                raise RuntimeError(f"missing {label}: {path}")
        if not task_d_reports:
            raise RuntimeError("no synthesis speaker reports found (task not fully dubbed?)")
        if not backgrounds:
            raise RuntimeError("no separation background track found")
        background = backgrounds[0]

        before_summary, before_report = _latest_dubqa_report(task_id, output_root)
        overall_before_score = before_summary.get("score")
        overall_before_problems = before_summary.get("problem_segment_count")

        td_flags: list[Any] = []
        for report in task_d_reports:
            td_flags += ["--task-d-report", report]

        plan_dir = output_root / "synthesis" / "voice" / "repair-plan"
        run_dir = output_root / "synthesis" / "voice" / "repair-run"
        voice_dir = output_root / "render" / "voice"
        snap_names = [
            f"dub_voice.{target_lang}.wav",
            f"preview_mix.{target_lang}.wav",
            f"mix_report.{target_lang}.json",
            f"timeline.{target_lang}.json",
            "render-manifest.json",
        ]
        cumulative_selected = run_dir / f"selected_segments.cumulative.{target_lang}.json"

        # Rolling "best so far" state. We never ship a cut worse than this.
        best_score = overall_before_score
        best_problems = overall_before_problems
        best_report = before_report
        best_report_rel: str | None = None
        accepted_segments: list[dict[str, Any]] = []
        attempted: set[str] = set()
        rounds_log: list[dict[str, Any]] = []
        total_repaired = 0
        final_analysis_id: str | None = None

        for round_idx in range(1, max_rounds + 1):
            if round_idx == 1 and seg_ids_req:
                # Honor the caller's explicit selection for the first pass.
                seen: set[str] = set()
                targets = []
                for sid in seg_ids_req:
                    s = str(sid)
                    if s and s not in seen:
                        seen.add(s)
                        targets.append(s)
                targets = targets[:max_items]
            else:
                targets = _auto_fix_targets(best_report, attempted, max_items)
            if not targets:
                break  # converged — nothing left the loop can auto-fix
            attempted |= set(targets)

            # 1) Plan: build the repair queue / rewrite / reference plans, force-
            #    queuing this round's targets so QA-flagged defects are attempted.
            _set_phase(job_id, 1, "plan", round_idx, max_rounds)
            plan_args: list[Any] = [
                "plan-dub-repair",
                "--translation", translation,
                "--profiles", profiles,
                *td_flags,
                "--output-dir", plan_dir,
                "--target-lang", target_lang,
                "--max-items", max_items,
            ]
            for sid in targets:
                plan_args += ["--include-segment-id", sid]
            _run_cli(plan_args, log_path)

            # 2) Run: tournament-synthesize the targets, select the best.
            _set_phase(job_id, 2, "repair", round_idx, max_rounds)
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
            for sid in targets:
                run_args += ["--segment-id", sid]
            if ledger.exists():
                run_args += ["--character-ledger", ledger]
            _run_cli(run_args, log_path)

            round_selected = run_dir / f"selected_segments.{target_lang}.json"
            round_selected_count = 0
            try:
                round_selected_count = int(
                    _read_json(round_selected).get("stats", {}).get("selected_count", 0)
                )
            except Exception:  # noqa: BLE001
                pass

            # Accumulate accepted repairs + this round's selections, so the re-
            # render keeps earlier rounds' fixes (render uses base synthesis audio
            # for any segment NOT in selected_segments).
            candidate_segments = _merge_selected_segments(accepted_segments, round_selected)
            run_dir.mkdir(parents=True, exist_ok=True)
            cumulative_selected.write_text(
                json.dumps(
                    {"stats": {"selected_count": len(candidate_segments)}, "segments": candidate_segments},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            # Snapshot the current best render so this round can be rolled back.
            backup_dir = voice_dir / f".autofix-backup-{job_id}-r{round_idx}"
            backup_dir.mkdir(parents=True, exist_ok=True)
            for name in snap_names:
                src = voice_dir / name
                if src.exists():
                    shutil.copy2(src, backup_dir / name)

            # 3) Render: re-mix with the cumulative repaired audio.
            _set_phase(job_id, 3, "render", round_idx, max_rounds)
            _run_cli(
                [
                    "render-dub",
                    "--background", background,
                    "--segments", segments,
                    "--translation", translation,
                    *td_flags,
                    "--selected-segments", cumulative_selected,
                    "--output-dir", output_root / "render",
                    "--target-lang", target_lang,
                    *_render_flags(output_root, target_lang),
                ],
                log_path,
            )

            # 4) Re-evaluate the new mix.
            _set_phase(job_id, 4, "evaluate", round_idx, max_rounds)
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
            after_score = after.get("score")
            after_problems = after.get("problem_segment_count")
            try:
                report_rel = str(result.artifacts.report_path.resolve().relative_to(output_root.resolve()))
            except ValueError:
                report_rel = str(result.artifacts.report_path)

            accepted = _round_accepted(best_score, after_score, best_problems, after_problems)
            rounds_log.append(
                {
                    "round": round_idx,
                    "targets": len(targets),
                    "repaired": round_selected_count,
                    "before_score": best_score,
                    "after_score": after_score,
                    "before_problem_count": best_problems,
                    "after_problem_count": after_problems,
                    "accepted": accepted,
                }
            )

            if accepted:
                total_repaired += round_selected_count
                best_score = after_score
                best_problems = after_problems
                best_report = result.report
                best_report_rel = report_rel
                accepted_segments = candidate_segments
                final_analysis_id = reeval_id
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
                            params={"run_translation_judge": False, "via": "auto-fix", "round": round_idx},
                            result=after,
                            report_path=report_rel,
                            started_at=now,
                            finished_at=now,
                        )
                    )
                    session.commit()
                shutil.rmtree(backup_dir, ignore_errors=True)
            else:
                # Restore the better previous cut; targets stay in ``attempted``
                # so they are not retried. The loop continues with any remaining
                # auto-fixable segments next round.
                for name in snap_names:
                    bak = backup_dir / name
                    if bak.exists():
                        shutil.copy2(bak, voice_dir / name)
                shutil.rmtree(backup_dir, ignore_errors=True)

        improved = final_analysis_id is not None
        payload = {
            "before_score": overall_before_score,
            "after_score": best_score,
            "before_problem_count": overall_before_problems,
            "after_problem_count": best_problems,
            "rounds_run": len(rounds_log),
            "rounds": rounds_log,
            "repaired_count": total_repaired,
            "requested_count": len(seg_ids_req),
            "tts_backends": backends,
            "device": device,
            "max_rounds": max_rounds,
            "rolled_back": not improved,
            "new_analysis_id": final_analysis_id,
        }
        with Session(engine) as session:
            job = session.get(Analysis, job_id)
            if job is None:
                return
            job.status = "succeeded"
            job.result = payload
            job.progress = None
            job.report_path = best_report_rel if improved else None
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
            job.progress = None
            job.finished_at = datetime.now()
            job.updated_at = datetime.now()
            job.elapsed_sec = round(time.monotonic() - started, 3)
            session.add(job)
            session.commit()
