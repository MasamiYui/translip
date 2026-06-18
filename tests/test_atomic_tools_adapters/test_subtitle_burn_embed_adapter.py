from __future__ import annotations

from pathlib import Path

SRT = """1
00:00:01,000 --> 00:00:03,000
你好，世界
"""


def test_subtitle_burn_converts_srt_and_burns(tmp_path: Path, monkeypatch) -> None:
    from translip.server.atomic_tools.adapters.subtitle_burn import SubtitleBurnAdapter

    video_path = tmp_path / "input" / "video_file" / "clip.mp4"
    subtitle_path = tmp_path / "input" / "subtitle_file" / "subs.srt"
    video_path.parent.mkdir(parents=True, exist_ok=True)
    subtitle_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(b"video")
    subtitle_path.write_text(SRT, encoding="utf-8")
    output_dir = tmp_path / "output"

    monkeypatch.setattr(
        "translip.server.atomic_tools.adapters.subtitle_burn.probe_video_resolution",
        lambda _path: (1920, 1080),
    )
    captured: dict = {}

    def fake_burn(**kwargs):
        kwargs["output_path"].write_bytes(b"burned")
        captured.update(kwargs)
        return kwargs["output_path"]

    monkeypatch.setattr(
        "translip.server.atomic_tools.adapters.subtitle_burn.burn_subtitle", fake_burn
    )

    result = SubtitleBurnAdapter().run(
        {"video_file_id": "video", "subtitle_file_id": "subs", "lang": "auto"},
        tmp_path / "input",
        output_dir,
        lambda *_a, **_k: None,
    )

    # SRT got converted to a styled ASS the burner was handed.
    ass_path = output_dir / "subtitle.ass"
    assert ass_path.exists()
    assert captured["subtitle_path"] == ass_path
    assert (output_dir / "output.mp4").read_bytes() == b"burned"
    assert result["output_file"] == "output.mp4"
    assert (result["width"], result["height"]) == (1920, 1080)


def test_subtitle_burn_passes_ass_through(tmp_path: Path, monkeypatch) -> None:
    from translip.server.atomic_tools.adapters.subtitle_burn import SubtitleBurnAdapter

    video_path = tmp_path / "input" / "video_file" / "clip.mp4"
    subtitle_path = tmp_path / "input" / "subtitle_file" / "subs.ass"
    video_path.parent.mkdir(parents=True, exist_ok=True)
    subtitle_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(b"video")
    subtitle_path.write_text("[Script Info]\n", encoding="utf-8")
    output_dir = tmp_path / "output"

    monkeypatch.setattr(
        "translip.server.atomic_tools.adapters.subtitle_burn.probe_video_resolution",
        lambda _path: (1280, 720),
    )
    captured: dict = {}
    monkeypatch.setattr(
        "translip.server.atomic_tools.adapters.subtitle_burn.burn_subtitle",
        lambda **kwargs: (captured.update(kwargs), kwargs["output_path"].write_bytes(b"x"))[1],
    )

    SubtitleBurnAdapter().run(
        {"video_file_id": "video", "subtitle_file_id": "subs"},
        tmp_path / "input",
        output_dir,
        lambda *_a, **_k: None,
    )

    # An ASS upload is burned directly — no conversion artifact written.
    assert captured["subtitle_path"] == subtitle_path
    assert not (output_dir / "subtitle.ass").exists()


def test_subtitle_embed_soft_muxes(tmp_path: Path, monkeypatch) -> None:
    from translip.server.atomic_tools.adapters.subtitle_embed import SubtitleEmbedAdapter

    video_path = tmp_path / "input" / "video_file" / "clip.mp4"
    subtitle_path = tmp_path / "input" / "subtitle_file" / "subs.srt"
    video_path.parent.mkdir(parents=True, exist_ok=True)
    subtitle_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(b"video")
    subtitle_path.write_text(SRT, encoding="utf-8")
    output_dir = tmp_path / "output"

    captured: dict = {}

    def fake_embed(**kwargs):
        kwargs["output_path"].write_bytes(b"embedded")
        captured.update(kwargs)
        return kwargs["output_path"]

    monkeypatch.setattr(
        "translip.server.atomic_tools.adapters.subtitle_embed.embed_soft_subtitle", fake_embed
    )

    result = SubtitleEmbedAdapter().run(
        {"video_file_id": "video", "subtitle_file_id": "subs", "container": "mkv"},
        tmp_path / "input",
        output_dir,
        lambda *_a, **_k: None,
    )

    assert (output_dir / "output.mkv").read_bytes() == b"embedded"
    assert result["output_file"] == "output.mkv"
    assert result["container"] == "mkv"
    assert captured["container"] == "mkv"
