from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from translip.quality import dub_pitch


def _write_sine_wav(path: Path, *, freq_hz: float, duration_sec: float, sr: int = 22050) -> None:
    t = np.linspace(0, duration_sec, int(sr * duration_sec), endpoint=False, dtype=np.float32)
    waveform = 0.5 * np.sin(2 * np.pi * freq_hz * t).astype(np.float32)
    sf.write(path, waveform, sr)


def test_extract_pitch_contour_returns_expected_frequency(tmp_path: Path) -> None:
    # 220 Hz = A3 — a friendly, well-inside-the-fmin..fmax band test tone.
    wav_path = tmp_path / "tone.wav"
    _write_sine_wav(wav_path, freq_hz=220.0, duration_sec=1.0)

    waveform, sr = sf.read(wav_path, dtype="float32", always_2d=False)
    contour = dub_pitch.extract_pitch_contour(waveform, sr)

    voiced = [hz for _, hz in contour if hz is not None]
    assert voiced, "pyin should detect the sine tone as voiced"
    median_hz = float(np.median(voiced))
    # Allow a generous +/- 8 Hz tolerance: pyin's quantization step at the
    # configured frame_length leaves a few Hz of jitter.
    assert abs(median_hz - 220.0) < 8.0, f"expected ~220Hz, got {median_hz:.2f}Hz"


def test_enrich_report_handles_no_segments(tmp_path: Path) -> None:
    report = {"segments": []}
    out = dub_pitch.enrich_report_with_pitch(report, pipeline_root=tmp_path)
    assert out["pitch_meta"]["status"] == "no_segments"


def test_enrich_report_marks_empty_when_audio_missing(tmp_path: Path) -> None:
    report = {
        "input": {"original_voice": "missing_original.wav"},
        "segments": [
            {
                "segment_id": "seg1",
                "start": 0.0,
                "end": 1.0,
                "dub_audio_path": "missing_dub.wav",
            }
        ],
    }
    out = dub_pitch.enrich_report_with_pitch(report, pipeline_root=tmp_path)
    assert out["pitch_meta"]["status"] == "empty"
    assert out["pitch_meta"]["enriched_count"] == 0
    assert out["pitch_meta"]["skipped_count"] >= 1
    assert "pitch_contour" not in out["segments"][0]


def test_enrich_report_writes_contours_for_real_audio(tmp_path: Path) -> None:
    original = tmp_path / "original.wav"
    dub = tmp_path / "dub.wav"
    _write_sine_wav(original, freq_hz=220.0, duration_sec=1.5)
    _write_sine_wav(dub, freq_hz=330.0, duration_sec=1.0)

    report = {
        "input": {"original_voice": "original.wav"},
        "segments": [
            {
                "segment_id": "seg1",
                "start": 0.2,
                "end": 1.2,
                "dub_audio_path": "dub.wav",
            }
        ],
    }
    out = dub_pitch.enrich_report_with_pitch(report, pipeline_root=tmp_path)

    assert out["pitch_meta"]["status"] == "ok"
    assert out["pitch_meta"]["enriched_count"] == 1

    contour = out["segments"][0]["pitch_contour"]
    assert set(contour.keys()) == {"original", "dub"}
    for key in ("original", "dub"):
        assert "times" in contour[key] and "hz" in contour[key]
        assert len(contour[key]["times"]) == len(contour[key]["hz"])

    voiced_original = [hz for hz in contour["original"]["hz"] if hz is not None]
    voiced_dub = [hz for hz in contour["dub"]["hz"] if hz is not None]
    assert voiced_original, "original 220Hz tone should produce voiced frames"
    assert voiced_dub, "dub 330Hz tone should produce voiced frames"
    # Median Hz should follow the synthetic source frequencies.
    assert abs(float(np.median(voiced_original)) - 220.0) < 8.0
    assert abs(float(np.median(voiced_dub)) - 330.0) < 8.0


def test_enrich_report_path_is_idempotent(tmp_path: Path) -> None:
    original = tmp_path / "original.wav"
    dub = tmp_path / "dub.wav"
    _write_sine_wav(original, freq_hz=220.0, duration_sec=1.2)
    _write_sine_wav(dub, freq_hz=220.0, duration_sec=1.0)

    report = {
        "input": {"original_voice": "original.wav"},
        "segments": [
            {"segment_id": "s1", "start": 0.0, "end": 1.0, "dub_audio_path": "dub.wav"}
        ],
    }
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    first = dub_pitch.enrich_report_path(report_path, pipeline_root=tmp_path)
    second = dub_pitch.enrich_report_path(report_path, pipeline_root=tmp_path)

    assert first["pitch_meta"]["status"] == "ok"
    assert second["pitch_meta"]["status"] == "empty"  # nothing new to enrich
    assert second["pitch_meta"]["skipped_count"] == 1
    # Contour data is preserved across re-runs (idempotency guarantee).
    assert second["segments"][0]["pitch_contour"]["original"]["times"]
