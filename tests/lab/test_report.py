"""Report rendering (markdown + HTML, run + compare)."""
from __future__ import annotations

from translip_lab.report import compare_to_html, compare_to_markdown, run_to_html, run_to_markdown


def _manifest():
    return {
        "run_id": "r1", "suite": "s", "dataset": "d", "sample_count": 1, "elapsed_sec": 1.2,
        "started_at": "2026-06-15T10:00:00",
        "aggregates": {"asr": {"primary_metric": "cer", "higher_is_better": False,
                               "mean": 0.2, "median": 0.2, "min": 0.1, "max": 0.3,
                               "scored": 1, "failed": 0, "skipped": 0}},
        "results": [{"sample_id": "s1", "scenario": "asr", "status": "succeeded",
                     "primary_metric": 0.2, "cached": False}],
    }


def _comparison():
    return {"baseline_run": "a", "candidate_run": "b",
            "rows": [{"scenario": "asr", "primary_metric": "cer", "higher_is_better": False,
                      "baseline_mean": 0.2, "candidate_mean": 0.3, "delta": 0.1, "regressed": True}],
            "regressions": ["asr"]}


def test_run_markdown_and_html():
    md = run_to_markdown(_manifest())
    assert "asr" in md and "cer" in md and "s1" in md
    html = run_to_html(_manifest())
    assert "<table" in html and "asr" in html


def test_compare_markdown_and_html():
    md = compare_to_markdown(_comparison())
    assert "regressed" in md and "asr" in md
    html = compare_to_html(_comparison())
    assert "reg" in html  # regressed rows get the .reg class
