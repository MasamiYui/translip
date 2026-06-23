"""Standalone FastAPI dashboard for the lab — own port, own origin.

Read/visualize runs + datasets + scenarios, and trigger a run (by shelling out
to ``python -m translip_lab run``, the same path the CLI uses). The UI is a single
self-contained static page (no npm/Vite) so the lab stays decoupled: the main
translip app only needs a link to this server's URL.
"""
from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse

from ..config import load_config
from ..core.run_store import compare_runs, list_runs, load_run
from ..core.scenario import SCENARIO_REGISTRY
from ..report.markdown import run_to_markdown
from ..datasets import DATASET_REGISTRY, get_dataset
from .. import scenarios as _scenarios  # noqa: F401 — registers scenarios
from .jobs import JobManager

_WEB_DIR = Path(__file__).parent / "web"
_SUITES_DIR = Path(__file__).resolve().parent.parent / "suites"

app = FastAPI(title="translip-lab", version="0.1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# One JobManager per runs_dir, created lazily — so tests with isolated
# TRANSLIP_LAB_HOME don't share a worker/queue, and a deployed server keeps one.
_job_managers: dict[str, JobManager] = {}
_jm_lock = threading.Lock()


def get_job_manager() -> JobManager:
    runs_dir = load_config().runs_dir
    key = str(runs_dir)
    with _jm_lock:
        jm = _job_managers.get(key)
        if jm is None:
            jm = JobManager(runs_dir=runs_dir)
            _job_managers[key] = jm
        return jm


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    page = _WEB_DIR / "index.html"
    return page.read_text(encoding="utf-8") if page.is_file() else "<h1>translip-lab</h1>"


@app.get("/api/lab/scenarios")
def api_scenarios() -> list[dict[str, Any]]:
    return [
        {"name": name, "primary_metric": s.primary_metric_key,
         "higher_is_better": s.higher_is_better, "required_gt": s.required_gt()}
        for name, s in sorted(SCENARIO_REGISTRY.items())
    ]


@app.get("/api/lab/suites")
def api_suites() -> list[str]:
    if not _SUITES_DIR.is_dir():
        return []
    return sorted(p.stem for p in _SUITES_DIR.glob("*.toml"))


@app.get("/api/lab/datasets")
def api_datasets() -> list[dict[str, Any]]:
    config = load_config()
    out: list[dict[str, Any]] = []
    for name in sorted(DATASET_REGISTRY):
        try:
            out.append(get_dataset(name, config).describe())
        except Exception as exc:  # noqa: BLE001
            out.append({"name": name, "error": str(exc)})
    return out


@app.get("/api/lab/runs")
def api_runs() -> list[dict[str, Any]]:
    return list_runs(load_config().runs_dir)


@app.get("/api/lab/runs/{run_id}")
def api_run_detail(run_id: str) -> dict[str, Any]:
    run_dir = load_config().runs_dir / run_id
    if not (run_dir / "run-manifest.json").is_file():
        raise HTTPException(status_code=404, detail=f"run not found: {run_id}")
    return load_run(run_dir)


@app.get("/api/lab/runs/{run_id}/report.md")
def api_run_report(run_id: str) -> PlainTextResponse:
    """Markdown report for a run (download)."""
    run_dir = load_config().runs_dir / run_id
    if not (run_dir / "run-manifest.json").is_file():
        raise HTTPException(status_code=404, detail=f"run not found: {run_id}")
    md = run_to_markdown(load_run(run_dir))
    return PlainTextResponse(
        md, media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{run_id}.md"'},
    )


@app.get("/api/lab/compare")
def api_compare(baseline: str, candidate: str) -> dict[str, Any]:
    config = load_config()
    for rid in (baseline, candidate):
        if not (config.runs_dir / rid / "run-manifest.json").is_file():
            raise HTTPException(status_code=404, detail=f"run not found: {rid}")
    return compare_runs(load_run(config.runs_dir / baseline), load_run(config.runs_dir / candidate))


@app.post("/api/lab/runs")
def api_trigger_run(payload: dict[str, Any]) -> dict[str, Any]:
    """Submit a tracked run job (queued → running → succeeded/failed; serialized)."""
    suite = payload.get("suite")
    dataset = payload.get("dataset")
    raw_scenarios = payload.get("scenarios")
    tail: list[str] = []
    if suite:
        tail += ["--suite", str(suite)]
    elif dataset and raw_scenarios:
        joined = ",".join(raw_scenarios) if isinstance(raw_scenarios, list) else str(raw_scenarios)
        tail += ["--dataset", str(dataset), "--scenario", joined]
    else:
        raise HTTPException(status_code=400, detail="provide 'suite' or ('dataset' and 'scenarios')")
    if payload.get("limit") is not None:
        tail += ["--limit", str(payload["limit"])]
    if payload.get("no_cache"):
        tail += ["--no-cache"]

    scenarios = raw_scenarios if isinstance(raw_scenarios, list) else ([raw_scenarios] if raw_scenarios else [])
    jm = get_job_manager()
    job_id = jm.new_job_id(suite or dataset)
    cmd = [sys.executable, "-m", "translip_lab", "run", "--run-id", job_id, *tail]
    job = jm.submit(cmd=cmd, job_id=job_id, suite=suite, dataset=dataset, scenarios=scenarios)
    return {"status": job.status, "job_id": job.job_id, "run_id": job.job_id, "cmd": job.cmd}


@app.get("/api/lab/jobs")
def api_jobs() -> list[dict[str, Any]]:
    return get_job_manager().list_jobs()


@app.get("/api/lab/jobs/{job_id}")
def api_job_detail(job_id: str) -> dict[str, Any]:
    jm = get_job_manager()
    job = jm.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"job not found: {job_id}")
    return {**job.to_dict(), "log_tail": jm.tail_log(job_id)}


def run_server(host: str | None = None, port: int | None = None) -> None:
    import uvicorn

    host = host or os.environ.get("TRANSLIP_LAB_HOST", "127.0.0.1")
    port = int(port or os.environ.get("TRANSLIP_LAB_PORT", "8799"))
    uvicorn.run(app, host=host, port=port)
