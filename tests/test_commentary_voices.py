from __future__ import annotations

from pathlib import Path

import pytest

from translip.commentary import voices


def test_builtin_voices_and_default() -> None:
    ids = [v.id for v in voices.list_narrator_voices()]
    assert voices.DEFAULT_NARRATOR_VOICE in ids
    # legacy voices kept stable
    assert "narrator-male-calm" in ids
    assert "narrator-female-bright" in ids
    # newly added narrators covering Chinese / English / Japanese / Korean
    assert "narrator-female-warm" in ids
    assert "narrator-male-beijing" in ids
    assert "narrator-male-sichuan" in ids
    assert "narrator-en-male-dynamic" in ids
    assert "narrator-en-male-sunny" in ids
    assert "narrator-ja-female" in ids
    assert "narrator-ko-female" in ids


def test_voice_metadata_fields_populated() -> None:
    for v in voices.list_narrator_voices():
        assert v.native_language in {"zh", "en", "ja", "ko"}
        # bilingual labels for the picker UI
        assert v.name_zh and v.name_en
        # short marketing-style descriptions for the picker UI
        assert v.description_zh and v.description_en


def test_lang_key_supports_zh_en_ja_ko() -> None:
    assert voices._lang_key("zh-CN") == "zh"
    assert voices._lang_key("en-US") == "en"
    assert voices._lang_key("ja") == "ja"
    assert voices._lang_key("ko-KR") == "ko"
    assert voices._lang_key("") == "zh"


def test_reading_text_covers_new_languages() -> None:
    for lang in ("zh", "en", "ja", "ko"):
        assert voices._reading_text(lang)


def test_cache_path_splits_by_language(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(voices, "narrator_voices_cache_dir", lambda: tmp_path)
    assert voices._reference_path("narrator-male-calm", "zh").name == "narrator-male-calm.zh.wav"
    assert voices._reference_path("narrator-male-calm", "en-US").name == "narrator-male-calm.en.wav"
    assert voices._reference_path("narrator-ja-female", "ja").name == "narrator-ja-female.ja.wav"
    assert voices._reference_path("narrator-ko-female", "ko-KR").name == "narrator-ko-female.ko.wav"


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


# ---- HTTP routes -------------------------------------------------------------


@pytest.fixture()
def api_client(tmp_path, monkeypatch):
    """Spin up a FastAPI TestClient with the narrator cache redirected to tmp."""
    from fastapi.testclient import TestClient

    from translip.server.app import app

    monkeypatch.setattr(voices, "narrator_voices_cache_dir", lambda: tmp_path)
    return TestClient(app)


def test_list_narrator_voices_endpoint_returns_metadata(api_client) -> None:
    resp = api_client.get("/api/config/narrator-voices")
    assert resp.status_code == 200
    payload = resp.json()
    by_id = {item["id"]: item for item in payload}
    # the picker depends on these fields
    sample = by_id["narrator-male-calm"]
    assert sample["name_zh"] == "沉稳男声"
    assert sample["native_language"] == "zh"
    assert sample["preview_url"] == "/api/config/narrator-voices/narrator-male-calm/preview"
    assert sample["description_zh"] and sample["description_en"]
    assert "narrator-ja-female" in by_id
    assert "narrator-ko-female" in by_id


def test_preview_endpoint_serves_cached_audio(api_client, tmp_path) -> None:
    cached = tmp_path / "narrator-female-bright.zh.wav"
    cached.write_bytes(b"RIFFfakeWAVE")

    resp = api_client.get("/api/config/narrator-voices/narrator-female-bright/preview")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("audio/wav")
    assert resp.content == b"RIFFfakeWAVE"


def test_preview_endpoint_renders_on_cache_miss(api_client, tmp_path, monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def fake_gen(voice, language, out_path):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"freshly-rendered")
        calls.append((voice.id, language))
        return out_path

    monkeypatch.setattr(voices, "_generate_voice_reference", fake_gen)

    resp = api_client.get("/api/config/narrator-voices/narrator-ja-female/preview")
    assert resp.status_code == 200
    assert resp.content == b"freshly-rendered"
    # falls back to the voice's native language when no `language` query is given
    assert calls == [("narrator-ja-female", "ja")]


def test_preview_endpoint_404_on_unknown_voice(api_client) -> None:
    resp = api_client.get("/api/config/narrator-voices/no-such/preview")
    assert resp.status_code == 404
