from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from translip.quality import dub_embeddings


def test_enrich_skips_when_speaker_module_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """If the SpeechBrain stack isn't importable, enrichment must degrade gracefully."""
    fake_module = types.ModuleType("translip.speaker_embedding_blocked")

    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def boom(name: str, *args: Any, **kwargs: Any):
        if name.endswith("speaker_embedding"):
            raise RuntimeError("torch missing in test env")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", boom)

    report: dict[str, Any] = {
        "segments": [
            {"segment_id": "s1", "speaker_id": "A", "dub_audio_path": "missing.wav"}
        ],
    }
    out = dub_embeddings.enrich_report_with_embeddings(report, pipeline_root=tmp_path)
    assert out is report
    assert out["embedding_meta"]["status"] == "unavailable"
    assert "torch missing" in out["embedding_meta"]["reason"]
    # Segment must not have grown a speaker_embedding from a failed run.
    assert "speaker_embedding" not in out["segments"][0]
    # Reference to fake_module to keep linters happy that we constructed it.
    assert isinstance(fake_module, types.ModuleType)


def test_enrich_skips_segments_with_missing_audio(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """When audio files don't exist, the report records skipped_count instead of raising."""
    fake = types.ModuleType("translip.speaker_embedding")

    def embedding_for_clip(_classifier: Any, _waveform: Any, _sr: Any) -> Any:  # pragma: no cover - never called
        raise AssertionError("should not be invoked when files are missing")

    def load_speechbrain_classifier(_device: str) -> Any:
        return object()

    def read_audio_mono(_path: Any) -> Any:  # pragma: no cover - never called
        raise AssertionError("should not be invoked when files are missing")

    def resolve_speaker_device(d: str) -> str:
        return d or "cpu"

    fake.embedding_for_clip = embedding_for_clip  # type: ignore[attr-defined]
    fake.load_speechbrain_classifier = load_speechbrain_classifier  # type: ignore[attr-defined]
    fake.read_audio_mono = read_audio_mono  # type: ignore[attr-defined]
    fake.resolve_speaker_device = resolve_speaker_device  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "translip.speaker_embedding", fake)

    report: dict[str, Any] = {
        "segments": [
            {"segment_id": "s1", "speaker_id": "A", "dub_audio_path": "nope_a.wav"},
            {"segment_id": "s2", "speaker_id": "B", "dub_audio_path": None},
        ],
    }
    out = dub_embeddings.enrich_report_with_embeddings(report, pipeline_root=tmp_path)
    assert out["embedding_meta"]["status"] == "empty"
    assert out["embedding_meta"]["skipped_count"] >= 1
    assert "speaker_embedding" not in out["segments"][0]
    assert "speaker_embedding" not in out["segments"][1]
    assert out["reference_embeddings"] == {}


def test_enrich_round_trips_through_disk(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A synthetic backend lets us exercise the on-disk read/write path end-to-end."""
    fake = types.ModuleType("translip.speaker_embedding")

    def embedding_for_clip(_classifier: Any, waveform: Any, _sr: Any) -> Any:
        # Embedding = first-byte signature of the synthetic waveform; lets us
        # assert that ref vs dub embeddings come out distinct.
        marker = float(waveform[0])
        return [marker, marker + 1.0, marker - 1.0]

    def load_speechbrain_classifier(_device: str) -> Any:
        return object()

    def read_audio_mono(path: Any) -> Any:
        # Use the file's first byte as the waveform's first sample.
        data = Path(path).read_bytes()
        return ([float(data[0])], 16000)

    def resolve_speaker_device(d: str) -> str:
        return d or "cpu"

    fake.embedding_for_clip = embedding_for_clip  # type: ignore[attr-defined]
    fake.load_speechbrain_classifier = load_speechbrain_classifier  # type: ignore[attr-defined]
    fake.read_audio_mono = read_audio_mono  # type: ignore[attr-defined]
    fake.resolve_speaker_device = resolve_speaker_device  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "translip.speaker_embedding", fake)

    # Layout: pipeline_root/dub.wav and pipeline_root/ref.wav
    (tmp_path / "dub.wav").write_bytes(b"\x05" + b"\x00" * 7)
    (tmp_path / "ref.wav").write_bytes(b"\x07" + b"\x00" * 7)

    report = {
        "segments": [
            {
                "segment_id": "s1",
                "speaker_id": "A",
                "dub_audio_path": "dub.wav",
                "reference_audio_path": "ref.wav",
            },
        ],
    }
    report_path = tmp_path / "dub_qa_report.en.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")

    enriched = dub_embeddings.enrich_report_path(report_path, pipeline_root=tmp_path)
    assert enriched["embedding_meta"]["status"] == "ok"
    assert enriched["embedding_meta"]["enriched_count"] == 1
    assert enriched["embedding_meta"]["embedding_dim"] == 3
    assert enriched["segments"][0]["speaker_embedding"] == [5.0, 6.0, 4.0]
    assert enriched["reference_embeddings"]["A"] == [7.0, 8.0, 6.0]

    # And a re-run is idempotent: enriched_count stays at 1, no new work.
    second = dub_embeddings.enrich_report_path(report_path, pipeline_root=tmp_path)
    assert second["embedding_meta"]["enriched_count"] == 1
    assert second["segments"][0]["speaker_embedding"] == [5.0, 6.0, 4.0]
