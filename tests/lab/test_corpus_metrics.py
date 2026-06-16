"""Corpus-level (micro) metrics + std/p90 aggregates."""
from __future__ import annotations

from translip_lab.core.run_store import summarize_aggregates
from translip_lab.core.scenario import ScenarioResult
from translip_lab.scenarios.asr import AsrScenario
from translip_lab.scenarios.diarization import DiarizationScenario
from translip_lab.scenarios.ocr_detect import OcrDetectScenario


def test_asr_micro_cer():
    # edits = 0.5*10 + 0.1*90 = 14 over 100 ref chars → micro 0.14
    metrics = [{"cer": 0.5, "reference_char_count": 10}, {"cer": 0.1, "reference_char_count": 90}]
    out = AsrScenario().corpus_metrics(metrics)
    assert abs(out["cer_micro"] - 0.14) < 1e-9
    assert out["reference_char_total"] == 100


def test_diarization_micro_der():
    metrics = [
        {"miss": 1.0, "false_alarm": 0.0, "confusion": 0.0, "ref_speech_sec": 10.0},
        {"miss": 0.0, "false_alarm": 2.0, "confusion": 0.0, "ref_speech_sec": 10.0},
    ]
    out = DiarizationScenario().corpus_metrics(metrics)
    assert abs(out["der_micro"] - 0.15) < 1e-9  # (1+2)/20


def test_ocr_micro_f1():
    metrics = [{"tp": 3, "fp": 1, "fn": 1}, {"tp": 1, "fp": 0, "fn": 1}]  # tp4 fp1 fn2
    out = OcrDetectScenario().corpus_metrics(metrics)
    assert out["precision_micro"] == 0.8
    assert abs(out["recall_micro"] - 0.6667) < 1e-3


def test_summarize_adds_std_and_p90():
    rows = [ScenarioResult("s1", "asr", "succeeded", {"cer": 0.1}, 0.1),
            ScenarioResult("s2", "asr", "succeeded", {"cer": 0.3}, 0.3),
            ScenarioResult("s3", "asr", "succeeded", {"cer": 0.5}, 0.5)]
    agg = summarize_aggregates(rows, {"asr": {"primary_metric_key": "cer", "higher_is_better": False}})["asr"]
    assert abs(agg["mean"] - 0.3) < 1e-9
    assert "std" in agg and agg["std"] > 0
    assert "p90" in agg
