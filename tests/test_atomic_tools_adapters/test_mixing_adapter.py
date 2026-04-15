from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf


def _write_tone(path: Path, *, frequency: float, duration_sec: float, sample_rate: int = 24_000) -> None:
    sample_count = max(1, int(round(duration_sec * sample_rate)))
    time_axis = np.linspace(0.0, duration_sec, sample_count, endpoint=False, dtype=np.float32)
    waveform = (0.15 * np.sin(2 * np.pi * frequency * time_axis)).astype(np.float32)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, waveform, sample_rate)


def test_mixing_adapter_creates_mixed_audio_file(tmp_path: Path) -> None:
    from translip.server.atomic_tools.adapters.mixing import MixingAdapter

    voice_path = tmp_path / "input" / "voice_file" / "voice.wav"
    background_path = tmp_path / "input" / "background_file" / "background.wav"
    _write_tone(voice_path, frequency=220.0, duration_sec=1.0)
    _write_tone(background_path, frequency=110.0, duration_sec=1.0)
    output_dir = tmp_path / "output"

    result = MixingAdapter().run(
        {
            "voice_file_id": "voice",
            "background_file_id": "background",
            "background_gain_db": -8.0,
            "ducking_mode": "static",
            "output_format": "wav",
        },
        tmp_path / "input",
        output_dir,
        lambda *_args, **_kwargs: None,
    )

    mixed_path = output_dir / "mixed.wav"
    waveform, sample_rate = sf.read(mixed_path, dtype="float32")
    assert sample_rate == 24_000
    assert waveform.size > 0
    assert result["mixed_file"] == "mixed.wav"
