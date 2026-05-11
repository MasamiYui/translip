from __future__ import annotations

import json
import sys
from pathlib import Path

from ..types import PipelineRequest
from .ocr_bridge import ocr_detection_path, resolve_ocr_project_root
from .subprocess_runner import run_stage_command
from .subtitle_erase_detection import prepare_subtitle_erase_detection


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def resolve_erase_project_root(request: PipelineRequest) -> Path:
    if request.erase_project_root is not None:
        return Path(request.erase_project_root).expanduser().resolve()
    return (_repo_root().parent / "video-subtitle-erasure").resolve()


def resolve_erase_python(request: PipelineRequest) -> Path:
    erase_project_root = resolve_erase_project_root(request)
    venv_python = erase_project_root / ".venv" / "bin" / "python"
    if venv_python.exists():
        return venv_python
    ocr_venv_python = resolve_ocr_project_root(request) / ".venv" / "bin" / "python"
    if ocr_venv_python.exists():
        return ocr_venv_python
    return Path(sys.executable).resolve()


def subtitle_erase_output_path(request: PipelineRequest) -> Path:
    return request.output_root / "subtitle-erase" / "clean_video.mp4"


def subtitle_erase_manifest_path(request: PipelineRequest) -> Path:
    return request.output_root / "subtitle-erase" / "subtitle-erase-manifest.json"


def subtitle_erase_reuse_detection_path(request: PipelineRequest) -> Path:
    return request.output_root / "subtitle-erase" / "reuse_detection.expanded.json"


def build_subtitle_erase_command(
    request: PipelineRequest,
    *,
    reuse_detection_path: Path | None = None,
) -> list[str]:
    detection_path = reuse_detection_path or ocr_detection_path(request)
    cmd: list[str] = [
        str(resolve_erase_python(request)),
        "-m",
        "subtitle_eraser.cli",
        "--input",
        str(request.input_path),
        "--output",
        str(subtitle_erase_output_path(request)),
        "--subtitle-ocr-project",
        str(resolve_ocr_project_root(request)),
        "--reuse-detection",
        str(detection_path),
        "--debug-dir",
        str(request.output_root / "subtitle-erase" / "debug"),
        "--inpaint-backend",
        str(request.erase_backend),
        "--mode",
        str(request.erase_mode),
        "--mask-dilate-x",
        str(int(request.erase_mask_dilate_x)),
        "--mask-dilate-y",
        str(int(request.erase_mask_dilate_y)),
        "--mask-temporal-radius",
        str(int(request.erase_mask_temporal_radius)),
        "--context-frames",
        str(int(request.erase_context_frames)),
        "--event-lead-frames",
        str(int(request.erase_event_lead_frames)),
        "--event-trail-frames",
        str(int(request.erase_event_trail_frames)),
        "--cleanup-max-coverage",
        f"{float(request.erase_cleanup_max_coverage):.4f}",
        "--temporal-consensus",
        str(int(request.erase_temporal_consensus)),
        "--temporal-std-threshold",
        f"{float(request.erase_temporal_std_threshold):.4f}",
        "--inpaint-radius",
        str(int(request.erase_inpaint_radius)),
        "--inpaint-context-margin",
        str(int(request.erase_inpaint_context_margin)),
        "--lama-device",
        str(request.erase_lama_device),
    ]
    if request.erase_regions:
        for x1, y1, x2, y2 in request.erase_regions:
            cmd.extend([
                "--region",
                f"{float(x1):.4f},{float(y1):.4f},{float(x2):.4f},{float(y2):.4f}",
            ])
    if request.erase_auto_tune:
        cmd.append("--auto-tune")
    return cmd


def build_subtitle_erase_env(request: PipelineRequest) -> dict[str, str]:
    erase_project_root = resolve_erase_project_root(request)
    existing = [entry for entry in sys.path if entry]
    pythonpath = ":".join([str(erase_project_root), *existing])
    return {"PYTHONPATH": pythonpath}


def run_subtitle_erase(request: PipelineRequest, *, log_path: Path) -> dict[str, object]:
    prepared_detection_path = prepare_subtitle_erase_detection(
        ocr_detection_path(request),
        subtitle_erase_reuse_detection_path(request),
        lead_frames=request.erase_event_lead_frames,
        trail_frames=request.erase_event_trail_frames,
        video_path=Path(request.input_path),
    )
    run_stage_command(
        build_subtitle_erase_command(request, reuse_detection_path=prepared_detection_path),
        log_path=log_path,
        env_overrides=build_subtitle_erase_env(request),
    )
    manifest_path = subtitle_erase_manifest_path(request)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "status": "succeeded",
                "artifacts": {
                    "clean_video": str(subtitle_erase_output_path(request)),
                    "detection_json": str(prepared_detection_path),
                    "source_detection_json": str(ocr_detection_path(request)),
                    "debug_dir": str(request.output_root / "subtitle-erase" / "debug"),
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "manifest_path": str(manifest_path),
        "artifact_paths": [
            str(subtitle_erase_output_path(request)),
            str(prepared_detection_path),
            str(manifest_path),
        ],
        "log_path": str(log_path),
    }
