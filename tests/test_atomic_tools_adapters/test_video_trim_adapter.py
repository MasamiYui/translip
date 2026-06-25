from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from translip.server.atomic_tools.adapters.video_trim import (
    VideoTrimAdapter,
    build_trim_command,
    compute_effective_duration,
)
from translip.server.atomic_tools.schemas import VideoTrimToolRequest


def _arg_value(args: list[str], flag: str) -> str | None:
    for i, tok in enumerate(args):
        if tok == flag and i + 1 < len(args):
            return args[i + 1]
    return None


# --- schema validation -------------------------------------------------------

def test_schema_defaults() -> None:
    dumped = VideoTrimToolRequest(file_id="v").model_dump()
    assert dumped["start_sec"] == 0.0
    assert dumped["end_sec"] is None and dumped["duration_sec"] is None
    assert dumped["mode"] == "accurate"
    assert dumped["output_format"] == "mp4"
    assert dumped["quality"] == "balanced"


def test_schema_accepts_duration_only() -> None:
    dumped = VideoTrimToolRequest(file_id="v", start_sec=2, duration_sec=8).model_dump()
    assert dumped["start_sec"] == 2 and dumped["duration_sec"] == 8
    assert dumped["end_sec"] is None


def test_schema_rejects_both_bounds() -> None:
    with pytest.raises(ValueError):
        VideoTrimToolRequest(file_id="v", end_sec=5, duration_sec=3)


@pytest.mark.parametrize("start,end", [(10, 5), (5, 5)])
def test_schema_rejects_non_positive_window(start: float, end: float) -> None:
    with pytest.raises(ValueError):
        VideoTrimToolRequest(file_id="v", start_sec=start, end_sec=end)


def test_schema_rejects_window_below_min_gap() -> None:
    # A 50ms window is below VIDEO_TRIM_MIN_WINDOW_SEC (0.1s) — must be rejected
    # so the backend never produces a 0-frame clip when the UI is bypassed.
    with pytest.raises(ValueError):
        VideoTrimToolRequest(file_id="v", start_sec=1.0, end_sec=1.05)


def test_schema_rejects_duration_below_min_gap() -> None:
    with pytest.raises(ValueError):
        VideoTrimToolRequest(file_id="v", duration_sec=0.05)


# --- effective duration ------------------------------------------------------

def test_effective_duration_prefers_explicit_duration() -> None:
    assert compute_effective_duration(5.0, None, 10.0) == 10.0


def test_effective_duration_from_end_minus_start() -> None:
    assert compute_effective_duration(5.0, 12.0, None) == 7.0


def test_effective_duration_open_ended_is_none() -> None:
    assert compute_effective_duration(5.0, None, None) is None


# --- pure command builder ----------------------------------------------------

def test_fast_command_stream_copies_and_seeks_before_input() -> None:
    cmd = build_trim_command(
        ffmpeg="ffmpeg",
        input_path=Path("in.mp4"),
        output_path=Path("clip.mp4"),
        mode="fast",
        start_sec=5.0,
        duration_sec=10.0,
        container="mp4",
        crf=18,
        preset="medium",
    )
    # Input-side seek: -ss must precede -i.
    assert cmd.index("-ss") < cmd.index("-i")
    assert _arg_value(cmd, "-ss") == "5.000"
    # Window length is an output-side -t duration, never -to.
    assert _arg_value(cmd, "-t") == "10.000"
    assert "-to" not in cmd
    # Stream copy, all streams kept, no re-encode.
    assert _arg_value(cmd, "-c") == "copy"
    assert _arg_value(cmd, "-map") == "0"
    assert "libx264" not in cmd
    # mp4 gets faststart; progress + output trail.
    assert "+faststart" in cmd
    assert _arg_value(cmd, "-progress") == "pipe:1"
    assert cmd[-1] == "clip.mp4"


def test_accurate_command_reencodes_maps_optional_audio_and_respects_container() -> None:
    cmd = build_trim_command(
        ffmpeg="ffmpeg",
        input_path=Path("in.mp4"),
        output_path=Path("clip.mkv"),
        mode="accurate",
        start_sec=0.0,
        duration_sec=None,
        container="mkv",
        crf=16,
        preset="slow",
    )
    assert "libx264" in cmd
    assert _arg_value(cmd, "-crf") == "16"
    assert _arg_value(cmd, "-preset") == "slow"
    # Primary video + optional (?) audio mapping.
    maps = [cmd[i + 1] for i, tok in enumerate(cmd) if tok == "-map"]
    assert maps == ["0:v:0", "0:a:0?"]
    # start=0 → no seek; open-ended → no -t; mkv → no faststart.
    assert "-ss" not in cmd
    assert "-t" not in cmd
    assert "+faststart" not in cmd


# --- adapter.run (mocked ffmpeg) ---------------------------------------------

