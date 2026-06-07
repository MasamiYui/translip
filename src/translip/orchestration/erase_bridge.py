from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from ..types import PipelineRequest
from .ocr_bridge import ocr_detection_path
from .subprocess_runner import run_stage_command
from .subtitle_erase_detection import prepare_subtitle_erase_detection

if TYPE_CHECKING:
    from .monitor import PipelineMonitor

# Must match translip.erase.extract.PROGRESS_PREFIX (kept as a literal here so
# this module stays free of the heavy erase stack at import time).
_ERASE_PROGRESS_PREFIX = "__ERASE_PROGRESS__"


def subtitle_erase_dir(request: PipelineRequest) -> Path:
    return request.output_root / "subtitle-erase"


def subtitle_erase_output_path(request: PipelineRequest) -> Path:
    return subtitle_erase_dir(request) / "clean_video.mp4"


def subtitle_erase_manifest_path(request: PipelineRequest) -> Path:
    return subtitle_erase_dir(request) / "subtitle-erase-manifest.json"


def subtitle_erase_reuse_detection_path(request: PipelineRequest) -> Path:
    return subtitle_erase_dir(request) / "reuse_detection.expanded.json"


def build_subtitle_erase_command(request: PipelineRequest, *, detection_path: Path) -> list[str]:
    # Run the in-tree eraser in an isolated subprocess (translip's own
    # interpreter), freeing the heavy inpainting models on exit — same pattern
    # as ocr-detect and every other ML stage.
    cmd: list[str] = [
        sys.executable,
        "-m",
        "translip.erase.extract",
        "--input",
        str(request.input_path),
        "--detection",
        str(detection_path),
        "--output-dir",
        str(subtitle_erase_dir(request)),
        "--backend",
        str(request.erase_backend),
        "--device",
        str(request.erase_device),
        "--mask-dilate-x",
        str(int(request.erase_mask_dilate_x)),
        "--mask-dilate-y",
        str(int(request.erase_mask_dilate_y)),
        "--neighbor-stride",
        str(int(request.erase_neighbor_stride)),
        "--reference-length",
        str(int(request.erase_reference_length)),
        "--max-load",
        str(int(request.erase_max_load)),
    ]
    if request.erase_regions:
        for x1, y1, x2, y2 in request.erase_regions:
            cmd.extend(["--region", f"{float(x1):.4f},{float(y1):.4f},{float(x2):.4f},{float(y2):.4f}"])
    return cmd


def parse_erase_progress_line(line: str) -> tuple[float, str] | None:
    """Parse one `__ERASE_PROGRESS__\\t<pct>\\t<message>` line from the extractor."""
    if not line.startswith(_ERASE_PROGRESS_PREFIX + "\t"):
        return None
    parts = line.split("\t", 2)
    if len(parts) < 2:
        return None
    try:
        percent = float(parts[1])
    except ValueError:
        return None
    return percent, parts[2] if len(parts) > 2 else "erasing subtitles"


def _build_progress_handler(monitor: "PipelineMonitor | None") -> Callable[[str], None] | None:
    if monitor is None:
        return None

    def _handle(line: str) -> None:
        parsed = parse_erase_progress_line(line)
        if parsed is not None:
            monitor.update_stage_progress("subtitle-erase", parsed[0], parsed[1])

    return _handle


def run_subtitle_erase(
    request: PipelineRequest,
    *,
    log_path: Path,
    monitor: "PipelineMonitor | None" = None,
    should_cancel: Callable[[], bool] | None = None,
) -> dict[str, object]:
    # Expand the OCR detection (lead/trail padding + visual-fallback events) and
    # hand the expanded detection.json to the in-tree extractor.
    prepared_detection_path = prepare_subtitle_erase_detection(
        ocr_detection_path(request),
        subtitle_erase_reuse_detection_path(request),
        lead_frames=request.erase_event_lead_frames,
        trail_frames=request.erase_event_trail_frames,
        video_path=Path(request.input_path),
    )
    run_stage_command(
        build_subtitle_erase_command(request, detection_path=prepared_detection_path),
        log_path=log_path,
        on_stdout_line=_build_progress_handler(monitor),
        should_cancel=should_cancel,
    )
    # The extractor writes subtitle-erase-manifest.json itself (like ocr-detect).
    return {
        "manifest_path": str(subtitle_erase_manifest_path(request)),
        "artifact_paths": [
            str(subtitle_erase_output_path(request)),
            str(prepared_detection_path),
            str(subtitle_erase_manifest_path(request)),
        ],
        "log_path": str(log_path),
    }
