from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from translip.server.atomic_tools.adapters.m3u8_to_mp4 import (
    M3u8ToMp4Adapter,
    build_ffmpeg_command,
    build_input_options,
    parse_out_time_seconds,
    progress_percent,
    _safe_output_name,
)
from translip.server.atomic_tools.schemas import M3u8ToMp4ToolRequest
from translip.utils.ffmpeg import ffmpeg_binary


# --- schema validation -------------------------------------------------------

def test_schema_accepts_url_only() -> None:
    dumped = M3u8ToMp4ToolRequest(url="https://host/path/index.m3u8").model_dump()
    assert dumped["url"] == "https://host/path/index.m3u8"
    assert dumped["playlist_file_id"] is None
    assert dumped["mode"] == "copy" and dumped["output_format"] == "mp4"


def test_schema_accepts_file_only() -> None:
    dumped = M3u8ToMp4ToolRequest(playlist_file_id="abc").model_dump()
    assert dumped["playlist_file_id"] == "abc"
    assert dumped["url"] is None


def test_schema_trims_url() -> None:
    dumped = M3u8ToMp4ToolRequest(url="  https://host/v.m3u8  ").model_dump()
    assert dumped["url"] == "https://host/v.m3u8"


@pytest.mark.parametrize(
    "params",
    [
        {},  # neither
        {"url": "https://host/v.m3u8", "playlist_file_id": "abc"},  # both
        {"url": "ftp://host/v.m3u8"},  # wrong scheme
        {"url": "/local/path.m3u8"},  # not a URL
    ],
)
def test_schema_rejects_bad_source(params: dict) -> None:
    with pytest.raises(ValueError):
        M3u8ToMp4ToolRequest(**params)


# --- pure command builders ---------------------------------------------------

def test_remote_input_options_exclude_file_protocol() -> None:
    opts = build_input_options(is_local=False, user_agent="UA", referer="https://ref")
    whitelist = opts[opts.index("-protocol_whitelist") + 1]
    assert "file" not in whitelist.split(",")
    assert "crypto" in whitelist and "https" in whitelist
    assert "-allowed_extensions" not in opts  # only for local playlists
    assert opts[opts.index("-user_agent") + 1] == "UA"
    assert "Referer: https://ref\r\n" == opts[opts.index("-headers") + 1]


def test_local_input_options_allow_file_and_extensions() -> None:
    opts = build_input_options(is_local=True, start_sec=12.0)
    whitelist = opts[opts.index("-protocol_whitelist") + 1]
    assert "file" in whitelist.split(",")
    assert opts[opts.index("-allowed_extensions") + 1] == "ALL"
    assert opts[opts.index("-ss") + 1] == "12.000"


def test_headers_merge_referer_and_extra_lines() -> None:
    opts = build_input_options(
        is_local=False, referer="https://ref", headers="Cookie: a=1\n\nOrigin: https://o"
    )
    block = opts[opts.index("-headers") + 1]
    assert block == "Referer: https://ref\r\nCookie: a=1\r\nOrigin: https://o\r\n"


def test_copy_command_remuxes_with_faststart() -> None:
    cmd = build_ffmpeg_command(
        ffmpeg="ffmpeg",
        input_arg="https://h/v.m3u8",
        is_local=False,
        params={"mode": "copy", "output_format": "mp4", "duration_limit_sec": 30},
        output_path=Path("/tmp/o.mp4"),
    )
    assert cmd[:1] == ["ffmpeg"]
    assert "-c" in cmd and cmd[cmd.index("-c") + 1] == "copy"
    assert cmd[cmd.index("-t") + 1] == "30.000"
    assert "+faststart" in cmd
    assert cmd[-4:] == ["-progress", "pipe:1", "-nostats", "/tmp/o.mp4"]
    assert "libx264" not in cmd


def test_transcode_command_reencodes_and_mkv_skips_faststart() -> None:
    cmd = build_ffmpeg_command(
        ffmpeg="ffmpeg",
        input_arg="/x/v.m3u8",
        is_local=True,
        params={
            "mode": "transcode",
            "output_format": "mkv",
            "crf": 18,
            "preset": "fast",
            "audio_bitrate": "128k",
        },
        output_path=Path("/tmp/o.mkv"),
    )
    assert cmd[cmd.index("-c:v") + 1] == "libx264"
    assert cmd[cmd.index("-crf") + 1] == "18"
    assert cmd[cmd.index("-preset") + 1] == "fast"
    assert cmd[cmd.index("-b:a") + 1] == "128k"
    assert "+faststart" not in cmd  # mkv container


def test_safe_output_name_sanitizes_and_derives() -> None:
    assert _safe_output_name(None, "https://h/p/My Video.m3u8?token=1", "mp4") == "My Video.mp4"
    assert _safe_output_name("clip.mp4", "x", "mp4") == "clip.mp4"
    assert _safe_output_name(None, "/a/index.m3u8", "mkv") == "index.mkv"
    assert _safe_output_name("../../etc/passwd", "x", "mp4") == "passwd.mp4"


def test_progress_helpers() -> None:
    assert parse_out_time_seconds("out_time_us=4500000") == pytest.approx(4.5)
    assert parse_out_time_seconds("out_time_us=N/A") is None
    assert parse_out_time_seconds("frame=10") is None
    assert progress_percent(50, 100) == pytest.approx(52.5)
    # Unknown total stays within the working band and never reaches 95.
    live = progress_percent(30, None)
    assert 10.0 < live < 95.0


# --- real ffmpeg end-to-end (skipped if HLS generation is unavailable) --------

def _make_local_hls(slot_dir: Path) -> bool:
    slot_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg_binary(), "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=15",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac",
        "-f", "hls", "-hls_time", "1", "-hls_list_size", "0",
        str(slot_dir / "playlist.m3u8"),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except Exception:
        return False
    return proc.returncode == 0 and (slot_dir / "playlist.m3u8").exists()


def test_local_playlist_converts_to_mp4(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    if not _make_local_hls(input_dir / "playlist_file"):
        pytest.skip("ffmpeg build cannot generate H.264/AAC HLS for the e2e test")

    output_dir = tmp_path / "output"
    result = M3u8ToMp4Adapter().run(
        M3u8ToMp4ToolRequest(playlist_file_id="local").model_dump(),
        input_dir,
        output_dir,
        lambda *_a, **_k: None,
    )

    out_path = output_dir / result["output_file"]
    assert out_path.exists() and out_path.stat().st_size > 0
    assert result["output_file"].endswith(".mp4")
    assert result["source_type"] == "file"
    assert result.get("video_codec") == "h264"
    assert result.get("width") == 320
