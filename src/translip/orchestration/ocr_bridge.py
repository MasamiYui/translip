from __future__ import annotations

import sys
from pathlib import Path

from ..types import PipelineRequest
from .subprocess_runner import run_stage_command


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _map_ocr_language(language: str) -> str:
    normalized = language.strip().lower()
    return {
        "zh": "ch",
        "zh-cn": "ch",
        "zh-hans": "ch",
        "ja": "japan",
        "jp": "japan",
        "ko": "korean",
    }.get(normalized, normalized or "auto")


def resolve_ocr_project_root(request: PipelineRequest) -> Path:
    """Path passed to the (still-external) subtitle-erase tool as ``--subtitle-ocr-project``.

    OCR *detection* is now fully in-tree (see ``translip.ocr``); this only remains
    for the erase bridge, which shells out to the external ``video-subtitle-erasure``
    project and hands it an OCR-project hint. Override via ``ocr_project_root``.
    """
    if request.ocr_project_root is not None:
        return Path(request.ocr_project_root).expanduser().resolve()
    return (_repo_root().parent / "subtitle-ocr").resolve()


def ocr_events_path(request: PipelineRequest) -> Path:
    return request.output_root / "ocr-detect" / "ocr_events.json"


def ocr_detection_path(request: PipelineRequest) -> Path:
    return request.output_root / "ocr-detect" / "detection.json"


def ocr_source_srt_path(request: PipelineRequest) -> Path:
    return request.output_root / "ocr-detect" / "ocr_subtitles.source.srt"


def ocr_detect_manifest_path(request: PipelineRequest) -> Path:
    return request.output_root / "ocr-detect" / "ocr-detect-manifest.json"


def build_ocr_detect_command(request: PipelineRequest) -> list[str]:
    # Run the in-tree extractor in an isolated subprocess (translip's own
    # interpreter, which carries the optional `ocr` extra). Keeping it as a
    # subprocess frees PaddleOCR's heavy models on exit, matching how every other
    # ML stage is run.
    return [
        sys.executable,
        "-m",
        "translip.ocr.extract",
        "--input",
        str(request.input_path),
        "--output-dir",
        str(request.output_root / "ocr-detect"),
        "--language",
        _map_ocr_language(request.transcription_language),
        "--sample-interval",
        "0.25",
    ]


def run_ocr_detect(request: PipelineRequest, *, log_path: Path) -> dict[str, object]:
    run_stage_command(build_ocr_detect_command(request), log_path=log_path)
    return {
        "manifest_path": str(ocr_detect_manifest_path(request)),
        "artifact_paths": [
            str(ocr_events_path(request)),
            str(ocr_detection_path(request)),
            str(ocr_source_srt_path(request)),
        ],
        "log_path": str(log_path),
    }
