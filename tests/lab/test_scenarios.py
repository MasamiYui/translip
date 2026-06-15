"""Scenario scoring logic, exercised directly with fixtures (no ML, no real stages)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from translip_lab.core.invoke import StageResult
from translip_lab.core.sample import GroundTruth, Sample
from translip_lab.core.scenario import SCENARIO_REGISTRY
import translip_lab.scenarios  # noqa: F401 — registers scenarios
from translip_lab.scenarios.diarization import DiarizationScenario
from translip_lab.scenarios.ocr_detect import OcrDetectScenario
from translip_lab.scenarios.separation import SeparationScenario


def _stage(outputs=None):
    return StageResult(argv=[], returncode=0, stdout="", stderr="", duration_sec=0.0, outputs=outputs or {})


def test_all_scenarios_registered():
    for name in ("asr", "diarization", "separation", "ocr-detect", "subtitle-erase", "e2e-dub"):
        assert name in SCENARIO_REGISTRY


def test_ocr_detect_score_perfect_and_miss(tmp_path):
    work = tmp_path / "work"
    (work / "ocr-detect").mkdir(parents=True)
    box = [40, 110, 200, 150]
    (work / "ocr-detect" / "detection.json").write_text(
        json.dumps({"events": [{"start_time": 0.2, "end_time": 1.0, "box": box, "text": "x"}]}), encoding="utf-8")
    gt_path = tmp_path / "gt.boxes.json"
    gt_path.write_text(json.dumps({"events": [{"start": 0.2, "end": 1.0, "box": box, "text": "x"}]}), encoding="utf-8")
    sample = Sample("s", tmp_path / "v.mp4", GroundTruth(subtitle_boxes=gt_path))

    perfect = OcrDetectScenario().score(sample, work, _stage(), {})
    assert perfect["f1"] == 1.0

    # move the prediction far away → no match
    (work / "ocr-detect" / "detection.json").write_text(
        json.dumps({"events": [{"start_time": 0.2, "end_time": 1.0, "box": [500, 500, 560, 540], "text": "x"}]}),
        encoding="utf-8")
    miss = OcrDetectScenario().score(sample, work, _stage(), {})
    assert miss["f1"] == 0.0


def test_diarization_score_from_segments(tmp_path):
    seg = tmp_path / "segments.json"
    seg.write_text(json.dumps({"segments": [
        {"start": 0.0, "end": 1.0, "speaker_label": "SPEAKER_00"},
        {"start": 1.0, "end": 2.0, "speaker_label": "SPEAKER_01"},
    ]}), encoding="utf-8")
    rttm = tmp_path / "ref.rttm"
    rttm.write_text(
        "SPEAKER f 1 0.0 1.0 <NA> <NA> A <NA> <NA>\nSPEAKER f 1 1.0 1.0 <NA> <NA> B <NA> <NA>\n", encoding="utf-8")
    sample = Sample("s", tmp_path / "v.wav", GroundTruth(rttm=rttm))
    out = DiarizationScenario().score(sample, tmp_path, _stage({"segments": str(seg)}), {})
    assert out["der"] < 0.05


def test_separation_score_si_sdr(tmp_path):
    import soundfile as sf

    rng = np.random.default_rng(0)
    voice = rng.standard_normal(8000).astype(np.float32)
    gt_voice = tmp_path / "gt_voice.wav"
    out_voice = tmp_path / "out_voice.wav"
    sf.write(gt_voice, voice, 8000)
    sf.write(out_voice, voice, 8000)  # perfect separation
    sample = Sample("s", tmp_path / "mix.wav", GroundTruth(clean_stems={"voice": str(gt_voice)}))
    out = SeparationScenario().score(sample, tmp_path, _stage({"voice": str(out_voice)}), {})
    assert out["si_sdr"] >= 100.0


def test_asr_score_uses_translip_scorer(tmp_path):
    seg = tmp_path / "segments.zh.json"
    seg.write_text(json.dumps({"segments": [{"id": "seg-0001", "start": 0.0, "end": 1.0, "text": "你好世界"}]}),
                   encoding="utf-8")
    srt = tmp_path / "ref.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\n你好世界\n", encoding="utf-8")
    sample = Sample("s", tmp_path / "a.wav", GroundTruth(transcript_srt=srt))
    from translip_lab.scenarios.asr import AsrScenario

    out = AsrScenario().score(sample, tmp_path, _stage({"segments": str(seg)}), {})
    assert "cer" in out
    assert out["cer"] < 0.5
