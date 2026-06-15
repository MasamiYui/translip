"""Self-contained HTML rendering (no external assets) for runs and comparisons."""
from __future__ import annotations

from typing import Any

_STYLE = """
body{font:14px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;margin:24px;color:#1a1a1a;background:#fafafa}
h1{font-size:20px}h2{font-size:16px;margin-top:24px}
table{border-collapse:collapse;width:100%;background:#fff;margin:8px 0;box-shadow:0 1px 2px rgba(0,0,0,.06)}
th,td{border:1px solid #e3e3e3;padding:6px 10px;text-align:left;font-variant-numeric:tabular-nums}
th{background:#f3f4f6}
.meta{color:#555}.fail{color:#b91c1c}.skip{color:#a16207}.ok{color:#15803d}
tr.reg{background:#fef2f2}tr.imp{background:#f0fdf4}
.badge{display:inline-block;padding:1px 6px;border-radius:4px;font-size:12px}
"""


def _esc(value: Any) -> str:
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.4g}"
    return _esc(value)


def _page(title: str, body: str) -> str:
    return f"<!doctype html><html><head><meta charset='utf-8'><title>{_esc(title)}</title><style>{_STYLE}</style></head><body>{body}</body></html>"


def run_to_html(manifest: dict[str, Any]) -> str:
    head = (
        f"<h1>Lab run <code>{_esc(manifest.get('run_id'))}</code></h1>"
        f"<p class='meta'>suite <b>{_esc(manifest.get('suite'))}</b> · dataset "
        f"<b>{_esc(manifest.get('dataset'))}</b> · {manifest.get('sample_count')} samples · "
        f"{_esc(manifest.get('elapsed_sec'))}s · {_esc(manifest.get('started_at'))}</p>"
    )
    agg_rows = "".join(
        f"<tr><td>{_esc(name)}</td><td>{_fmt(a.get('primary_metric'))} "
        f"{'↓' if a.get('higher_is_better') is False else ('↑' if a.get('higher_is_better') else '')}</td>"
        f"<td>{_fmt(a.get('mean'))}</td><td>{_fmt(a.get('median'))}</td><td>{_fmt(a.get('min'))}</td>"
        f"<td>{_fmt(a.get('max'))}</td><td>{a.get('scored', 0)}</td>"
        f"<td class='fail'>{a.get('failed', 0)}</td><td class='skip'>{a.get('skipped', 0)}</td></tr>"
        for name, a in manifest.get("aggregates", {}).items()
    )
    agg = (
        "<h2>Aggregates</h2><table><tr><th>scenario</th><th>metric</th><th>mean</th><th>median</th>"
        "<th>min</th><th>max</th><th>scored</th><th>failed</th><th>skipped</th></tr>" + agg_rows + "</table>"
    )
    res_rows = ""
    for r in manifest.get("results", []):
        status = r.get("status")
        cls = {"failed": "fail", "skipped": "skip", "succeeded": "ok"}.get(status, "")
        err = (r.get("error") or "").splitlines()[0][:100] if r.get("error") else ""
        res_rows += (
            f"<tr><td>{_esc(r['sample_id'])}</td><td>{_esc(r['scenario'])}</td>"
            f"<td class='{cls}'>{_esc(status)}</td><td>{_fmt(r.get('primary_metric'))}</td>"
            f"<td>{'✓' if r.get('cached') else ''}</td><td class='fail'>{_esc(err)}</td></tr>"
        )
    res = (
        "<h2>Per-sample results</h2><table><tr><th>sample</th><th>scenario</th><th>status</th>"
        "<th>primary</th><th>cached</th><th>error</th></tr>" + res_rows + "</table>"
    )
    return _page(f"Lab run {manifest.get('run_id')}", head + agg + res)


def compare_to_html(comparison: dict[str, Any]) -> str:
    head = (
        f"<h1>Compare <code>{_esc(comparison.get('baseline_run'))}</code> → "
        f"<code>{_esc(comparison.get('candidate_run'))}</code></h1>"
    )
    rows = ""
    for row in comparison.get("rows", []):
        cls = "reg" if row.get("regressed") is True else ("imp" if row.get("regressed") is False else "")
        verdict = "⚠️ regressed" if row.get("regressed") is True else (
            "✅ improved/flat" if row.get("regressed") is False else "—")
        rows += (
            f"<tr class='{cls}'><td>{_esc(row['scenario'])}</td><td>{_fmt(row.get('primary_metric'))}</td>"
            f"<td>{_fmt(row.get('baseline_mean'))}</td><td>{_fmt(row.get('candidate_mean'))}</td>"
            f"<td>{_fmt(row.get('delta'))}</td><td>{verdict}</td></tr>"
        )
    table = (
        "<table><tr><th>scenario</th><th>metric</th><th>baseline</th><th>candidate</th><th>Δ</th>"
        "<th>verdict</th></tr>" + rows + "</table>"
    )
    regressions = comparison.get("regressions") or []
    note = f"<p><b>Regressions:</b> {_esc(', '.join(regressions)) if regressions else 'none'}</p>"
    return _page("Compare runs", head + table + note)
