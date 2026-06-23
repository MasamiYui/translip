"""tts-clone scenario scoring: SIM + CER over fabricated stage outputs (fully offline).

No TTS model and no real audio: a fake StageResult supplies the synth path + a
transcript, and the ECAPA embedder is monkeypatched to a pure-numpy stand-in, so
the whole score path (timbre SIM + intelligibility CER) is exercised deterministically.
"""
from __future__ import annotations

import json

import numpy as np

import translip_lab.metrics.speaker as speaker_mod
import translip_lab.scenarios  # noqa: F401 — registers scenarios
from translip_lab.core.invoke import StageResult
from translip_lab.core.sample import GroundTruth, Sample
from translip_lab.core.scenario import SCENARIO_REGISTRY
from translip_lab.scenarios.tts_clone import TtsCloneScenario


def _stage(outputs):
    return StageResult(argv=[], returncode=0, stdout="", stderr="", duration_sec=0.0, outputs=outputs)


def _write_segments(path, text):
    path.write_text(json.dumps({"segments": [{"start": 0.0, "end": 2.0, "text": text}]}), encoding="utf-8")


def test_tts_clone_registered():
    assert "tts-clone" in SCENARIO_REGISTRY


def test_tts_clone_skips_without_target_text(tmp_path):
    sample = Sample("s", tmp_path / "prompt.wav", GroundTruth())  # no clone_text
    res = TtsCloneScenario().run(sample, tmp_path / "w", None, config={})
    assert res.status == "skipped" and "clone_text" in (res.error or "")


def test_tts_clone_perfect_vs_degraded(tmp_path, monkeypatch):
    import soundfile as sf

    prompt = tmp_path / "prompt.wav"
    synth_good = tmp_path / "synth_good.wav"
    synth_bad = tmp_path / "synth_bad.wav"
    for path in (prompt, synth_good, synth_bad):
        sf.write(path, np.zeros(1600, dtype=np.float32), 16000)

    target = "你好世界今天天气很好"
    sample = Sample("s", prompt, GroundTruth(clone_text=target, clone_ref_wav=prompt))
    scen = TtsCloneScenario()

    # Inject a pure-numpy embedder: prompt + good = same speaker, bad = different.
    emb = {
        str(prompt): np.array([1.0, 0.0, 0.0]),
        str(synth_good): np.array([1.0, 0.0, 0.0]),
        str(synth_bad): np.array([0.0, 1.0, 0.0]),
    }
    monkeypatch.setattr(speaker_mod, "_ecapa_embedder", lambda device="auto": (lambda p: emb[str(p)]))

    seg_good = tmp_path / "good.segments.json"
    _write_segments(seg_good, target)  # transcript == target
    good = scen.score(sample, tmp_path, _stage({"synth_wav": str(synth_good), "segments": str(seg_good)}), {})
    assert good["cer"] < 0.01 and good["sim"] > 0.99 and good["intelligibility"] > 0.99

    seg_bad = tmp_path / "bad.segments.json"
    _write_segments(seg_bad, "完全不同的内容啊啊啊")  # garbled transcript
    bad = scen.score(sample, tmp_path, _stage({"synth_wav": str(synth_bad), "segments": str(seg_bad)}), {})
    assert bad["cer"] > good["cer"] and bad["sim"] < good["sim"]


def test_tts_clone_corpus_metrics():
    rows = [
        {"cer": 0.0, "reference_char_count": 10, "sim": 0.9},
        {"cer": 0.2, "reference_char_count": 10, "sim": 0.7},
    ]
    corpus = TtsCloneScenario().corpus_metrics(rows)
    assert abs(corpus["cer_micro"] - 0.1) < 1e-9  # pooled: (0*10 + 0.2*10) / 20
    assert abs(corpus["sim_mean"] - 0.8) < 1e-9
