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
