"""Standalone FastAPI dashboard for the lab — own port, own origin.

Read/visualize runs + datasets + scenarios, and trigger a run (by shelling out
to ``python -m translip_lab run``, the same path the CLI uses). The UI is a single
self-contained static page (no npm/Vite) so the lab stays decoupled: the main
translip app only needs a link to this server's URL.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from ..config import load_config
from ..core.run_store import compare_runs, list_runs, load_run
from ..core.scenario import SCENARIO_REGISTRY
from ..datasets import DATASET_REGISTRY, get_dataset
from .. import scenarios as _scenarios  # noqa: F401 — registers scenarios

_WEB_DIR = Path(__file__).parent / "web"
_SUITES_DIR = Path(__file__).resolve().parent.parent / "suites"

app = FastAPI(title="translip-lab", version="0.1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)


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


@app.get("/api/lab/compare")
def api_compare(baseline: str, candidate: str) -> dict[str, Any]:
    config = load_config()
    for rid in (baseline, candidate):
        if not (config.runs_dir / rid / "run-manifest.json").is_file():
            raise HTTPException(status_code=404, detail=f"run not found: {rid}")
    return compare_runs(load_run(config.runs_dir / baseline), load_run(config.runs_dir / candidate))


@app.post("/api/lab/runs")
def api_trigger_run(payload: dict[str, Any]) -> dict[str, Any]:
    """Launch a run in the background (subprocess → translip-lab run)."""
    cmd = [sys.executable, "-m", "translip_lab", "run"]
    if payload.get("suite"):
        cmd += ["--suite", str(payload["suite"])]
    elif payload.get("dataset") and payload.get("scenarios"):
        scenarios = payload["scenarios"]
        scenarios = ",".join(scenarios) if isinstance(scenarios, list) else str(scenarios)
        cmd += ["--dataset", str(payload["dataset"]), "--scenario", scenarios]
    else:
        raise HTTPException(status_code=400, detail="provide 'suite' or ('dataset' and 'scenarios')")
    if payload.get("limit") is not None:
        cmd += ["--limit", str(payload["limit"])]
    if payload.get("no_cache"):
        cmd += ["--no-cache"]

    threading.Thread(target=lambda: subprocess.run(cmd, cwd=os.getcwd()), daemon=True).start()
    return {"status": "started", "cmd": cmd}


def run_server(host: str | None = None, port: int | None = None) -> None:
    import uvicorn

    host = host or os.environ.get("TRANSLIP_LAB_HOST", "127.0.0.1")
    port = int(port or os.environ.get("TRANSLIP_LAB_PORT", "8799"))
    uvicorn.run(app, host=host, port=port)
