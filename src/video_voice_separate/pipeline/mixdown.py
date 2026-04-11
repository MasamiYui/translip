from __future__ import annotations

from pathlib import Path

from ..utils.ffmpeg import mix_audio


def build_background(stems: list[Path], output_path: Path) -> Path:
    return mix_audio(stems, output_path)

