"""clip dataset: media + GT (srt/rttm/stems) trimmed and shifted to a window."""
from __future__ import annotations

import numpy as np

from translip_lab.config import LabConfig
from translip_lab.core.media import load_audio
from translip_lab.datasets.base import get_dataset
from translip_lab.datasets.clip import _parse_srt
from translip_lab.metrics.diarization import parse_rttm


def _cfg(tmp_path):
    return LabConfig(home=tmp_path, datasets_dir=tmp_path / "d", runs_dir=tmp_path / "r",
                     cache_dir=tmp_path / "c", translip_cmd=("x",), python_cmd=("y",))


def test_clip_audio_and_stems(tmp_path):
    ds = get_dataset("clip", _cfg(tmp_path), {
        "base": "synthetic-mix", "seconds": 1.0, "sr": 8000,
        "base_params": {"clips": 1, "duration": 3.0, "sr": 8000},
    })
    sample = ds.normalize().samples[0]
    media, sr = load_audio(sample.media_path)
    assert sr == 8000 and 0.8 < len(media) / sr < 1.2  # ~1s
    voice, _ = load_audio(sample.ground_truth.clean_stems["voice"])
    assert 0.8 < len(voice) / 8000 < 1.2


def test_clip_folder_srt_rttm_shift(tmp_path):
    import soundfile as sf

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    sf.write(corpus / "a.wav", np.zeros(8000 * 4, dtype=np.float32), 8000)  # 4s
    (corpus / "a.srt").write_text(
        "1\n00:00:00,500 --> 00:00:01,500\nhello\n\n2\n00:00:02,500 --> 00:00:03,500\nworld\n", encoding="utf-8")
    (corpus / "a.rttm").write_text(
        "SPEAKER a 1 0.5 1.0 <NA> <NA> A <NA> <NA>\nSPEAKER a 1 2.5 1.0 <NA> <NA> B <NA> <NA>\n", encoding="utf-8")

    ds = get_dataset("clip", _cfg(tmp_path), {
        "base": "folder", "seconds": 2.0, "offset": 1.0, "sr": 8000,
        "base_params": {"root": str(corpus)},
    })
    sample = ds.normalize().samples[0]

    # window [1,3]: A(0.5-1.5)→[0,0.5]; B(2.5-3.5)→[1.5,2.0]
    segs = parse_rttm(sample.ground_truth.rttm)
    assert len(segs) == 2
    assert abs(segs[0][0] - 0.0) < 0.02 and abs(segs[0][1] - 0.5) < 0.02
    assert abs(segs[1][0] - 1.5) < 0.02 and abs(segs[1][1] - 2.0) < 0.02

    items = _parse_srt(sample.ground_truth.transcript_srt)
    assert len(items) == 2 and abs(items[0][0] - 0.0) < 0.02
