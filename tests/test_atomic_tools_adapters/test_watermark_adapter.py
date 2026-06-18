from __future__ import annotations

from pathlib import Path


def _arg_value(args: list[str], flag: str) -> str | None:
    for i, tok in enumerate(args):
        if tok == flag and i + 1 < len(args):
            return args[i + 1]
    return None


def _patch_run(monkeypatch, captured: dict, *, write_output: bool = True):
    """Stub run_stage_command: capture the argv and create the output file."""

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        if write_output:
            Path(command[-1]).write_bytes(b"encoded")

    monkeypatch.setattr(
        "translip.server.atomic_tools.adapters.watermark.run_stage_command", fake_run
    )
    monkeypatch.setattr(
        "translip.server.atomic_tools.adapters.watermark.ffmpeg_binary", lambda: "ffmpeg"
    )
    # Probe is best-effort; force "unknown duration" so tests don't shell out.
    monkeypatch.setattr(
        "translip.server.atomic_tools.adapters.watermark.WatermarkAdapter._probe_duration",
        staticmethod(lambda _path: None),
    )


def test_watermark_image_mode_builds_overlay_command(tmp_path: Path, monkeypatch) -> None:
    from translip.server.atomic_tools.adapters.watermark import WatermarkAdapter

    video_path = tmp_path / "input" / "video_file" / "clip.mp4"
    image_path = tmp_path / "input" / "image_file" / "logo.png"
    video_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(b"video")
    image_path.write_bytes(b"png")
    output_dir = tmp_path / "output"

    captured: dict = {}
    _patch_run(monkeypatch, captured)

    result = WatermarkAdapter().run(
        {
            "video_file_id": "video",
            "image_file_id": "logo",
            "mode": "image",
            "position": "top-left",
            "margin": 32,
            "opacity": 0.5,
            "scale": 0.2,
            "quality": "high",
        },
        tmp_path / "input",
        output_dir,
        lambda *_a, **_k: None,
    )

    assert (output_dir / "output.mp4").read_bytes() == b"encoded"
    assert result == {"output_file": "output.mp4", "mode": "image", "position": "top-left"}

    cmd = captured["command"]
    assert cmd[0] == "ffmpeg"
    # Both video and image inputs are mapped, in order.
    assert [_arg_value(cmd, "-i")] and cmd.count("-i") == 2
    inputs = [cmd[i + 1] for i, t in enumerate(cmd) if t == "-i"]
    assert inputs == [str(video_path), str(image_path)]
    fc = _arg_value(cmd, "-filter_complex")
    assert "colorchannelmixer=aa=0.5000" in fc
    assert "scale=iw*0.2000:-1[wm]" in fc
    assert "overlay=32:32" in fc  # top-left → x=margin, y=margin
    # quality=high → crf 16 / preset slow
    assert _arg_value(cmd, "-crf") == "16"
    assert _arg_value(cmd, "-preset") == "slow"
    # Streaming progress requested; output is last.
    assert _arg_value(cmd, "-progress") == "pipe:1"
    assert cmd[-1] == str(output_dir / "output.mp4")
    # Cancellation predicate is threaded through.
    assert "should_cancel" in captured["kwargs"]


def test_watermark_text_mode_builds_drawtext_command(tmp_path: Path, monkeypatch) -> None:
    from translip.server.atomic_tools.adapters.watermark import WatermarkAdapter

    video_path = tmp_path / "input" / "video_file" / "clip.mp4"
    video_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(b"video")
    output_dir = tmp_path / "output"

    captured: dict = {}
    _patch_run(monkeypatch, captured)

    result = WatermarkAdapter().run(
        {
            "video_file_id": "video",
            "mode": "text",
            "text": "Hello:World",
            "position": "bottom-right",
            "margin": 24,
            "opacity": 0.9,
            "font_size": 48,
            "font_color": "yellow",
            "stroke_color": "black@0.5",
            "stroke_width": 3,
            "quality": "balanced",
        },
        tmp_path / "input",
        output_dir,
        lambda *_a, **_k: None,
    )

    assert (output_dir / "output.mp4").read_bytes() == b"encoded"
    assert result == {"output_file": "output.mp4", "mode": "text", "position": "bottom-right"}

    cmd = captured["command"]
    assert cmd.count("-i") == 1  # no image input in text mode
    vf = _arg_value(cmd, "-vf")
    assert vf.startswith("drawtext=")
    assert "text='Hello\\:World'" in vf  # colon escaped
    assert "fontsize=48" in vf
    assert "fontcolor=yellow@0.9000" in vf
    assert "bordercolor=black@0.5" in vf
    assert "borderw=3" in vf
    # quality=balanced → crf 18 / preset medium
    assert _arg_value(cmd, "-crf") == "18"
    assert _arg_value(cmd, "-preset") == "medium"


