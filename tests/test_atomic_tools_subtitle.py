from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import translip.server.atomic_tools as _atomic_tools  # noqa: F401  (triggers adapter registration)
from translip.server.atomic_tools.adapters.subtitle_erase import (
    PRESETS,
    SubtitleEraseAdapter,
    build_eraser_command,
    resolve_preset_params,
)
from translip.server.atomic_tools.adapters.subtitle_detect import SubtitleDetectAdapter
from translip.server.atomic_tools.schemas import (
    SubtitleDetectToolRequest,
    SubtitleEraseToolRequest,
)


# ---------------------------------------------------------------------------
# Test 1: preset → resolved parameters mapping
# ---------------------------------------------------------------------------


def test_resolve_preset_params_maps_each_preset_to_its_profile() -> None:
    for preset_name, profile in PRESETS.items():
        resolved = resolve_preset_params({"preset": preset_name})
        assert resolved["backend"] == profile.backend
        assert resolved["mask_dilate_x"] == profile.mask_dilate_x
        assert resolved["mask_dilate_y"] == profile.mask_dilate_y
        assert resolved["mask_temporal_radius"] == profile.mask_temporal_radius
        assert resolved["cleanup_max_coverage"] == profile.cleanup_max_coverage
        assert resolved["temporal_consensus"] == profile.temporal_consensus
        assert resolved["temporal_std_threshold"] == profile.temporal_std_threshold
        assert resolved["lama_device"] == profile.lama_device


def test_resolve_preset_params_advanced_overrides_take_priority() -> None:
    resolved = resolve_preset_params({
        "preset": "fast",
        "backend": "lama",
        "mask_dilate_x": 99,
        "cleanup_max_coverage": 0.05,
        "auto_tune": True,
    })
    assert resolved["backend"] == "lama"
    assert resolved["mask_dilate_x"] == 99
    assert resolved["cleanup_max_coverage"] == 0.05
    assert resolved["auto_tune"] is True
    # Untouched fields stay on the preset baseline.
    assert resolved["mask_temporal_radius"] == PRESETS["fast"].mask_temporal_radius


# ---------------------------------------------------------------------------
# Test 2: schema validation - subtitle-erase requires detection_file_id
# ---------------------------------------------------------------------------


def test_subtitle_erase_request_requires_detection_file_id() -> None:
    with pytest.raises(Exception):
        SubtitleEraseToolRequest(file_id="abc")
    request = SubtitleEraseToolRequest(file_id="abc", detection_file_id="det")
    assert request.preset == "fast"


def test_subtitle_erase_request_accepts_advanced_overrides() -> None:
    request = SubtitleEraseToolRequest(
        file_id="abc",
        detection_file_id="det",
        preset="quality",
        backend="lama",
        regions=[(0.0, 0.7, 1.0, 0.95)],
        mask_dilate_x=20,
        auto_tune=True,
    )
    assert request.preset == "quality"
    assert request.backend == "lama"
    assert request.regions == [(0.0, 0.7, 1.0, 0.95)]
    assert request.mask_dilate_x == 20
    assert request.auto_tune is True


def test_subtitle_detect_request_defaults() -> None:
    request = SubtitleDetectToolRequest(file_id="abc")
    assert request.language == "ch"
    assert request.position_mode == "bottom"
    assert request.roi_bottom_ratio == 0.34
    assert request.preview_frames == 3


# ---------------------------------------------------------------------------
# Test 3: build_eraser_command produces a CLI matching the resolved profile
# ---------------------------------------------------------------------------


def test_build_eraser_command_includes_preset_parameters(tmp_path: Path) -> None:
    resolved = resolve_preset_params({"preset": "balanced"})
    cmd = build_eraser_command(
        input_video=tmp_path / "in.mp4",
        output_video=tmp_path / "out.mp4",
        detection_json=tmp_path / "detection.json",
        debug_dir=tmp_path / "debug",
        resolved=resolved,
    )
    assert "--inpaint-backend" in cmd
    assert cmd[cmd.index("--inpaint-backend") + 1] == "flow-guided"
    assert cmd[cmd.index("--mask-temporal-radius") + 1] == str(PRESETS["balanced"].mask_temporal_radius)
    assert cmd[cmd.index("--cleanup-max-coverage") + 1] == f"{PRESETS['balanced'].cleanup_max_coverage:.4f}"
    assert "--auto-tune" not in cmd


