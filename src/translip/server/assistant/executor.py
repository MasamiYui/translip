"""Chained execution of a planned atomic-tool call chain.

The executor is deliberately thin: each plan step becomes an ordinary atomic-tool
job. Chaining works because atomic-tool *artifacts* are themselves stored files
with their own ``file_id`` (``AtomicToolFile`` kind="artifact"), and the job
manager materializes/validates any stored ``file_id`` — upload or artifact —
identically. So feeding step N's output into step N+1 is just passing the prior
job's artifact ``file_id`` as the next job's ``*_file_id`` parameter.

Runs execute on a daemon thread (mirroring ``task_manager``). Each step calls the
job manager's synchronous worker ``_execute_job_sync`` — the same internal entry
``recover_pending_jobs`` drives from threads — so run/heavy concurrency limits are
honoured and assistant runs coexist safely with manual atomic-tool jobs.
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy.engine import Engine
from sqlmodel import Session

from ..atomic_tools.job_manager import job_manager as default_job_manager
from ..database import engine as default_engine
from ..models import AssistantRun
from .catalog import is_file_param
from .models import AssistantPlan, RunState, RunStepState, StepArtifact


class AssistantRunError(RuntimeError):
    pass


class AssistantRunManager:
    def __init__(self, *, job_manager: Any = None, db_engine: Engine | None = None) -> None:
        self.job_manager = job_manager or default_job_manager
        self.db_engine = db_engine or default_engine
        self._cancel_events: dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    # -- public API ---------------------------------------------------------

    def start_run(
        self,
        plan: AssistantPlan,
        *,
        upload_file_ids: list[str],
        conversation_id: str | None = None,
        message: str = "",
        background: bool = True,
    ) -> str:
        run_id = uuid4().hex
        now = datetime.now()
        steps = [
            {
                "id": step.id,
                "tool_id": step.tool_id,
                "title": step.title or step.tool_id,
                "job_id": None,
                "status": "pending",
                "error": None,
            }
            for step in plan.steps
        ]
        with self._session() as session:
            session.add(
                AssistantRun(
                    id=run_id,
                    conversation_id=conversation_id,
                    status="pending",
                    message=message,
                    summary=plan.summary,
                    plan=plan.model_dump(),
                    upload_file_ids=list(upload_file_ids),
                    steps=steps,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.commit()
        if background:
            threading.Thread(target=self._run_sync, args=(run_id,), daemon=True).start()
        else:
            self._run_sync(run_id)
        return run_id

    def get_run(self, run_id: str) -> RunState:
        with self._session() as session:
            run = session.get(AssistantRun, run_id)
            if run is None:
                raise KeyError(run_id)
            stored_status = run.status
            stored_steps = list(run.steps)
            message = run.message
            summary = run.summary
            error = run.error_message
        step_states = [self._step_state(step) for step in stored_steps]
        return RunState(
            run_id=run_id,
            status=stored_status,  # type: ignore[arg-type]
            message=message,
            summary=summary,
            steps=step_states,
            error_message=error,
        )

    def cancel_run(self, run_id: str) -> bool:
        with self._session() as session:
            run = session.get(AssistantRun, run_id)
            if run is None:
                raise KeyError(run_id)
            if run.status not in ("pending", "running"):
                return False
            active_job_ids = [s.get("job_id") for s in run.steps if s.get("status") == "running"]
        self._cancel_event_for(run_id).set()
        for job_id in active_job_ids:
            if job_id:
                try:
                    self.job_manager.cancel_job(job_id)
                except KeyError:
                    pass
        self._update_run(run_id, status="cancelled", finished_at=datetime.now())
        return True

    # -- execution ----------------------------------------------------------

    def _run_sync(self, run_id: str) -> None:
        cancel_event = self._cancel_event_for(run_id)
        with self._session() as session:
            run = session.get(AssistantRun, run_id)
            if run is None:
                return
            plan = AssistantPlan.model_validate(run.plan)
            upload_file_ids = list(run.upload_file_ids)
            steps = list(run.steps)
        self._update_run(run_id, status="running")
        # step_id -> completed atomic job_id, for resolving downstream bindings.
        completed_jobs: dict[str, str] = {}
        try:
            for index, step in enumerate(plan.steps):
                if cancel_event.is_set():
                    self._update_run(run_id, status="cancelled", finished_at=datetime.now())
                    return
                try:
                    params = self._resolve_params(step, upload_file_ids, completed_jobs)
                except AssistantRunError as exc:
                    self._fail_step(run_id, index, steps, str(exc))
                    return
                job = self.job_manager.create_job(step.tool_id, params)
                steps[index]["job_id"] = job.job_id
                steps[index]["status"] = "running"
                self._persist_steps(run_id, steps)
                # Synchronous worker — blocks until the job finishes (acquires the
                # run/heavy semaphores internally).
                self.job_manager._execute_job_sync(job.job_id)  # noqa: SLF001
                detail = self.job_manager.get_job(job.job_id)
                if detail.status != "completed":
                    reason = detail.error_message or f"步骤 {step.title or step.tool_id} {detail.status}"
                    steps[index]["status"] = detail.status
                    steps[index]["error"] = reason
                    self._persist_steps(run_id, steps)
                    final = "cancelled" if detail.status == "cancelled" else "failed"
                    self._update_run(
                        run_id,
                        status=final,
                        error_message=None if final == "cancelled" else reason,
                        finished_at=datetime.now(),
                    )
                    return
                steps[index]["status"] = "completed"
                self._persist_steps(run_id, steps)
                completed_jobs[step.id] = job.job_id
            self._update_run(run_id, status="completed", finished_at=datetime.now())
        except Exception as exc:  # pragma: no cover - defensive
            self._update_run(run_id, status="failed", error_message=str(exc), finished_at=datetime.now())
        finally:
            self._drop_cancel_event(run_id)

    def _resolve_params(
        self,
        step: Any,
        upload_file_ids: list[str],
        completed_jobs: dict[str, str],
    ) -> dict[str, Any]:
        params: dict[str, Any] = {k: v for k, v in step.params.items() if not is_file_param(k)}
        for param_name, binding in step.inputs.items():
            if binding.source == "upload":
                idx = binding.upload_index or 0
                if idx >= len(upload_file_ids):
                    raise AssistantRunError(
                        f"步骤「{step.title or step.tool_id}」需要第 {idx + 1} 个上传文件，但未提供。"
                    )
                params[param_name] = upload_file_ids[idx]
            elif binding.source == "step":
                params[param_name] = self._resolve_step_output(step, binding, completed_jobs)
            else:  # pragma: no cover - schema-constrained
                raise AssistantRunError(f"未知的输入来源：{binding.source}")
        return params

    def _resolve_step_output(self, step: Any, binding: Any, completed_jobs: dict[str, str]) -> str:
        job_id = completed_jobs.get(binding.step_id or "")
        if job_id is None:
            raise AssistantRunError(
                f"步骤「{step.title or step.tool_id}」依赖的上游步骤 {binding.step_id} 尚未完成。"
            )
        result = self.job_manager.get_job_result(job_id) or {}
        artifacts = self.job_manager.list_artifacts(job_id)
        if not artifacts:
            raise AssistantRunError(f"上游步骤 {binding.step_id} 没有产物可供下一步使用。")
        if binding.output:
            target_name = result.get(binding.output)
            if not target_name:
                raise AssistantRunError(
                    f"上游步骤 {binding.step_id} 没有输出「{binding.output}」。"
                )
            for artifact in artifacts:
                if artifact.filename == target_name or artifact.filename.endswith(f"/{target_name}"):
                    if artifact.file_id:
                        return artifact.file_id
            raise AssistantRunError(
                f"在步骤 {binding.step_id} 的产物中找不到「{target_name}」。"
            )
        # No explicit output: only safe when there's a single artifact.
        if len(artifacts) == 1 and artifacts[0].file_id:
            return artifacts[0].file_id
        raise AssistantRunError(
            f"步骤 {binding.step_id} 有多个产物，请在 binding 中指定 output。"
        )

    # -- step serialization -------------------------------------------------

    def _step_state(self, stored: dict[str, Any]) -> RunStepState:
        job_id = stored.get("job_id")
        state = RunStepState(
            id=stored["id"],
            tool_id=stored["tool_id"],
            title=stored.get("title", ""),
            job_id=job_id,
            status=stored.get("status", "pending"),
            error_message=stored.get("error"),
        )
        if job_id:
            try:
                detail = self.job_manager.get_job_detail(job_id)
            except KeyError:
                return state
            state.status = detail.status
            state.progress_percent = detail.progress_percent
            state.current_step = detail.current_step
            state.error_message = detail.error_message or stored.get("error")
            state.artifacts = [
                StepArtifact(
                    filename=a.filename,
                    download_url=a.download_url,
                    file_id=a.file_id,
                    size_bytes=a.size_bytes,
                    content_type=a.content_type,
                )
                for a in detail.artifacts
            ]
        return state

    # -- db helpers ---------------------------------------------------------

    def _session(self) -> Session:
        return Session(self.db_engine)

    def _persist_steps(self, run_id: str, steps: list[dict[str, Any]]) -> None:
        self._update_run(run_id, steps=list(steps))

    def _fail_step(self, run_id: str, index: int, steps: list[dict[str, Any]], reason: str) -> None:
        steps[index]["status"] = "failed"
        steps[index]["error"] = reason
        self._persist_steps(run_id, steps)
        self._update_run(run_id, status="failed", error_message=reason, finished_at=datetime.now())

    def _update_run(self, run_id: str, **values: Any) -> None:
        with self._session() as session:
            run = session.get(AssistantRun, run_id)
            if run is None:
                raise KeyError(run_id)
            for key, value in values.items():
                setattr(run, key, value)
            run.updated_at = datetime.now()
            session.add(run)
            session.commit()

    # -- cancellation -------------------------------------------------------

    def _cancel_event_for(self, run_id: str) -> threading.Event:
        with self._lock:
            event = self._cancel_events.get(run_id)
            if event is None:
                event = threading.Event()
                self._cancel_events[run_id] = event
            return event

    def _drop_cancel_event(self, run_id: str) -> None:
        with self._lock:
            self._cancel_events.pop(run_id, None)


run_manager = AssistantRunManager()
