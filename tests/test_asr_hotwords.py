from __future__ import annotations

from pathlib import Path

from translip.transcription import asr
from translip.transcription.asr import AsrOptions, hotword_string


def test_hotword_string_joins_and_strips() -> None:
    assert hotword_string(("Ne Zha", "  Ao Bing ", "", "  ")) == "Ne Zha Ao Bing"
    assert hotword_string(()) == ""


def test_parse_hotwords_cli_splits_on_commas() -> None:
    from translip.cli import _parse_hotwords

    assert _parse_hotwords("Ne Zha, Ao Bing ,") == ["Ne Zha", "Ao Bing"]
    assert _parse_hotwords(None) == []
    assert _parse_hotwords("") == []


def test_asr_options_metadata_includes_hotwords_as_list() -> None:
    meta = AsrOptions(hotwords=("Ne Zha", "Ao Bing")).metadata()
    assert meta["hotwords"] == ["Ne Zha", "Ao Bing"]
    # default is empty
    assert AsrOptions().metadata()["hotwords"] == []


class _FakeInfo:
    language = "zh"
    duration = 1.0


class _FakeModel:
    def __init__(self) -> None:
        self.kwargs: dict | None = None

    def transcribe(self, audio, **kwargs):
        self.kwargs = kwargs
        return iter([]), _FakeInfo()


def test_transcribe_audio_passes_hotwords_to_faster_whisper(monkeypatch, tmp_path: Path) -> None:
    fake = _FakeModel()
    monkeypatch.setattr(asr, "_load_model", lambda *a, **k: fake)

    asr.transcribe_audio(
        tmp_path / "audio.wav",
        model_name="tiny",
        language="zh",
        requested_device="cpu",
        options=AsrOptions(hotwords=("Ne Zha", "Ao Bing")),
    )
    assert fake.kwargs is not None
    assert fake.kwargs.get("hotwords") == "Ne Zha Ao Bing"


def test_transcribe_audio_omits_hotwords_when_empty(monkeypatch, tmp_path: Path) -> None:
    fake = _FakeModel()
    monkeypatch.setattr(asr, "_load_model", lambda *a, **k: fake)

    asr.transcribe_audio(
        tmp_path / "audio.wav",
        model_name="tiny",
        language="zh",
        requested_device="cpu",
        options=AsrOptions(),
    )
    assert fake.kwargs is not None
    assert "hotwords" not in fake.kwargs