def test_build_eraser_command_appends_regions_and_auto_tune(tmp_path: Path) -> None:
    resolved = resolve_preset_params({
        "preset": "fast",
        "regions": [(0.0, 0.7, 1.0, 0.95)],
        "auto_tune": True,
    })
    cmd = build_eraser_command(
        input_video=tmp_path / "in.mp4",
        output_video=tmp_path / "out.mp4",
        detection_json=tmp_path / "detection.json",
        debug_dir=tmp_path / "debug",
        resolved=resolved,
    )
    assert "--auto-tune" in cmd
    region_index = cmd.index("--region")
    assert cmd[region_index + 1] == "0.0000,0.7000,1.0000,0.9500"


# ---------------------------------------------------------------------------
# Test 4: HTTP endpoint - subtitle-erase rejects requests without detection
# ---------------------------------------------------------------------------


def test_subtitle_erase_http_rejects_missing_detection_file_id(tmp_path: Path, monkeypatch) -> None:
    from translip.server.app import app
    from translip.server.atomic_tools.job_manager import JobManager
    from translip.server.routes import atomic_tools as atomic_tools_route

    manager = JobManager(root=tmp_path / "atomic-tools")
    monkeypatch.setattr(atomic_tools_route, "job_manager", manager)

    client = TestClient(app)
    upload_response = client.post(
        "/api/atomic-tools/upload",
        files={"file": ("demo.mp4", BytesIO(b"data"), "video/mp4")},
    )
    file_id = upload_response.json()["file_id"]

    response = client.post(
        "/api/atomic-tools/subtitle-erase/run",
        json={"file_id": file_id},
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Test 5: SubtitleEraseAdapter.run is mocked end-to-end (no real FFmpeg/LaMa)
# ---------------------------------------------------------------------------


class _StubProgress:
    def __init__(self) -> None:
        self.events: list[tuple[float, str | None]] = []

    def __call__(self, percent: float, step: str | None = None) -> None:
        self.events.append((percent, step))


def test_subtitle_erase_adapter_run_invokes_command_and_writes_report(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    file_dir = input_dir / "file"
    detection_dir = input_dir / "detection_file"
    file_dir.mkdir(parents=True)
    detection_dir.mkdir(parents=True)
    video_path = file_dir / "in.mp4"
    video_path.write_bytes(b"\x00" * 16)
    detection_path = detection_dir / "detection.json"
    detection_path.write_text(json.dumps({"events": []}), encoding="utf-8")

    captured: dict[str, object] = {}

    def fake_run_stage_command(cmd, *, log_path, env_overrides=None):
        captured["cmd"] = list(cmd)
        captured["env"] = dict(env_overrides or {})
        # Simulate the eraser writing its output video.
        out_video = Path(cmd[cmd.index("--output") + 1])
        out_video.parent.mkdir(parents=True, exist_ok=True)
        out_video.write_bytes(b"\x00" * 16)

    def fake_metrics(*_args, **_kwargs):
        return {"sampled_frames": 0, "band_diff_mean": 0.0, "spill_mean": 0.0}

    adapter = SubtitleEraseAdapter()
    params = adapter.validate_params({
        "file_id": "x",
        "detection_file_id": "y",
        "preset": "fast",
    })

    with patch(
        "translip.server.atomic_tools.adapters.subtitle_erase.run_stage_command",
        side_effect=fake_run_stage_command,
    ), patch(
        "translip.server.atomic_tools.adapters.subtitle_erase._quick_metrics",
        side_effect=fake_metrics,
    ):
        result = adapter.run(params, input_dir, output_dir, _StubProgress())

    assert result["erased_file"] == "erased.mp4"
    assert result["preset"] == "fast"
    assert result["backend"] == "telea"
    assert (output_dir / "report.json").exists()
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    assert report["preset"] == "fast"
    assert report["resolved_parameters"]["backend"] == "telea"
    cmd = captured["cmd"]
    assert "--inpaint-backend" in cmd
    assert cmd[cmd.index("--inpaint-backend") + 1] == "telea"


# ---------------------------------------------------------------------------
# Test 6: ToolSpec registration sanity (icons / accept_formats / size)
# ---------------------------------------------------------------------------


def test_subtitle_tools_are_registered_with_video_category() -> None:
    from translip.server.atomic_tools.registry import TOOL_REGISTRY

    detect = TOOL_REGISTRY["subtitle-detect"]
    erase = TOOL_REGISTRY["subtitle-erase"]
    assert detect.category == "video"
    assert erase.category == "video"
    assert detect.max_file_size_mb == 2048
    assert erase.max_file_size_mb == 2048
    assert ".mp4" in detect.accept_formats
    assert ".json" in erase.accept_formats
