"""Generic folder dataset: media + sidecar GT wiring."""
from __future__ import annotations

from pathlib import Path

from translip_lab.config import LabConfig
from translip_lab.datasets.folder import FolderDataset


def _cfg(tmp_path: Path) -> LabConfig:
    return LabConfig(home=tmp_path, datasets_dir=tmp_path / "d", runs_dir=tmp_path / "r",
                     cache_dir=tmp_path / "c", translip_cmd=("x",), python_cmd=("y",))


def test_folder_wires_sidecar_ground_truth(tmp_path):
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "a.mp4").write_bytes(b"x")
    (root / "a.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\n你好\n", encoding="utf-8")
    (root / "a.rttm").write_text("SPEAKER a 1 0.0 1.0 <NA> <NA> s1 <NA> <NA>\n", encoding="utf-8")
    (root / "a.boxes.json").write_text("{}", encoding="utf-8")
    (root / "a.clean.mp4").write_bytes(b"x")
    (root / "b.wav").write_bytes(b"x")
    (root / "b.voice.wav").write_bytes(b"x")
    (root / "b.background.wav").write_bytes(b"x")

    ds = FolderDataset(_cfg(tmp_path), root=str(root))
    manifest = ds.normalize()
    by_id = {s.sample_id: s for s in manifest.samples}

    # a.mp4 picks up srt/rttm/boxes/clean; the .clean.mp4 is NOT its own sample
    assert "a" in by_id and "a.clean" not in by_id
    a = by_id["a"]
    assert a.ground_truth.transcript_srt and a.ground_truth.rttm
    assert a.ground_truth.subtitle_boxes and a.ground_truth.clean_video

    # b.wav picks up voice/background stems; those are not standalone samples
    assert "b" in by_id and "b.voice" not in by_id and "b.background" not in by_id
    assert by_id["b"].ground_truth.clean_stems["voice"].endswith("b.voice.wav")


def test_folder_missing_root_raises(tmp_path):
    ds = FolderDataset(_cfg(tmp_path), root=str(tmp_path / "nope"))
    try:
        ds.normalize()
    except FileNotFoundError:
        return
    raise AssertionError("expected FileNotFoundError for missing root")
