from __future__ import annotations

import json
from pathlib import Path

import pytest

from translip.server.atomic_tools.adapters.video_analyze import (
    VideoAnalyzeAdapter,
    parse_vision_progress_line,
)


def test_parse_vision_progress_line() -> None:
    assert parse_vision_progress_line("__VISION_PROGRESS__\t42\tanalyzing unit 3/10") == (
        42.0,
        "analyzing unit 3/10",
    )
    assert parse_vision_progress_line("__VISION_PROGRESS__\t7") == (7.0, "analyzing video")
    assert parse_vision_progress_line("__VISION_PROGRESS__\tnan-pct\tmsg") is None
    assert parse_vision_progress_line("__ERASE_PROGRESS__\t42\tmsg") is None
    assert parse_vision_progress_line("plain log line") is None


def test_validate_params_defaults_and_task_rules() -> None:
    adapter = VideoAnalyzeAdapter()
    params = adapter.validate_params({"file_id": "f1"})
    assert params["task"] == "scene-context"
    assert params["sample_interval"] == 10.0
    assert params["frames_per_unit"] == 4
    assert params["backend"] == "auto"

    with pytest.raises(ValueError, match="question"):
        adapter.validate_params({"file_id": "f1", "task": "freeform"})
    with pytest.raises(ValueError, match="detection_file_id"):
        adapter.validate_params({"file_id": "f1", "task": "ocr-classify"})
    with pytest.raises(ValueError):
        adapter.validate_params({"file_id": "f1", "frames_per_unit": 99})
    with pytest.raises(ValueError):
        adapter.validate_params({"file_id": "f1", "task": "speaker-visual"})  # not exposed in the tool

    ok = adapter.validate_params(
        {"file_id": "f1", "task": "freeform", "question": "有几辆车?", "max_units": 5}
    )
    assert ok["question"] == "有几辆车?"


def test_run_invokes_extractor_and_collects_result(tmp_path: Path, monkeypatch) -> None:
    adapter = VideoAnalyzeAdapter()
    input_dir = tmp_path / "input"
    (input_dir / "file").mkdir(parents=True)
    (input_dir / "file" / "video.mp4").write_bytes(b"\x00")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    captured: dict[str, object] = {}

    def fake_run_stage_command(cmd, *, log_path, on_stdout_line=None, should_cancel=None):
        captured["cmd"] = cmd
        # Simulate extractor progress + artifacts.
        on_stdout_line("__VISION_PROGRESS__\t50\tanalyzing unit 1/2")
        (output_dir / "visual_context.json").write_text(
            json.dumps({"task": "scene-context", "units": []}), encoding="utf-8"
        )
        (output_dir / "scene-context-manifest.json").write_text(
            json.dumps(
                {
                    "status": "succeeded",
                    "task": "scene-context",
                    "model": {"backend": "mlx", "model": "m"},
                    "unit_count": 2,
                    "error_count": 0,
                }
            ),
            encoding="utf-8",
        )

    monkeypatch.setattr(
        "translip.server.atomic_tools.adapters.video_analyze.run_stage_command",
        fake_run_stage_command,
    )

    progress: list[tuple[float, str | None]] = []
    result = adapter.run(
        {"task": "scene-context", "sample_interval": 10.0, "frames_per_unit": 4, "lang": "zh", "backend": "auto"},
        input_dir,
        output_dir,
        lambda pct, step=None: progress.append((pct, step)),
    )

    cmd = captured["cmd"]
    assert "-m" in cmd and "translip.vision.extract" in cmd
    assert "--task" in cmd and "scene-context" in cmd
    assert result["unit_count"] == 2
    assert result["backend"] == "mlx"
    assert result["result_file"] == "visual_context.json"
    # 50% extractor progress lands mid-band (5-95).
    assert any(45.0 <= pct <= 55.0 for pct, _ in progress)


def test_run_fails_when_manifest_failed(tmp_path: Path, monkeypatch) -> None:
    adapter = VideoAnalyzeAdapter()
    input_dir = tmp_path / "input"
    (input_dir / "file").mkdir(parents=True)
    (input_dir / "file" / "video.mp4").write_bytes(b"\x00")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    def fake_run_stage_command(cmd, *, log_path, on_stdout_line=None, should_cancel=None):
        (output_dir / "scene-context-manifest.json").write_text(
            json.dumps({"status": "failed", "error": "5 consecutive unit failures"}),
            encoding="utf-8",
        )

    monkeypatch.setattr(
        "translip.server.atomic_tools.adapters.video_analyze.run_stage_command",
        fake_run_stage_command,
    )

    with pytest.raises(RuntimeError, match="consecutive"):
        adapter.run({"task": "scene-context"}, input_dir, output_dir, lambda *a, **k: None)
