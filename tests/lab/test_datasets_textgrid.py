"""TextGrid parsing → intervals / RTTM / SRT."""
from __future__ import annotations

from translip_lab.datasets.textgrid import parse_textgrid, to_rttm, to_srt

_TG = """File type = "ooTextFile"
Object class = "TextGrid"
xmin = 0
xmax = 5
tiers? <exists>
size = 2
item []:
    item [1]:
        class = "IntervalTier"
        name = "spkA"
        xmin = 0
        xmax = 5
        intervals: size = 2
        intervals [1]:
            xmin = 0
            xmax = 1.5
            text = "你好"
        intervals [2]:
            xmin = 1.5
            xmax = 2.0
            text = ""
    item [2]:
        class = "IntervalTier"
        name = "spkB"
        xmin = 0
        xmax = 5
        intervals: size = 1
        intervals [1]:
            xmin = 2.0
            xmax = 3.0
            text = "世界"
"""


def test_parse_textgrid(tmp_path):
    path = tmp_path / "x.TextGrid"
    path.write_text(_TG, encoding="utf-8")
    intervals = parse_textgrid(path)
    assert intervals == [(0.0, 1.5, "spkA", "你好"), (2.0, 3.0, "spkB", "世界")]


def test_to_rttm_and_srt(tmp_path):
    path = tmp_path / "x.TextGrid"
    path.write_text(_TG, encoding="utf-8")
    intervals = parse_textgrid(path)
    rttm = to_rttm(intervals, "meeting1")
    assert "SPEAKER meeting1 1 0.000 1.500 <NA> <NA> spkA <NA> <NA>" in rttm
    assert "spkB" in rttm
    srt = to_srt(intervals)
    assert "00:00:00,000 --> 00:00:01,500" in srt
    assert "你好" in srt and "世界" in srt


def test_alimeeting_audio_to_textgrid_stem_mapping(tmp_path):
    # AliMeeting audio R<room>_M<meeting>_MS<id>.wav must resolve R<room>_M<meeting>.TextGrid
    import numpy as np
    import soundfile as sf

    from translip_lab.config import LabConfig
    from translip_lab.datasets.alimeeting import AliMeetingDataset

    base = tmp_path / "datasets" / "alimeeting" / "Eval_Ali" / "Eval_Ali_far"
    (base / "audio_dir").mkdir(parents=True)
    (base / "textgrid_dir").mkdir(parents=True)
    sf.write(base / "audio_dir" / "R1_M1_MS801.wav", np.zeros(8000, dtype=np.float32), 8000)
    (base / "textgrid_dir" / "R1_M1.TextGrid").write_text(_TG, encoding="utf-8")

    cfg = LabConfig(home=tmp_path, datasets_dir=tmp_path / "datasets", runs_dir=tmp_path / "r",
                    cache_dir=tmp_path / "c", translip_cmd=("x",), python_cmd=("y",))
    manifest = AliMeetingDataset(cfg, subset="Eval_Ali/Eval_Ali_far").normalize()
    assert len(manifest) == 1
    sample = manifest.samples[0]
    assert sample.sample_id == "R1_M1_MS801"
    assert sample.ground_truth.rttm is not None
    assert sample.ground_truth.transcript_srt is not None
