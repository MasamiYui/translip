"""Aggregation + run-to-run comparison (regression detection)."""
from __future__ import annotations

from translip_lab.core.run_store import compare_runs, summarize_aggregates
from translip_lab.core.scenario import ScenarioResult


def test_aggregates_mean_and_counts():
    results = [
        ScenarioResult("s1", "asr", "succeeded", {"cer": 0.1}, 0.1),
        ScenarioResult("s2", "asr", "succeeded", {"cer": 0.3}, 0.3),
        ScenarioResult("s3", "asr", "failed"),
        ScenarioResult("s4", "asr", "skipped"),
    ]
    agg = summarize_aggregates(results, {"asr": {"primary_metric_key": "cer", "higher_is_better": False}})
    assert agg["asr"]["mean"] == 0.2
    assert agg["asr"]["succeeded"] == 2
    assert agg["asr"]["failed"] == 1
    assert agg["asr"]["skipped"] == 1
    assert agg["asr"]["scored"] == 2


def test_compare_regression_lower_is_better():
    base = {"run_id": "a", "aggregates": {"asr": {"primary_metric": "cer", "higher_is_better": False, "mean": 0.2}}}
    cand = {"run_id": "b", "aggregates": {"asr": {"primary_metric": "cer", "higher_is_better": False, "mean": 0.3}}}
    cmp = compare_runs(base, cand)
    row = cmp["rows"][0]
    assert row["delta"] == 0.1
    assert row["regressed"] is True
    assert cmp["regressions"] == ["asr"]


def test_compare_improvement_higher_is_better():
    base = {"run_id": "a", "aggregates": {"sep": {"primary_metric": "si_sdr", "higher_is_better": True, "mean": 8.0}}}
    cand = {"run_id": "b", "aggregates": {"sep": {"primary_metric": "si_sdr", "higher_is_better": True, "mean": 9.5}}}
    cmp = compare_runs(base, cand)
    assert cmp["rows"][0]["regressed"] is False
    assert cmp["regressions"] == []
