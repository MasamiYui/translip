"""MagicData-RAMC parser + adapter: [start,end] speaker gender,dialect text → RTTM/SRT.

The corpus can't be downloaded here, so these tests pin the *parsing logic* against a
fixture in the published RAMC transcript format. The parser is the one risk surface
(format built from published examples), so it gets the most coverage.
"""
from __future__ import annotations

import numpy as np
import pytest
import soundfile as sf

from translip_lab.config import load_config
from translip_lab.datasets.magicdata_ramc import MagicDataRamcDataset, parse_ramc_transcript
from translip_lab.metrics.diarization import parse_rttm

# Three segments, two speakers, demographic attribute tokens present.
_SAMPLE = (
    "[1.319,6.691] G00000140 女,普通话 你好今天天气很好\n"
    "[7.000,9.500] G00000141 男,四川话 是的我们出去走走吧\n"
    "[10.000,12.000] G00000140 女,普通话 好的那走吧\n"
)


def test_parse_segments_speakers_and_text(tmp_path):
    p = tmp_path / "conv.txt"
    p.write_text(_SAMPLE, encoding="utf-8")
    rows = parse_ramc_transcript(p)
    assert len(rows) == 3
    assert rows[0] == (1.319, 6.691, "G00000140", "你好今天天气很好")
    assert rows[1][2] == "G00000141" and rows[1][3] == "是的我们出去走走吧"
    # the gender,dialect tokens must NOT leak into the reference text
    joined = "".join(r[3] for r in rows)
    assert "普通话" not in joined and "四川话" not in joined


def test_parse_handles_attrs_absent(tmp_path):
    p = tmp_path / "c2.txt"
    p.write_text("[0.0,2.0] C0 你好世界\n", encoding="utf-8")
    assert parse_ramc_transcript(p) == [(0.0, 2.0, "C0", "你好世界")]


def test_parse_tolerates_spaced_brackets(tmp_path):
    # a real-data variant: whitespace inside the [start , end] marker
    p = tmp_path / "c4.txt"
    p.write_text("[ 1.5 , 3.0 ] G9 男,普通话 喂你好\n", encoding="utf-8")
    assert parse_ramc_transcript(p) == [(1.5, 3.0, "G9", "喂你好")]


def test_parse_preserves_comma_text_and_sorts_and_drops_empty(tmp_path):
    p = tmp_path / "c3.txt"
    # out-of-order; a zero-length segment; a text token that contains a comma but is
    # NOT a gender,dialect attribute (must be preserved, not stripped).
    p.write_text(
        "[5.0,6.0] G2 后面说的话\n"
        "[2.0,2.0] G1 空段\n"
        "[1.0,3.0] G1 前面,还有逗号\n",
        encoding="utf-8",
    )
    rows = parse_ramc_transcript(p)
    assert [r[0] for r in rows] == [1.0, 5.0]  # sorted, zero-length dropped
    assert rows[0][3] == "前面,还有逗号"  # comma-bearing text kept intact


def test_adapter_builds_cer_and_der_gt(tmp_path, monkeypatch):
    monkeypatch.setenv("TRANSLIP_LAB_HOME", str(tmp_path))
    cfg = load_config()
    base = cfg.datasets_dir / "magicdata-ramc" / "test"
    base.mkdir(parents=True)
    (base / "conv1.txt").write_text(_SAMPLE, encoding="utf-8")
    (base / "SPKINFO.txt").write_text("C0 G00000140 F ...\n", encoding="utf-8")  # metadata → must be ignored
    sf.write(base / "conv1.wav", np.zeros(1600, dtype=np.float32), 16000)

    manifest = MagicDataRamcDataset(cfg, subset="test").normalize()
    assert manifest.dataset == "magicdata-ramc" and len(manifest) == 1
    sample = manifest.samples[0]
    assert sample.sample_id == "conv1"

    # ASR GT (SRT): text present, attribute tokens stripped
    srt_path = sample.ground_truth.transcript_srt
    assert srt_path and srt_path.is_file()
    srt = srt_path.read_text(encoding="utf-8")
    assert "你好今天天气很好" in srt and "普通话" not in srt

    # diarization GT (RTTM): two speakers, three turns, durations correct
    rttm_path = sample.ground_truth.rttm
    assert rttm_path and rttm_path.is_file()
    ref = parse_rttm(rttm_path)
    assert len(ref) == 3
    assert {spk for _, _, spk in ref} == {"G00000140", "G00000141"}
    start, end, _ = ref[0]
    assert abs((end - start) - (6.691 - 1.319)) < 1e-3


def test_adapter_missing_subset_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("TRANSLIP_LAB_HOME", str(tmp_path))
    cfg = load_config()
    with pytest.raises(FileNotFoundError):
        MagicDataRamcDataset(cfg, subset="nope").normalize()
