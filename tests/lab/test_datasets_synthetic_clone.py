"""synthetic-clone generator: deterministic (reference voice, target text) cases."""
from __future__ import annotations

import numpy as np
import soundfile as sf

from translip_lab.config import load_config
from translip_lab.datasets.synthetic_clone import (
    SyntheticCloneDataset,
    generate_clone_case,
    synth_voice,
)


def test_synth_voice_deterministic_and_speaker_separable():
    a1 = synth_voice(0, duration=1.0, sr=16000)
    a2 = synth_voice(0, duration=1.0, sr=16000)
    b = synth_voice(3, duration=1.0, sr=16000)
    assert np.array_equal(a1, a2)  # same seed → identical waveform
    # same-speaker pair is closer than a different-speaker pair
    assert np.mean((a1 - a2) ** 2) < np.mean((a1 - b[: len(a1)]) ** 2)


def test_generate_clone_case_writes_prompt_and_text(tmp_path):
    case = generate_clone_case(tmp_path / "c0", index=0, speaker_seed=0, duration=1.0)
    assert case["prompt"].is_file()
    data, sr = sf.read(case["prompt"])
    assert sr == 16000 and len(data) > 0
    assert isinstance(case["text"], str) and case["text"]


def test_dataset_normalize_builds_clone_gt(tmp_path, monkeypatch):
    monkeypatch.setenv("TRANSLIP_LAB_HOME", str(tmp_path))
    cfg = load_config()
    manifest = SyntheticCloneDataset(cfg, clips=2, duration=1.0).normalize()
    assert manifest.dataset == "synthetic-clone" and len(manifest) == 2
    sample = manifest.samples[0]
    assert sample.media_path.is_file()
    assert sample.ground_truth.clone_text  # target text present
    assert sample.ground_truth.clone_ref_wav == sample.media_path  # prompt is the SIM anchor
    # round-trips through the JSON-serializable form the runner persists
    gt = sample.ground_truth.to_dict()
    assert gt["clone_text"] and gt["clone_ref_wav"]
