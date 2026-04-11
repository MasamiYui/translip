from pathlib import Path

import numpy as np
import soundfile as sf

from video_voice_separate.pipeline.route import resolve_route
from video_voice_separate.types import SeparationRequest


def test_manual_route_wins(tmp_path: Path) -> None:
    wav_path = tmp_path / "tone.wav"
    signal = np.sin(2 * np.pi * 440 * np.linspace(0, 1, 22050, endpoint=False))
    sf.write(wav_path, signal, 22050)
    route = resolve_route(SeparationRequest(input_path=wav_path, mode="music"), wav_path)
    assert route.route == "music"
    assert route.reason == "manual-mode"

