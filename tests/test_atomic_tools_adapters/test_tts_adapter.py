from __future__ import annotations

import wave
from pathlib import Path

import pytest


def _write_stub_wav(output_path: Path, *, sample_rate: int = 24_000, seconds: int = 1) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"\0\0" * sample_rate * seconds)


def test_tts_adapter_generates_speech_and_report(tmp_path: Path, monkeypatch) -> None:
    from translip.server.atomic_tools.adapters.tts import TtsAdapter

    output_dir = tmp_path / "output"
    captured: dict[str, object] = {}

    def fake_generate_speech(
        *, text: str, language: str, backend: str, reference_audio_path: Path | None, output_path: Path
    ):
        captured["backend"] = backend
        _write_stub_wav(output_path)
        return {
            "output_path": output_path,
            "duration_sec": 1.0,
            "sample_rate": 24_000,
            "mode": "designed",
            "backend": backend,
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
    # Default backend is qwen3tts and is threaded through to generate_speech + result.
    assert captured["backend"] == "qwen3tts"
    assert result["backend"] == "qwen3tts"


def test_tts_adapter_dispatches_to_protocol_backend(tmp_path: Path, monkeypatch) -> None:
    from translip.server.atomic_tools.adapters import tts as tts_module

    output_dir = tmp_path / "output"
    # Materialize an uploaded reference clip where first_input() will find it.
    _write_stub_wav(tmp_path / "input" / "reference_audio_file" / "ref.wav")

    seen: dict[str, object] = {}

    def fake_protocol(*, backend, text, language, reference_audio_path, output_path):
        seen["backend"] = backend
        seen["reference_audio_path"] = reference_audio_path
        _write_stub_wav(output_path, sample_rate=16_000)
        return 16_000, 2.5

    monkeypatch.setattr(tts_module, "_generate_via_protocol_backend", fake_protocol)

    result = tts_module.TtsAdapter().run(
        {"text": "Hola", "language": "es", "backend": "voxcpm2", "reference_audio_file_id": "ref-1"},
        tmp_path / "input",
        output_dir,
        lambda *_args, **_kwargs: None,
    )

    assert seen["backend"] == "voxcpm2"
    assert Path(seen["reference_audio_path"]).name == "ref.wav"  # type: ignore[arg-type]
    assert result["backend"] == "voxcpm2"
    assert result["mode"] == "voice_clone"
    assert result["sample_rate"] == 16_000
    assert result["duration_sec"] == 2.5
    assert result["reference_used"] is True


def test_prepare_reference_audio_caps_and_mono(tmp_path: Path) -> None:
    import numpy as np
    import soundfile as sf

    from translip.server.atomic_tools.adapters.tts import (
        _REFERENCE_MAX_SPEECH_SEC,
        _REFERENCE_TAIL_SILENCE_SEC,
        _prepare_reference_audio,
    )

    sample_rate = 16_000
    # 20s stereo clip → should be downmixed to mono and capped to 11s + 1s tail.
    stereo = np.zeros((sample_rate * 20, 2), dtype=np.float32)
    src = tmp_path / "long_stereo.wav"
    sf.write(src, stereo, sample_rate)

    prepared_path, duration = _prepare_reference_audio(src, tmp_path)

    assert prepared_path.name == "reference_prepared.wav"
    data, out_sr = sf.read(str(prepared_path), always_2d=False)
    assert out_sr == sample_rate
    assert data.ndim == 1  # mono
    expected_len = int(_REFERENCE_MAX_SPEECH_SEC * sample_rate) + int(_REFERENCE_TAIL_SILENCE_SEC * sample_rate)
    assert len(data) == expected_len
    assert duration == pytest.approx((_REFERENCE_MAX_SPEECH_SEC + _REFERENCE_TAIL_SILENCE_SEC), abs=0.01)


def test_prepare_reference_audio_falls_back_on_decode_error(tmp_path: Path) -> None:
    from translip.server.atomic_tools.adapters.tts import _prepare_reference_audio

    bogus = tmp_path / "not-audio.mp3"
    bogus.write_bytes(b"not a real audio file")

    prepared_path, duration = _prepare_reference_audio(bogus, tmp_path)

    # Decode failed → fall back to the raw upload path so the backend loader can try.
    assert prepared_path == bogus
    assert duration == 0.0


def test_tts_request_schema_validation() -> None:
    from pydantic import ValidationError

    from translip.server.atomic_tools.schemas import TtsToolRequest

    # Default backend keeps the tool usable with no upload.
    assert TtsToolRequest(text="hi").backend == "qwen3tts"

    # Clone-only backends require a reference audio upload.
    for backend in ("moss-tts-nano-onnx", "voxcpm2"):
        with pytest.raises(ValidationError):
            TtsToolRequest(text="hi", backend=backend)
        ok = TtsToolRequest(text="hi", backend=backend, reference_audio_file_id="ref-1")
        assert ok.backend == backend

    # Unknown backends are rejected.
    with pytest.raises(ValidationError):
        TtsToolRequest(text="hi", backend="bogus")
