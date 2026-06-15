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
        "| scenario | metric | mean | median | min | max | scored | failed | skipped |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for name, agg in manifest.get("aggregates", {}).items():
        arrow = "↓ lower better" if agg.get("higher_is_better") is False else (
            "↑ higher better" if agg.get("higher_is_better") else "")
        lines.append(
            f"| {name} | {_fmt(agg.get('primary_metric'))} {arrow} | {_fmt(agg.get('mean'))} | "
            f"{_fmt(agg.get('median'))} | {_fmt(agg.get('min'))} | {_fmt(agg.get('max'))} | "
            f"{agg.get('scored', 0)} | {agg.get('failed', 0)} | {agg.get('skipped', 0)} |"
        )

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
