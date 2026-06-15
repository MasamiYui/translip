"""Frame-based DER unit tests (hand-computed expectations)."""
from __future__ import annotations

from translip_lab.metrics.diarization import der, parse_rttm


def test_der_perfect_match_is_zero():
    out = der([(0.0, 1.0, "A")], [(0.0, 1.0, "X")])
    assert abs(out["der"]) < 1e-9


def test_der_half_missed():
    # hypothesis covers only the first half of A's speech → 0.5 missed
    out = der([(0.0, 1.0, "A")], [(0.0, 0.5, "X")])
    assert abs(out["der"] - 0.5) < 0.02
    assert out["miss"] > out["false_alarm"]


def test_der_all_missed_when_no_hypothesis():
    out = der([(0.0, 1.0, "A")], [])
    assert abs(out["der"] - 1.0) < 0.02


def test_der_merged_speakers_confusion():
    # two reference speakers, one hypothesis speaker spanning both → ~0.5 (half confused)
    out = der([(0.0, 1.0, "A"), (1.0, 2.0, "B")], [(0.0, 2.0, "X")])
    assert abs(out["der"] - 0.5) < 0.02
    assert out["confusion"] > 0.0


def test_parse_rttm_roundtrip(tmp_path):
    rttm = tmp_path / "ref.rttm"
    rttm.write_text(
        "SPEAKER file 1 0.00 1.50 <NA> <NA> spk1 <NA> <NA>\n"
        "SPEAKER file 1 1.50 0.80 <NA> <NA> spk2 <NA> <NA>\n",
        encoding="utf-8",
    )
    segs = parse_rttm(rttm)
    assert segs == [(0.0, 1.5, "spk1"), (1.5, 2.3, "spk2")]