def _patch_run(monkeypatch, captured: dict) -> None:
    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        Path(command[-1]).write_bytes(b"clip")

    module = "translip.server.atomic_tools.adapters.video_trim"
    monkeypatch.setattr(f"{module}.run_stage_command", fake_run)
    monkeypatch.setattr(f"{module}.ffmpeg_binary", lambda: "ffmpeg")
    # Probes are best-effort; stub them so the test never shells out to ffprobe.
    monkeypatch.setattr(
        f"{module}.VideoTrimAdapter._probe_duration", staticmethod(lambda _p: None)
    )
    monkeypatch.setattr(
        f"{module}.VideoTrimAdapter._probe_output", staticmethod(lambda _p: {})
    )


def test_run_builds_command_and_returns_result(tmp_path: Path, monkeypatch) -> None:
    src = tmp_path / "input" / "file" / "src.mp4"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"video")
    output_dir = tmp_path / "output"

    captured: dict = {}
    _patch_run(monkeypatch, captured)

    result = VideoTrimAdapter().run(
        {
            "file_id": "src",
            "start_sec": 3.0,
            "end_sec": 8.0,
            "mode": "fast",
            "output_format": "mp4",
            "quality": "balanced",
        },
        tmp_path / "input",
        output_dir,
        lambda *_a, **_k: None,
    )

    assert (output_dir / "clip.mp4").read_bytes() == b"clip"
    assert result["output_file"] == "clip.mp4"
    assert result["mode"] == "fast"
    assert result["start_sec"] == 3.0
    assert result["end_sec"] == 8.0
    assert result["requested_duration_sec"] == 5.0
    # end_sec (8) - start_sec (3) == 5s output window.
    assert _arg_value(captured["command"], "-t") == "5.000"
    assert _arg_value(captured["command"], "-ss") == "3.000"
    assert "should_cancel" in captured["kwargs"]


def test_run_raises_when_no_output_produced(tmp_path: Path, monkeypatch) -> None:
    src = tmp_path / "input" / "file" / "src.mp4"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"video")

    module = "translip.server.atomic_tools.adapters.video_trim"
    monkeypatch.setattr(f"{module}.run_stage_command", lambda *_a, **_k: None)
    monkeypatch.setattr(f"{module}.ffmpeg_binary", lambda: "ffmpeg")
    monkeypatch.setattr(
        f"{module}.VideoTrimAdapter._probe_duration", staticmethod(lambda _p: None)
    )

    with pytest.raises(RuntimeError, match="produced no output"):
        VideoTrimAdapter().run(
            {"file_id": "src", "start_sec": 0.0, "duration_sec": 2.0},
            tmp_path / "input",
            tmp_path / "output",
            lambda *_a, **_k: None,
        )


def test_run_propagates_ffmpeg_failure(tmp_path: Path, monkeypatch) -> None:
    from translip.orchestration.subprocess_runner import StageSubprocessError

    src = tmp_path / "input" / "file" / "src.mp4"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"video")

    def fake_run(command, **kwargs):
        raise StageSubprocessError(
            command=["ffmpeg"],
            returncode=1,
            log_path=tmp_path / "ffmpeg.log",
            tail=["Invalid data found"],
        )

    module = "translip.server.atomic_tools.adapters.video_trim"
    monkeypatch.setattr(f"{module}.run_stage_command", fake_run)
    monkeypatch.setattr(f"{module}.ffmpeg_binary", lambda: "ffmpeg")
    monkeypatch.setattr(
        f"{module}.VideoTrimAdapter._probe_duration", staticmethod(lambda _p: None)
    )

    with pytest.raises(RuntimeError, match="Invalid data found"):
        VideoTrimAdapter().run(
            {"file_id": "src", "start_sec": 0.0, "duration_sec": 2.0},
            tmp_path / "input",
            tmp_path / "output",
            lambda *_a, **_k: None,
        )


# --- real ffmpeg integration (skipped when ffmpeg is absent) -----------------

@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")
def test_trim_really_cuts_a_clip(tmp_path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg is not None
    src = tmp_path / "input" / "file" / "src.mp4"
    src.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc=duration=3:size=320x240:rate=10",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
            str(src),
        ],
        check=True,
    )

    output_dir = tmp_path / "output"
    result = VideoTrimAdapter().run(
        {
            "file_id": "src",
            "start_sec": 1.0,
            "end_sec": 2.0,
            "mode": "accurate",
            "output_format": "mp4",
            "quality": "balanced",
        },
        tmp_path / "input",
        output_dir,
        lambda *_a, **_k: None,
    )

    clip = output_dir / "clip.mp4"
    assert clip.exists() and clip.stat().st_size > 0
    assert result["output_file"] == "clip.mp4"
    assert result["width"] == 320 and result["height"] == 240
    # A 1.0s window — allow generous tolerance for keyframe/codec padding.
    assert abs(float(result["duration_sec"]) - 1.0) < 0.5
