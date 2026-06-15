"""Synthetic GT generators (real ffmpeg on tiny clips)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from translip_lab.config import LabConfig
from translip_lab.core.media import load_audio, probe_video
from translip_lab.datasets.synthetic_mix import SyntheticMixDataset
from translip_lab.datasets.synthetic_subtitle import SyntheticSubtitleDataset, find_font
from translip_lab.metrics.audio import si_sdr
from translip_lab.metrics.detection import match_boxes, prf


def _cfg(tmp_path: Path) -> LabConfig:
    return LabConfig(home=tmp_path, datasets_dir=tmp_path / "d", runs_dir=tmp_path / "r",
                     cache_dir=tmp_path / "c", translip_cmd=("x",), python_cmd=("y",))


@pytest.mark.skipif(find_font() is None, reason="no CJK/usable font for drawtext")
def test_synthetic_subtitle_produces_box_and_clean_gt(tmp_path):
    ds = SyntheticSubtitleDataset(_cfg(tmp_path), clips=1, duration=2.0, fps=4, width=320, height=180)
    manifest = ds.normalize()
    assert len(manifest) == 1
    sample = manifest.samples[0]
    assert sample.media_path.is_file()
    assert sample.ground_truth.clean_video.is_file()
    assert sample.ground_truth.subtitle_boxes.is_file()

    data = json.loads(sample.ground_truth.subtitle_boxes.read_text(encoding="utf-8"))
    assert len(data["events"]) >= 1
    for ev in data["events"]:
        x1, y1, x2, y2 = ev["box"]
        assert 0 <= x1 < x2 <= 320 and 0 <= y1 < y2 <= 180

    # the GT box set must self-match perfectly through the detection metric
    boxes = [ev["box"] for ev in data["events"]]
    m = match_boxes(boxes, boxes)
    assert prf(m["tp"], m["fp"], m["fn"])["f1"] == 1.0

    info = probe_video(sample.media_path)
    assert info.width == 320 and info.height == 180


def test_synthetic_mix_produces_stems(tmp_path):
    ds = SyntheticMixDataset(_cfg(tmp_path), clips=1, duration=1.0, sr=8000)
    manifest = ds.normalize()
    sample = manifest.samples[0]
    assert sample.media_path.is_file()
    voice_path = sample.ground_truth.clean_stems["voice"]
    assert Path(voice_path).is_file()

    voice, sr = load_audio(voice_path)
    assert sr == 8000 and voice.size > 0
    assert si_sdr(voice, voice) >= 100.0  # real audio round-trips
