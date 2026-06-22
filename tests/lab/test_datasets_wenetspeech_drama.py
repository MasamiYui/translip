"""WenetSpeech-Drama adapter: manifest parsing, drama filter, sidecar SRT wiring.

These tests fabricate a tiny on-disk layout that matches the schema documented in
``translip_lab/datasets/wenetspeech_drama.py`` so we exercise every branch (sidecar
SRT, inline text → derived SRT, drama-only filter, max_samples cap, missing
manifest, malformed JSON) without requiring the real WenetSpeech corpus (which
is EULA-gated and multi-TB).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from translip_lab.config import LabConfig
from translip_lab.datasets import available_datasets, get_dataset
from translip_lab.datasets.wenetspeech_drama import WenetSpeechDramaDataset


def _cfg(tmp_path: Path) -> LabConfig:
    return LabConfig(home=tmp_path, datasets_dir=tmp_path / "d", runs_dir=tmp_path / "r",
                     cache_dir=tmp_path / "c", translip_cmd=("x",), python_cmd=("y",))


def _layout(cfg: LabConfig, subset: str = "mini") -> Path:
    sub = cfg.datasets_dir / "wenetspeech-drama" / subset
    (sub / "audio").mkdir(parents=True)
    (sub / "srt").mkdir(parents=True)
    return sub


def _write_audio(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"RIFF0000WAVEfmt ")  # contents don't matter for the adapter


def test_registered_in_global_registry():
    assert "wenetspeech-drama" in available_datasets()


def test_normalize_picks_drama_segments_with_sidecar_srt(tmp_path):
    cfg = _cfg(tmp_path)
    sub = _layout(cfg)
    _write_audio(sub / "audio" / "S0001.wav")
    _write_audio(sub / "audio" / "S0002.wav")  # podcast, must be filtered out
    (sub / "srt" / "S0001.srt").write_text(
        "1\n00:00:00,000 --> 00:00:02,000\n你好世界\n", encoding="utf-8")
    (sub / "srt" / "S0002.srt").write_text(
        "1\n00:00:00,000 --> 00:00:01,000\n播客\n", encoding="utf-8")
    (sub / "manifest.json").write_text(json.dumps({
        "dataset": "wenetspeech-drama", "subset": "mini",
        "license": "WeNet Open Source — research only",
        "source": "https://wenet.org.cn/WenetSpeech/",
        "segments": [
            {"segment_id": "S0001", "audio": "audio/S0001.wav",
             "srt": "srt/S0001.srt", "duration_sec": 2.0,
             "show_id": "Y0001", "subsets": ["D"], "confidence": 1.0},
            {"segment_id": "S0002", "audio": "audio/S0002.wav",
             "srt": "srt/S0002.srt", "duration_sec": 1.0,
             "show_id": "Y0002", "subsets": ["P"], "confidence": 1.0},
        ],
    }), encoding="utf-8")

    manifest = get_dataset("wenetspeech-drama", cfg, {"subset": "mini"}).normalize()
    assert manifest.dataset == "wenetspeech-drama"
    assert manifest.meta["drama_only"] is True
    assert len(manifest) == 1
    sample = manifest.samples[0]
    assert sample.sample_id == "S0001"
    assert sample.media_path.name == "S0001.wav"
    assert sample.ground_truth.transcript_srt is not None
    assert sample.ground_truth.transcript_srt.name == "S0001.srt"
    assert sample.meta["lang"] == "zh"
    assert sample.meta["subset"] == "mini"
    assert sample.meta["show_id"] == "Y0001"
    assert sample.meta["subsets"] == ["D"]


def test_inline_text_materializes_single_cue_srt(tmp_path):
    cfg = _cfg(tmp_path)
    sub = _layout(cfg)
    _write_audio(sub / "audio" / "S0003.wav")
    (sub / "manifest.json").write_text(json.dumps({
        "segments": [
            {"segment_id": "S0003", "audio": "audio/S0003.wav",
             "text": "今天天气真好", "duration_sec": 1.5, "subsets": ["D"]},
        ],
    }), encoding="utf-8")

    manifest = WenetSpeechDramaDataset(cfg, subset="mini").normalize()
    assert len(manifest) == 1
    srt = manifest.samples[0].ground_truth.transcript_srt
    assert srt is not None and srt.is_file()
    body = srt.read_text(encoding="utf-8")
    assert "今天天气真好" in body
    assert "00:00:00,000 --> 00:00:01,500" in body
    # The derived SRT lives in the lab cache, not next to user data.
    assert str(srt).startswith(str(cfg.cache_dir))


def test_segments_without_reference_text_are_skipped(tmp_path):
    cfg = _cfg(tmp_path)
    sub = _layout(cfg)
    _write_audio(sub / "audio" / "S0004.wav")
    (sub / "manifest.json").write_text(json.dumps({
        "segments": [
            {"segment_id": "S0004", "audio": "audio/S0004.wav", "subsets": ["D"]},
        ],
    }), encoding="utf-8")
    assert WenetSpeechDramaDataset(cfg, subset="mini").normalize().samples == []


def test_max_samples_caps_normalize(tmp_path):
    cfg = _cfg(tmp_path)
    sub = _layout(cfg)
    segs = []
    for i in range(4):
        sid = f"S{i:04d}"
        _write_audio(sub / "audio" / f"{sid}.wav")
        (sub / "srt" / f"{sid}.srt").write_text(
            f"1\n00:00:00,000 --> 00:00:01,000\n台词{i}\n", encoding="utf-8")
        segs.append({"segment_id": sid, "audio": f"audio/{sid}.wav",
                     "srt": f"srt/{sid}.srt", "duration_sec": 1.0, "subsets": ["D"]})
    (sub / "manifest.json").write_text(json.dumps({"segments": segs}), encoding="utf-8")

    manifest = WenetSpeechDramaDataset(cfg, subset="mini", max_samples=2).normalize()
    assert [s.sample_id for s in manifest.samples] == ["S0000", "S0001"]


def test_require_drama_tag_false_keeps_all_subsets(tmp_path):
    cfg = _cfg(tmp_path)
    sub = _layout(cfg)
    _write_audio(sub / "audio" / "P0001.wav")
    (sub / "srt" / "P0001.srt").write_text(
        "1\n00:00:00,000 --> 00:00:01,000\n播客内容\n", encoding="utf-8")
    (sub / "manifest.json").write_text(json.dumps({
        "segments": [
            {"segment_id": "P0001", "audio": "audio/P0001.wav",
             "srt": "srt/P0001.srt", "duration_sec": 1.0, "subsets": ["P"]},
        ],
    }), encoding="utf-8")

    ds = WenetSpeechDramaDataset(cfg, subset="mini", require_drama_tag=False)
    manifest = ds.normalize()
    assert len(manifest) == 1
    assert manifest.meta["drama_only"] is False


def test_missing_subset_root_raises(tmp_path):
    cfg = _cfg(tmp_path)
    with pytest.raises(FileNotFoundError) as exc:
        WenetSpeechDramaDataset(cfg, subset="missing").normalize()
    assert "wenetspeech-drama" in str(exc.value)
    assert "wenet.org.cn" in str(exc.value)


def test_missing_manifest_raises(tmp_path):
    cfg = _cfg(tmp_path)
    _layout(cfg, "mini")  # subset dir exists but no manifest.json
    with pytest.raises(FileNotFoundError) as exc:
        WenetSpeechDramaDataset(cfg, subset="mini").normalize()
    assert "manifest" in str(exc.value)


def test_invalid_json_raises_valueerror(tmp_path):
    cfg = _cfg(tmp_path)
    sub = _layout(cfg)
    (sub / "manifest.json").write_text("{not valid json", encoding="utf-8")
    with pytest.raises(ValueError):
        WenetSpeechDramaDataset(cfg, subset="mini").normalize()


def test_describe_exposes_license_and_layout(tmp_path):
    cfg = _cfg(tmp_path)
    info = WenetSpeechDramaDataset(cfg, subset="mini").describe()
    assert info["name"] == "wenetspeech-drama"
    assert info["subset"] == "mini"
    assert "wenet.org.cn" in info["license"]
    assert "manifest.json" in info["expected_layout"]
    assert "asr (CER)" in info["provides"]
