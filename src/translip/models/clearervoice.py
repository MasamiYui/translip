from __future__ import annotations

from pathlib import Path

from .base import VoiceEnhancer


class NoOpVoiceEnhancer(VoiceEnhancer):
    """Passthrough placeholder — copies the voice track through unchanged.

    There is **no** real ClearerVoice / denoise / dereverb integration yet; this
    exists only so the ``--enhance-voice`` flag has a no-op implementation. Do not
    treat its output as enhanced audio. Callers that enable it should warn the
    user (see ``pipeline/runner.py``). Replacing this with a real enhancer is
    tracked as SEP-3 and requires real-synthesis A/B validation.
    """

    def enhance(self, voice_path: Path, output_path: Path) -> Path:
        output_path.write_bytes(voice_path.read_bytes())
        return output_path

