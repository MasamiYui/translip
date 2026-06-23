"""Background job runner for the lab dashboard.

Turns "trigger a run" from a fire-and-forget subprocess into a *tracked* job with a
lifecycle (``queued`` → ``running`` → ``succeeded`` | ``failed``). Jobs are serialized
through a single worker thread so heavy ML runs don't stampede a 16 GB host, their
output is captured to a log, and a small JSON record per job is persisted under
``<runs>/.jobs/`` so the list survives a server restart and is inspectable.

The job id is reused as the run id (``--run-id``), so a finished job points straight
at ``<runs>/<job_id>/run-manifest.json`` (the detail page / report endpoint). The
worker shells out to the same ``python -m translip_lab run`` the CLI uses — one-way
coupling, models freed on subprocess exit, exactly like every other lab stage.
"""
from __future__ import annotations

import json
import subprocess
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from queue import Queue
from typing import Any

_TERMINAL = ("succeeded", "failed")


def _safe(text: str) -> str:
    return "".join(c if (c.isalnum() or c in "-_.") else "_" for c in text)


@dataclass
class Job:
    job_id: str
    cmd: list[str]
    suite: str | None = None
    dataset: str | None = None
    scenarios: list[str] = field(default_factory=list)
    status: str = "queued"  # queued | running | succeeded | failed
    run_id: str | None = None  # == job_id once a run-manifest exists
    returncode: int | None = None
    created_at: str = ""
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class JobManager:
    def __init__(self, *, runs_dir: Path, max_workers: int = 1) -> None:
        self.runs_dir = Path(runs_dir)
        self.jobs_dir = self.runs_dir / ".jobs"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._seq = 0
        self._queue: Queue[str] = Queue()
        self._load_existing()
        for _ in range(max(1, max_workers)):
            threading.Thread(target=self._worker, daemon=True).start()

    # ---- ids / paths -------------------------------------------------------
    def _now(self) -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")

    def new_job_id(self, label: str | None) -> str:
        with self._lock:
            self._seq += 1
            seq = self._seq
        stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
        return f"{stamp}-{_safe(label or 'run')}-{seq:03d}"

    def log_path(self, job_id: str) -> Path:
        return self.jobs_dir / f"{job_id}.log"

    def _record_path(self, job_id: str) -> Path:
        return self.jobs_dir / f"{job_id}.json"

    # ---- persistence -------------------------------------------------------
    def _persist(self, job: Job) -> None:
        try:
            self._record_path(job.job_id).write_text(
                json.dumps(job.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    def _load_existing(self) -> None:
        for rec in self.jobs_dir.glob("*.json"):
            try:
                data = json.loads(rec.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            fields = {k: data.get(k) for k in Job.__dataclass_fields__ if k in data}
            try:
                job = Job(**fields)
            except TypeError:
                continue
            # a job still 'queued'/'running' from a prior process is orphaned
            if job.status not in _TERMINAL:
                job.status = "failed"
                job.error = job.error or "interrupted (server restarted)"
                self._persist(job)
            self._jobs[job.job_id] = job

    # ---- api ---------------------------------------------------------------
    def submit(self, *, cmd: list[str], job_id: str, suite: str | None = None,
               dataset: str | None = None, scenarios: list[str] | None = None) -> Job:
        job = Job(job_id=job_id, cmd=list(cmd), suite=suite, dataset=dataset,
                  scenarios=list(scenarios or []), created_at=self._now())
        with self._lock:
            self._jobs[job_id] = job
        self._persist(job)
        self._queue.put(job_id)
        return job

    def list_jobs(self) -> list[dict[str, Any]]:
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
        return [j.to_dict() for j in jobs]

    def get_job(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def tail_log(self, job_id: str, n: int = 8000) -> str:
        path = self.log_path(job_id)
        if not path.is_file():
            return ""
        return path.read_text(encoding="utf-8", errors="replace")[-n:]

    # ---- worker ------------------------------------------------------------
    def _worker(self) -> None:
        while True:
            job_id = self._queue.get()
            try:
                self._run_job(job_id)
            except Exception:  # noqa: BLE001 — never let the worker thread die
                job = self._jobs.get(job_id)
                if job and job.status not in _TERMINAL:
                    job.status = "failed"
                    job.finished_at = self._now()
                    self._persist(job)
            finally:
                self._queue.task_done()

    def _run_job(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            return
        job.status = "running"
        job.started_at = self._now()
        self._persist(job)
        try:
            with self.log_path(job_id).open("w", encoding="utf-8") as fh:
                fh.write(f"$ {' '.join(job.cmd)}\n\n")
                fh.flush()
                proc = subprocess.run(job.cmd, stdout=fh, stderr=subprocess.STDOUT)
            job.returncode = proc.returncode
        except Exception as exc:  # noqa: BLE001 — surface as a failed job
            job.status = "failed"
            job.error = f"{type(exc).__name__}: {exc}"
            job.finished_at = self._now()
            self._persist(job)
            return
        # A produced run-manifest means the run actually completed (a non-zero exit
        # may just be a --fail-under gate, which still yields real results).
        if (self.runs_dir / job_id / "run-manifest.json").is_file():
            job.status = "succeeded"
            job.run_id = job_id
        else:
            job.status = "failed"
            job.error = f"exit {job.returncode}; no run-manifest produced — see log"
        job.finished_at = self._now()
        self._persist(job)
