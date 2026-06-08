from __future__ import annotations

from pathlib import Path

import pytest

from translip.utils import ffmpeg


def _pairs(args: list[str], flag: str) -> list[str]:
    return [args[i + 1] for i, tok in enumerate(args) if tok == flag and i + 1 < len(args)]


def test_iso639_2_mapping() -> None:
    assert ffmpeg.iso639_2("en") == "eng"
    assert ffmpeg.iso639_2("zh") == "zho"
    assert ffmpeg.iso639_2("zh-CN") == "zho"
    assert ffmpeg.iso639_2("ja") == "jpn"
    assert ffmpeg.iso639_2("kor") == "kor"  # already 3-letter passthrough
    assert ffmpeg.iso639_2("xx") == "und"
    assert ffmpeg.iso639_2(None) == "und"


def test_soft_subtitle_args_full_feature() -> None:
    args = ffmpeg.build_soft_subtitle_mux_args(
        input_video_path=Path("in.mp4"),
        dub_audio_path=Path("dub.wav"),
        subtitle_path=Path("subs.srt"),
        output_path=Path("out.mp4"),
        container="mp4",
        video_codec="copy",
        audio_codec="aac",
        audio_bitrate="256k",
        audio_language="en",
        subtitle_language="en",
        embed_original_audio=True,
        end_policy="trim_audio_to_video",
        loudnorm=True,
    )

    # No video re-encode.
    assert _pairs(args, "-c:v") == ["copy"]
    # dub + original + subtitle streams mapped.
    maps = _pairs(args, "-map")
    assert maps == ["0:v:0", "1:a:0", "0:a:0?", "2:s:0"]
    # soft subtitle codec for mp4.
    assert _pairs(args, "-c:s") == ["mov_text"]
    # language tags + dispositions.
    assert "-metadata:s:a:0" in args and "language=eng" in args
    assert "-metadata:s:a:1" in args
    assert "-metadata:s:s:0" in args
    assert _pairs(args, "-disposition:a:0") == ["default"]
    assert _pairs(args, "-disposition:a:1") == ["0"]
    # dub-only loudnorm + trim + faststart.
    assert _pairs(args, "-filter:a:0") == [ffmpeg._DELIVERY_LOUDNORM_FILTER]
    assert "-shortest" in args
    assert _pairs(args, "-movflags") == ["+faststart"]
    assert args[-1] == "out.mp4"


def test_soft_subtitle_args_without_subtitle_or_original() -> None:
    args = ffmpeg.build_soft_subtitle_mux_args(
        input_video_path=Path("in.mp4"),
        dub_audio_path=Path("dub.wav"),
        subtitle_path=None,
        output_path=Path("out.mp4"),
        embed_original_audio=False,
    )
    assert _pairs(args, "-map") == ["0:v:0", "1:a:0"]
    assert "-c:s" not in args
    assert "-metadata:s:s:0" not in args
    assert "-metadata:s:a:1" not in args


def test_soft_subtitle_args_mkv_uses_srt_codec() -> None:
    args = ffmpeg.build_soft_subtitle_mux_args(
        input_video_path=Path("in.mkv"),
        dub_audio_path=Path("dub.wav"),
        subtitle_path=Path("subs.srt"),
        output_path=Path("out.mkv"),
        container="mkv",
    )
    assert _pairs(args, "-c:s") == ["srt"]


def test_soft_subtitle_args_rejects_unknown_end_policy() -> None:
    with pytest.raises(ffmpeg.FFmpegError):
        ffmpeg.build_soft_subtitle_mux_args(
            input_video_path=Path("in.mp4"),
            dub_audio_path=Path("dub.wav"),
            subtitle_path=None,
            output_path=Path("out.mp4"),
            end_policy="bogus",
        )


def test_mux_video_with_audio_tags_language(monkeypatch, tmp_path) -> None:
    captured: dict[str, list[str]] = {}
    monkeypatch.setattr(ffmpeg, "run_ffmpeg", lambda args: captured.setdefault("args", args))
    ffmpeg.mux_video_with_audio(
        input_video_path=tmp_path / "in.mp4",
        input_audio_path=tmp_path / "dub.wav",
        output_path=tmp_path / "out.mp4",
        audio_language="zh",
    )
    args = captured["args"]
    assert "-metadata:s:a:0" in args
    assert "language=zho" in args


def test_burn_subtitle_threads_crf_preset_and_language(monkeypatch, tmp_path) -> None:
    captured: dict[str, list[str]] = {}
    monkeypatch.setattr(ffmpeg, "_run_ffmpeg_with_libass", lambda args: captured.setdefault("args", args))
    ffmpeg.burn_subtitle_and_mux(
        input_video_path=tmp_path / "in.mp4",
        input_audio_path=tmp_path / "dub.wav",
        subtitle_path=tmp_path / "subs.ass",
        output_path=tmp_path / "out.mp4",
        video_codec="libx264",
        audio_language="ja",
        crf=20,
        preset="slow",
    )
    args = captured["args"]
    assert _pairs(args, "-crf") == ["20"]
    assert _pairs(args, "-preset") == ["slow"]
    assert "language=jpn" in args
