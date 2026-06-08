from __future__ import annotations

from translip.models.base import VoiceEnhancer
from translip.models.clearervoice import NoOpVoiceEnhancer


def test_noop_voice_enhancer_is_a_passthrough(tmp_path) -> None:
    # SEP-3: NoOpVoiceEnhancer is an honest placeholder — it must copy the input
    # through byte-for-byte and apply no real enhancement.
    src = tmp_path / "voice.wav"
    payload = b"RIFF....fake-wav-bytes...."
    src.write_bytes(payload)
    out = tmp_path / "voice_enhanced.wav"

    result = NoOpVoiceEnhancer().enhance(src, out)

    assert result == out
    assert out.read_bytes() == payload


def test_noop_voice_enhancer_is_a_voice_enhancer() -> None:
    assert issubclass(NoOpVoiceEnhancer, VoiceEnhancer)