def test_watermark_propagates_ffmpeg_failure(tmp_path: Path, monkeypatch) -> None:
    import pytest

    from translip.orchestration.subprocess_runner import StageSubprocessError
    from translip.server.atomic_tools.adapters.watermark import WatermarkAdapter

    video_path = tmp_path / "input" / "video_file" / "clip.mp4"
    video_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(b"video")

    def fake_run(command, **kwargs):
        raise StageSubprocessError(
            command=["ffmpeg"],
            returncode=1,
            log_path=tmp_path / "ffmpeg.log",
            tail=["Invalid data found"],
        )

    monkeypatch.setattr(
        "translip.server.atomic_tools.adapters.watermark.run_stage_command", fake_run
    )
    monkeypatch.setattr(
        "translip.server.atomic_tools.adapters.watermark.ffmpeg_binary", lambda: "ffmpeg"
    )
    monkeypatch.setattr(
        "translip.server.atomic_tools.adapters.watermark.WatermarkAdapter._probe_duration",
        staticmethod(lambda _path: None),
    )

    with pytest.raises(RuntimeError, match="Invalid data found"):
        WatermarkAdapter().run(
            {"video_file_id": "video", "mode": "text", "text": "hi"},
            tmp_path / "input",
            tmp_path / "output",
            lambda *_a, **_k: None,
        )


def test_watermark_validate_rejects_text_mode_without_text() -> None:
    import pytest

    from translip.server.atomic_tools.adapters.watermark import WatermarkAdapter

    with pytest.raises(ValueError):
        WatermarkAdapter().validate_params(
            {"video_file_id": "video", "mode": "text", "text": "   "}
        )


def test_watermark_validate_rejects_image_mode_without_image_id() -> None:
    import pytest

    from translip.server.atomic_tools.adapters.watermark import WatermarkAdapter

    with pytest.raises(ValueError):
        WatermarkAdapter().validate_params({"video_file_id": "video", "mode": "image"})


def test_watermark_validate_accepts_valid_colors() -> None:
    from translip.server.atomic_tools.adapters.watermark import WatermarkAdapter

    for color in ("white", "#ffcc00", "#FFCC0080", "black@0.6", "yellow@1"):
        params = WatermarkAdapter().validate_params(
            {
                "video_file_id": "video",
                "mode": "text",
                "text": "hi",
                "font_color": color,
                "stroke_color": color,
            }
        )
        assert params["font_color"] == color


def test_watermark_validate_rejects_filter_breaking_colors() -> None:
    import pytest

    from translip.server.atomic_tools.adapters.watermark import WatermarkAdapter

    for bad in ("white:x=0", "rgb(0,0,0)", "black' ", "red;drawbox"):
        with pytest.raises(ValueError):
            WatermarkAdapter().validate_params(
                {
                    "video_file_id": "video",
                    "mode": "text",
                    "text": "hi",
                    "font_color": bad,
                }
            )


def test_watermark_validate_ignores_colors_in_image_mode() -> None:
    # Colors are text-only; an odd color must not block an image-mode job.
    from translip.server.atomic_tools.adapters.watermark import WatermarkAdapter

    params = WatermarkAdapter().validate_params(
        {
            "video_file_id": "video",
            "image_file_id": "logo",
            "mode": "image",
            "font_color": "white:x=0",
        }
    )
    assert params["mode"] == "image"
