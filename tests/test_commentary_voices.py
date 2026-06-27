from __future__ import annotations

from pathlib import Path

import pytest

from translip.commentary import voices


def test_builtin_voices_and_default() -> None:
    ids = [v.id for v in voices.list_narrator_voices()]
    assert voices.DEFAULT_NARRATOR_VOICE in ids
    assert "narrator-male-calm" in ids
    assert "narrator-female-bright" in ids


def test_cache_path_splits_by_language(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(voices, "narrator_voices_cache_dir", lambda: tmp_path)
    assert voices._reference_path("narrator-male-calm", "zh").name == "narrator-male-calm.zh.wav"
    assert voices._reference_path("narrator-male-calm", "en-US").name == "narrator-male-calm.en.wav"


def test_resolve_default_generates_builtin_default(tmp_path, monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def fake_gen(voice, language, out_path):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"wav")
        calls.append((voice.id, language))
        return out_path

    monkeypatch.setattr(voices, "narrator_voices_cache_dir", lambda: tmp_path / "nv")
    monkeypatch.setattr(voices, "_generate_voice_reference", fake_gen)

    ref = voices.resolve_narrator_reference(
        None, language="zh", work_dir=tmp_path, source_path=Path("x.mp4"), source_duration=100.0
    )
    assert ref.exists()
    assert calls == [(voices.DEFAULT_NARRATOR_VOICE, "zh")]


def test_resolve_builtin_cache_hit_skips_generation(tmp_path, monkeypatch) -> None:
    cache_dir = tmp_path / "nv"
    cache_dir.mkdir(parents=True)
    cached = cache_dir / "narrator-male-calm.zh.wav"
    cached.write_bytes(b"cached")
    monkeypatch.setattr(voices, "narrator_voices_cache_dir", lambda: cache_dir)

    def boom(*args, **kwargs):
        raise AssertionError("must not regenerate when the cache is warm")

    monkeypatch.setattr(voices, "_generate_voice_reference", boom)
    ref = voices.resolve_narrator_reference(
        "narrator-male-calm", language="zh", work_dir=tmp_path, source_path=Path("x"), source_duration=10.0
    )
    assert ref == cached


def test_resolve_source_borrows_from_video(tmp_path, monkeypatch) -> None:
    borrowed = tmp_path / "borrowed.wav"
    monkeypatch.setattr(voices, "borrow_from_source", lambda **kwargs: borrowed)
    ref = voices.resolve_narrator_reference(
        "source", language="zh", work_dir=tmp_path, source_path=Path("x"), source_duration=10.0
    )
    assert ref == borrowed


def test_resolve_path_passthrough(tmp_path) -> None:
    supplied = tmp_path / "my_narrator.wav"
    supplied.write_bytes(b"x")
    ref = voices.resolve_narrator_reference(
        str(supplied), language="zh", work_dir=tmp_path, source_path=Path("x"), source_duration=10.0
    )
    assert ref == supplied


def test_resolve_unknown_voice_raises(tmp_path) -> None:
    with pytest.raises(ValueError):
        voices.resolve_narrator_reference(
            "no-such-voice", language="zh", work_dir=tmp_path, source_path=Path("x"), source_duration=10.0
        )


def test_resolve_generation_failure_is_actionable(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(voices, "narrator_voices_cache_dir", lambda: tmp_path / "nv")

    def fail(*args, **kwargs):
        raise RuntimeError(
            "Could not load the VoiceDesign model ...: boom. Set HF_ENDPOINT=https://hf-mirror.com to download it."
        )

    monkeypatch.setattr(voices, "_generate_voice_reference", fail)
    with pytest.raises(RuntimeError, match="hf-mirror"):
        voices.resolve_narrator_reference(
            "narrator-male-calm", language="zh", work_dir=tmp_path, source_path=Path("x"), source_duration=10.0
        )
