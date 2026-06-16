"""Markdown rendering of a run manifest and a run-vs-run comparison."""
from __future__ import annotations

from typing import Any


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value)


def run_to_markdown(manifest: dict[str, Any]) -> str:
    lines = [
        f"# Lab run `{manifest.get('run_id')}`",
        "",
        f"- suite: `{manifest.get('suite')}`",
        f"- dataset: `{manifest.get('dataset')}`",
        f"- samples: {manifest.get('sample_count')}",
        f"- started: {manifest.get('started_at')}",
        f"- elapsed: {manifest.get('elapsed_sec')}s",
        "",
        "## Aggregates",
        "",
        "| scenario | metric | mean | micro | std | median | min | max | scored | failed | skipped |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for name, agg in manifest.get("aggregates", {}).items():
        arrow = "↓" if agg.get("higher_is_better") is False else ("↑" if agg.get("higher_is_better") else "")
        metric = agg.get("primary_metric")
        micro = (agg.get("corpus") or {}).get(f"{metric}_micro")
        lines.append(
            f"| {name} | {_fmt(metric)} {arrow} | {_fmt(agg.get('mean'))} | {_fmt(micro)} | "
            f"{_fmt(agg.get('std'))} | {_fmt(agg.get('median'))} | {_fmt(agg.get('min'))} | "
            f"{_fmt(agg.get('max'))} | {agg.get('scored', 0)} | {agg.get('failed', 0)} | {agg.get('skipped', 0)} |"
        )

    sweep = sweep_to_markdown(manifest)
    if sweep:
        lines += ["", sweep]

    lines += ["", "## Per-sample results", "",
              "| sample | scenario | status | primary | cached | error |",
              "|---|---|---|---|---|---|"]
    for r in manifest.get("results", []):
        err = (r.get("error") or "").splitlines()[0][:80] if r.get("error") else ""
        lines.append(
            f"| {r['sample_id']} | {r['scenario']} | {r['status']} | {_fmt(r.get('primary_metric'))} | "
            f"{'✓' if r.get('cached') else ''} | {err} |"
        )
    return "\n".join(lines) + "\n"


def sweep_to_markdown(manifest: dict[str, Any]) -> str:
    """Config-sweep matrix: per scenario, one row per arm, winner marked."""
    if len(manifest.get("arms", [])) <= 1:
        return ""
    by_scenario: dict[str, list[dict[str, Any]]] = {}
    for agg in manifest.get("aggregates", {}).values():
        by_scenario.setdefault(agg.get("scenario", "?"), []).append(agg)

    out: list[str] = ["## Sweep (config arms)", ""]
    for scenario, rows in by_scenario.items():
        metric = rows[0].get("primary_metric")
        higher = rows[0].get("higher_is_better")
        scored = [r for r in rows if isinstance(r.get("mean"), (int, float))]
        winner = None
        if scored:
            winner = (max if higher else min)(scored, key=lambda r: r["mean"]).get("arm")
        out.append(f"### {scenario} ({metric} {'↑' if higher else '↓'})")
        out.append("| arm | mean | micro | std | scored |")
        out.append("|---|---|---|---|---|")
        for r in sorted(rows, key=lambda r: (r.get("mean") is None, r.get("mean", 0))):
            micro = (r.get("corpus") or {}).get(f"{metric}_micro")
            star = " 🏆" if r.get("arm") == winner else ""
            out.append(f"| {r.get('arm')}{star} | {_fmt(r.get('mean'))} | {_fmt(micro)} | "
                       f"{_fmt(r.get('std'))} | {r.get('scored', 0)} |")
        out.append("")
    return "\n".join(out)


def compare_to_markdown(comparison: dict[str, Any]) -> str:
    lines = [
        f"# Compare `{comparison.get('baseline_run')}` → `{comparison.get('candidate_run')}`",
        "",
        "| scenario | metric | baseline | candidate | Δ | verdict |",
        "|---|---|---|---|---|---|",
    ]
    for row in comparison.get("rows", []):
        verdict = "—"
        if row.get("regressed") is True:
            verdict = "⚠️ regressed"
        elif row.get("regressed") is False:
            verdict = "✅ improved/flat"
        lines.append(
            f"| {row['scenario']} | {_fmt(row.get('primary_metric'))} | {_fmt(row.get('baseline_mean'))} | "
            f"{_fmt(row.get('candidate_mean'))} | {_fmt(row.get('delta'))} | {verdict} |"
        )
    regressions = comparison.get("regressions") or []
    lines += ["", f"**Regressions:** {', '.join(regressions) if regressions else 'none'}", ""]
    return "\n".join(lines) + "\n"
