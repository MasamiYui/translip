from __future__ import annotations

from pathlib import Path

import numpy as np

from translip.pipeline.separation_quality import (
    compute_separation_metrics,
    separation_metrics,
)


def test_perfect_reconstruction_has_high_confidence() -> None:
    rng = np.linspace(0, 1, 16000, dtype=np.float32)
    voice = np.sin(2 * np.pi * 220 * rng).astype(np.float32)
    background = 0.3 * np.sin(2 * np.pi * 55 * rng).astype(np.float32)
    mix = voice + background

    metrics = separation_metrics(voice=voice, background=background, mix=mix)

    assert metrics["reconstruction_residual_ratio"] < 1e-3
    assert metrics["separation_confidence"] > 0.99
    # voice is louder than the background -> positive dB ratio.
    assert metrics["voice_to_background_db"] > 0


def test_poor_reconstruction_has_low_confidence() -> None:
    rng = np.linspace(0, 1, 16000, dtype=np.float32)
    voice = np.sin(2 * np.pi * 220 * rng).astype(np.float32)
    background = 0.3 * np.sin(2 * np.pi * 55 * rng).astype(np.float32)
    # Mix unrelated to voice+background -> large residual.
    mix = np.sin(2 * np.pi * 999 * rng).astype(np.float32)

    metrics = separation_metrics(voice=voice, background=background, mix=mix)

    assert metrics["reconstruction_residual_ratio"] > 0.5
    assert metrics["separation_confidence"] < 0.5


def test_metrics_skip_residual_when_sample_rates_differ() -> None:
    sig = np.ones(100, dtype=np.float32)
    metrics = separation_metrics(voice=sig, background=sig, mix=sig, same_sample_rate=False)
    assert "reconstruction_residual_ratio" not in metrics
    assert "separation_confidence" not in metrics
    assert "voice_rms" in metrics


def test_empty_signal_returns_empty_metrics() -> None:
    empty = np.zeros(0, dtype=np.float32)
    assert separation_metrics(voice=empty, background=empty, mix=empty) == {}


def test_compute_separation_metrics_reads_files(tmp_path: Path) -> None:
    import soundfile as sf

    sr = 16000
    rng = np.linspace(0, 1, sr, dtype=np.float32)
    # Keep the mix within +/-1 so the 16-bit WAV round-trip does not clip.
    voice = 0.6 * np.sin(2 * np.pi * 220 * rng).astype(np.float32)
    background = 0.2 * np.sin(2 * np.pi * 60 * rng).astype(np.float32)
    mix = voice + background

    voice_path = tmp_path / "voice.wav"
    background_path = tmp_path / "background.wav"
    mix_path = tmp_path / "mix.wav"
    sf.write(voice_path, voice, sr)
    sf.write(background_path, background, sr)
    sf.write(mix_path, mix, sr)

    metrics = compute_separation_metrics(
        voice_path=voice_path, background_path=background_path, mix_path=mix_path
    )
    assert metrics["separation_confidence"] > 0.95
