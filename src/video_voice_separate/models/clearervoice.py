from __future__ import annotations

from pathlib import Path

from .base import VoiceEnhancer


class NoOpVoiceEnhancer(VoiceEnhancer):
    def enhance(self, voice_path: Path, output_path: Path) -> Path:
        output_path.write_bytes(voice_path.read_bytes())
        return output_path

