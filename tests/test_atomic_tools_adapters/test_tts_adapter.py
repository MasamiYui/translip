from __future__ import annotations

import wave
from pathlib import Path


def test_tts_adapter_generates_speech_and_report(tmp_path: Path, monkeypatch) -> None:
    from translip.server.atomic_tools.adapters.tts import TtsAdapter

    output_dir = tmp_path / "output"

    def fake_generate_speech(*, text: str, language: str, reference_audio_path: Path | None, output_path: Path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(24_000)
            wav_file.writeframes(b"\0\0" * 24_000)
        return {
            "output_path": output_path,
            "duration_sec": 1.0,
            "sample_rate": 24_000,
            "mode": "designed",
            "reference_used": reference_audio_path is not None,
        }

    monkeypatch.setattr(
        "translip.server.atomic_tools.adapters.tts.generate_speech",
        fake_generate_speech,
    )

    result = TtsAdapter().run(
        {"text": "Hello world", "language": "en"},
        tmp_path / "input",
        output_dir,
        lambda *_args, **_kwargs: None,
    )

    assert (output_dir / "speech.wav").exists()
    assert (output_dir / "speech.json").exists()
    assert result["speech_file"] == "speech.wav"
    assert result["sample_rate"] == 24_000
    assert result["duration_sec"] == 1.0
