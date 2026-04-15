from __future__ import annotations

import json
import sys
from pathlib import Path

from ..types import PipelineRequest
from .ocr_bridge import ocr_detection_path, resolve_ocr_project_root
from .subprocess_runner import run_stage_command


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


def build_subtitle_erase_command(request: PipelineRequest) -> list[str]:
    return [
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
        str(ocr_detection_path(request)),
        "--debug-dir",
        str(request.output_root / "subtitle-erase" / "debug"),
    ]


def build_subtitle_erase_env(request: PipelineRequest) -> dict[str, str]:
    erase_project_root = resolve_erase_project_root(request)
    existing = [entry for entry in sys.path if entry]
    pythonpath = ":".join([str(erase_project_root), *existing])
    return {"PYTHONPATH": pythonpath}


def run_subtitle_erase(request: PipelineRequest, *, log_path: Path) -> dict[str, object]:
    run_stage_command(
        build_subtitle_erase_command(request),
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
                    "detection_json": str(ocr_detection_path(request)),
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
        "artifact_paths": [str(subtitle_erase_output_path(request)), str(manifest_path)],
        "log_path": str(log_path),
    }
