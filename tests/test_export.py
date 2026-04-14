from pathlib import Path

import numpy as np
import soundfile as sf

from translip.pipeline.export import export_pair


def test_export_pair_wav(tmp_path: Path) -> None:
    voice_wav = tmp_path / "voice.wav"
    background_wav = tmp_path / "background.wav"
    tone = np.sin(2 * np.pi * 220 * np.linspace(0, 1, 44100, endpoint=False))
    sf.write(voice_wav, tone, 44100)
    sf.write(background_wav, tone, 44100)

    voice_out, background_out = export_pair(
        voice_wav,
        background_wav,
        tmp_path / "out",
        fmt="wav",
        sample_rate=None,
        bitrate=None,
    )

    assert voice_out.exists()
    assert background_out.exists()

