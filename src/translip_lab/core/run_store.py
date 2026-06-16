"""Run persistence, aggregation, and run-to-run comparison (regression).

A run directory holds ``run-manifest.json`` plus per-result JSON. Aggregates are
the per-scenario summary (mean/median of the primary metric, status counts).
``compare_runs`` diffs two runs and flags regressions according to each
scenario's ``higher_is_better``.
"""
from __future__ import annotations

import json
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Any

from .scenario import ScenarioResult

RUN_MANIFEST_NAME = "run-manifest.json"


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return float("nan")
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def aggregate_key(scenario: str, arm: str) -> str:
    """Aggregate key: bare scenario for the default arm, scenario@arm for sweeps."""
    return scenario if arm == "default" else f"{scenario}@{arm}"


def summarize_aggregates(results: list[ScenarioResult], scenario_meta: dict[str, dict]) -> dict[str, Any]:
    """Per (scenario, arm) summary: status counts + mean/median/std/p90/min/max of primary."""
    groups: dict[tuple[str, str], list[ScenarioResult]] = {}
    for r in results:
        groups.setdefault((r.scenario, getattr(r, "arm", "default")), []).append(r)

    aggregates: dict[str, Any] = {}
    for (scenario, arm), rows in groups.items():
        meta = scenario_meta.get(scenario, {})
        values = [r.primary_metric for r in rows if r.status == "succeeded" and r.primary_metric is not None]
        agg = {
            "scenario": scenario,
            "arm": arm,
            "primary_metric": meta.get("primary_metric_key"),
            "higher_is_better": meta.get("higher_is_better"),
            "count": len(rows),
            "succeeded": sum(1 for r in rows if r.status == "succeeded"),
            "failed": sum(1 for r in rows if r.status == "failed"),
            "skipped": sum(1 for r in rows if r.status == "skipped"),
            "scored": len(values),
        }
        if values:
            agg.update({
                "mean": round(mean(values), 4),
                "median": round(median(values), 4),
                "std": round(pstdev(values), 4) if len(values) > 1 else 0.0,
                "p90": round(_percentile(values, 0.9), 4),
                "min": round(min(values), 4),
                "max": round(max(values), 4),
            })
        aggregates[aggregate_key(scenario, arm)] = agg
    return aggregates


def write_run(run_dir: Path, manifest: dict[str, Any]) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / RUN_MANIFEST_NAME
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_run(run_dir: Path) -> dict[str, Any]:
    path = Path(run_dir) / RUN_MANIFEST_NAME
    return json.loads(path.read_text(encoding="utf-8"))


def list_runs(runs_dir: Path) -> list[dict[str, Any]]:
    runs_dir = Path(runs_dir)
    out: list[dict[str, Any]] = []
    if not runs_dir.exists():
        return out
    for child in sorted(runs_dir.iterdir(), reverse=True):
        manifest = child / RUN_MANIFEST_NAME
        if not manifest.is_file():
            continue
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        out.append({
            "run_id": data.get("run_id", child.name),
            "suite": data.get("suite"),
            "dataset": data.get("dataset"),
            "scenarios": data.get("scenarios", []),
            "started_at": data.get("started_at"),
            "elapsed_sec": data.get("elapsed_sec"),
            "aggregates": data.get("aggregates", {}),
            "run_dir": str(child),
        })
    return out


def compare_runs(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """Diff candidate against baseline per scenario. Positive delta = candidate − baseline."""
    base_agg = baseline.get("aggregates", {})
    cand_agg = candidate.get("aggregates", {})
    rows: list[dict[str, Any]] = []
    for name in sorted(set(base_agg) | set(cand_agg)):
        b = base_agg.get(name, {})
        c = cand_agg.get(name, {})
        b_mean = b.get("mean")
        c_mean = c.get("mean")
        higher_is_better = c.get("higher_is_better", b.get("higher_is_better"))
        delta = None
        regressed = None
        if isinstance(b_mean, (int, float)) and isinstance(c_mean, (int, float)):
            delta = round(c_mean - b_mean, 4)
            if higher_is_better is True:
                regressed = delta < 0
            elif higher_is_better is False:
                regressed = delta > 0
        rows.append({
            "scenario": name,
            "primary_metric": c.get("primary_metric", b.get("primary_metric")),
            "higher_is_better": higher_is_better,
            "baseline_mean": b_mean,
            "candidate_mean": c_mean,
            "delta": delta,
            "regressed": regressed,
        })
    return {
        "baseline_run": baseline.get("run_id"),
        "candidate_run": candidate.get("run_id"),
        "rows": rows,
        "regressions": [r["scenario"] for r in rows if r["regressed"]],
    }
