from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import soundfile as sf

from translip.quality import dub_mel


def _write_sine_wav(path: Path, *, freq_hz: float, duration_sec: float, sr: int = 22050) -> None:
    t = np.linspace(0, duration_sec, int(sr * duration_sec), endpoint=False, dtype=np.float32)
    waveform = 0.6 * np.sin(2 * np.pi * freq_hz * t).astype(np.float32)
    sf.write(path, waveform, sr)


def test_extract_mel_db_returns_uint8_with_correct_shape(tmp_path: Path) -> None:
    wav_path = tmp_path / "tone.wav"
    _write_sine_wav(wav_path, freq_hz=440.0, duration_sec=1.0)

    waveform, sr = sf.read(wav_path, dtype="float32", always_2d=False)
    mel, meta = dub_mel.extract_mel_db(waveform, sr)

    assert mel.dtype == np.uint8
    assert mel.shape[0] == dub_mel.N_MELS
    assert mel.shape[1] > 0
    assert meta["n_mels"] == dub_mel.N_MELS
    # Energy is concentrated in a narrow band (a sine), so most cells should be quiet.
    assert int(mel.min()) == 0
    assert int(mel.max()) == 255  # ref=np.max in librosa.power_to_db pins peak to 0 dB


def test_mel_peak_band_tracks_input_frequency(tmp_path: Path) -> None:
    """A higher-frequency tone must light up a higher mel band index."""
    low_path = tmp_path / "low.wav"
    high_path = tmp_path / "high.wav"
    _write_sine_wav(low_path, freq_hz=220.0, duration_sec=0.8)
    _write_sine_wav(high_path, freq_hz=2200.0, duration_sec=0.8)

    low_wave, low_sr = sf.read(low_path, dtype="float32", always_2d=False)
    high_wave, high_sr = sf.read(high_path, dtype="float32", always_2d=False)
    low_mel, _ = dub_mel.extract_mel_db(low_wave, low_sr)
    high_mel, _ = dub_mel.extract_mel_db(high_wave, high_sr)

    low_peak_band = int(np.argmax(low_mel.mean(axis=1)))
    high_peak_band = int(np.argmax(high_mel.mean(axis=1)))
    assert high_peak_band > low_peak_band, (
        f"expected higher band for 2200Hz than 220Hz, got {high_peak_band} vs {low_peak_band}"
    )


def test_enrich_report_handles_no_segments(tmp_path: Path) -> None:
    report = {"segments": []}
    out = dub_mel.enrich_report_with_mel(report, pipeline_root=tmp_path)
    assert out["mel_meta"]["status"] == "no_segments"


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
    out = dub_mel.enrich_report_with_mel(report, pipeline_root=tmp_path)
    assert out["mel_meta"]["status"] == "empty"
    assert out["mel_meta"]["enriched_count"] == 0
    assert out["mel_meta"]["skipped_count"] >= 1
    assert "mel_spectrogram" not in out["segments"][0]


def test_enrich_report_writes_spectrograms_for_real_audio(tmp_path: Path) -> None:
    original = tmp_path / "original.wav"
    dub = tmp_path / "dub.wav"
    _write_sine_wav(original, freq_hz=440.0, duration_sec=1.5)
    _write_sine_wav(dub, freq_hz=880.0, duration_sec=1.0)

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
    out = dub_mel.enrich_report_with_mel(report, pipeline_root=tmp_path)

    assert out["mel_meta"]["status"] == "ok"
    assert out["mel_meta"]["enriched_count"] == 1

    spec = out["segments"][0]["mel_spectrogram"]
    for key in ("original", "dub"):
        payload = spec[key]
        assert payload is not None
        # Row-major list-of-lists with N_MELS rows.
        assert len(payload["data"]) == dub_mel.N_MELS
        # Frame count should respect the cap.
        assert 0 < payload["n_frames"] <= dub_mel.MAX_FRAMES_PER_SEGMENT
        # Each row must be the same length as n_frames.
        assert all(len(row) == payload["n_frames"] for row in payload["data"])
        # Values must be uint8-like ints in [0, 255].
        flat = [v for row in payload["data"] for v in row]
        assert min(flat) >= 0 and max(flat) <= 255


def test_enrich_report_path_is_idempotent(tmp_path: Path) -> None:
    original = tmp_path / "original.wav"
    dub = tmp_path / "dub.wav"
    _write_sine_wav(original, freq_hz=440.0, duration_sec=1.2)
    _write_sine_wav(dub, freq_hz=440.0, duration_sec=1.0)

    report = {
        "input": {"original_voice": "original.wav"},
        "segments": [
            {"segment_id": "s1", "start": 0.0, "end": 1.0, "dub_audio_path": "dub.wav"}
        ],
    }
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    first = dub_mel.enrich_report_path(report_path, pipeline_root=tmp_path)
    second = dub_mel.enrich_report_path(report_path, pipeline_root=tmp_path)

    assert first["mel_meta"]["status"] == "ok"
    assert second["mel_meta"]["status"] == "empty"  # nothing new to enrich
    assert second["mel_meta"]["skipped_count"] == 1
    # Spectrogram data is preserved across re-runs.
    assert second["segments"][0]["mel_spectrogram"]["original"]["data"]
