from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace


def _fake_info(*, media_type="video", streams=()):
    return SimpleNamespace(
        media_type=media_type,
        format_name="mov,mp4,m4a,3gp,3g2,mj2",
        duration_sec=15.2,
        audio_stream_count=sum(1 for s in streams if s.codec_type == "audio"),
        sample_rate=48_000,
        channels=2,
        streams=list(streams),
    )


def _stream(index, codec_type, codec_name, language=None, title=None):
    return SimpleNamespace(
        index=index, codec_type=codec_type, codec_name=codec_name, language=language, title=title
    )


def test_probe_adapter_writes_report_and_result_payload(tmp_path: Path, monkeypatch) -> None:
    from translip.server.atomic_tools.adapters.probe import ProbeAdapter

    input_file = tmp_path / "input" / "file" / "demo.mp4"
    input_file.parent.mkdir(parents=True, exist_ok=True)
    input_file.write_bytes(b"video")
    output_dir = tmp_path / "output"

    monkeypatch.setattr(
        "translip.server.atomic_tools.adapters.probe.probe_media",
        lambda path: _fake_info(streams=[_stream(0, "video", "h264"), _stream(1, "audio", "aac")]),
    )

    result = ProbeAdapter().run(
        {"file_id": "fake"},
        input_file.parent.parent,
        output_dir,
        lambda *_args, **_kwargs: None,
    )

    report = json.loads((output_dir / "probe.json").read_text(encoding="utf-8"))
    assert report["duration_sec"] == 15.2
    assert result["format_name"] == "mov,mp4,m4a,3gp,3g2,mj2"
    assert result["has_video"] is True
    assert result["audio_streams"] == 1


def test_probe_adapter_surfaces_stream_language_tags(tmp_path: Path, monkeypatch) -> None:
    from translip.server.atomic_tools.adapters.probe import ProbeAdapter

    input_file = tmp_path / "input" / "file" / "demo.mkv"
    input_file.parent.mkdir(parents=True, exist_ok=True)
    input_file.write_bytes(b"video")
    output_dir = tmp_path / "output"

    streams = [
        _stream(0, "video", "h264"),
        _stream(1, "audio", "aac", language="jpn"),
        _stream(2, "subtitle", "subrip", language="chi", title="简体中文"),
        _stream(3, "subtitle", "subrip", language="eng"),
    ]
    monkeypatch.setattr(
        "translip.server.atomic_tools.adapters.probe.probe_media",
        lambda path: _fake_info(streams=streams),
    )

    result = ProbeAdapter().run(
        {"file_id": "fake"}, input_file.parent.parent, output_dir, lambda *_a, **_k: None
    )

    assert result["audio_languages"] == ["jpn"]
    assert result["subtitle_stream_count"] == 2
    assert result["subtitle_languages"] == ["chi", "eng"]
    assert [s["type"] for s in result["streams"]] == ["video", "audio", "subtitle", "subtitle"]
    assert result["streams"][2]["title"] == "简体中文"
