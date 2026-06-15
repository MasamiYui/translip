"""The runner — iterate samples × scenarios, with caching, into a run directory.

Sequential by design: scenarios shell out to translip stages that load multi-GB
models, so running them one at a time avoids memory blow-ups (the same reason
translip serializes heavy tools). Results are cached cross-run by
(scenario, sample, config, input fingerprints); a cache hit reuses the metrics
without re-running the stage.
"""
from __future__ import annotations

import json
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import LabConfig
from .cache import scenario_cache_key
from .invoke import Invoker
from .run_store import summarize_aggregates, write_run
from .sample import SampleManifest
from .scenario import Scenario, ScenarioResult


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _safe_id(text: str) -> str:
    return "".join(c if (c.isalnum() or c in "-_.") else "_" for c in text)


def run_suite(
    *,
    manifest: SampleManifest,
    scenarios: list[Scenario],
    suite: str,
    invoker: Invoker,
    lab_config: LabConfig,
    scenario_config: dict[str, dict] | None = None,
    limit: int | None = None,
    timeout_sec: float | None = None,
    use_cache: bool = True,
    run_id: str | None = None,
    on_progress: Callable[[dict], None] | None = None,
) -> dict[str, Any]:
    scenario_config = scenario_config or {}
    samples = manifest.samples[:limit] if limit else list(manifest.samples)
    if run_id is None:
        run_id = datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + _safe_id(suite)
    run_dir = lab_config.runs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    cache_results_dir = lab_config.cache_dir / "results"
    cache_results_dir.mkdir(parents=True, exist_ok=True)

    started = _now_iso()
    start_t = time.time()
    results: list[ScenarioResult] = []
    total = len(samples) * len(scenarios)
    idx = 0
    for sample in samples:
        for scenario in scenarios:
            idx += 1
            cfg = scenario_config.get(scenario.name, {})
            work_dir = run_dir / _safe_id(sample.sample_id) / scenario.name
            key = scenario_cache_key(
                scenario=scenario.name, sample_id=sample.sample_id, config=cfg,
                input_paths=[str(p) for p in scenario.input_paths(sample)],
            )
            cache_file = cache_results_dir / f"{key}.json"

            result: ScenarioResult | None = None
            if use_cache and cache_file.is_file():
                try:
                    result = ScenarioResult.from_dict(json.loads(cache_file.read_text(encoding="utf-8")))
                    result.cached = True
                except (json.JSONDecodeError, KeyError, OSError):
                    result = None
            if result is None:
                result = scenario.run(sample, work_dir, invoker, config=cfg, timeout=timeout_sec)
                if use_cache and result.status in ("succeeded", "skipped"):
                    try:
                        cache_file.write_text(
                            json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
                    except OSError:
                        pass

            results.append(result)
            try:
                work_dir.mkdir(parents=True, exist_ok=True)
                (work_dir / "result.json").write_text(
                    json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
            except OSError:
                pass

            if on_progress:
                on_progress({
                    "phase": "result", "index": idx, "total": total,
                    "sample_id": sample.sample_id, "scenario": scenario.name,
                    "status": result.status, "primary_metric": result.primary_metric,
                    "cached": result.cached,
                })

    scenario_meta = {
        s.name: {"primary_metric_key": s.primary_metric_key, "higher_is_better": s.higher_is_better}
        for s in scenarios
    }
    aggregates = summarize_aggregates(results, scenario_meta)
    run_manifest = {
        "run_id": run_id,
        "suite": suite,
        "dataset": manifest.dataset,
        "scenarios": [s.name for s in scenarios],
        "sample_count": len(samples),
        "config": {
            "limit": limit, "timeout_sec": timeout_sec, "use_cache": use_cache,
            "scenario_config": scenario_config,
        },
        "started_at": started,
        "finished_at": _now_iso(),
        "elapsed_sec": round(time.time() - start_t, 3),
        "aggregates": aggregates,
        "results": [r.to_dict() for r in results],
    }
    write_run(run_dir, run_manifest)
    return run_manifest
