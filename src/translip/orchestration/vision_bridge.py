from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from ..types import PipelineRequest
from .commands import (
    effective_task_a_segments_path,
    visual_context_dir,
    visual_context_manifest_path,
    visual_context_path,
)
from .subprocess_runner import run_stage_command

if TYPE_CHECKING:
    from .monitor import PipelineMonitor

# Must match translip.vision.extract.PROGRESS_PREFIX (kept as a literal here so
# this module stays free of the vision stack at import time).
_VISION_PROGRESS_PREFIX = "__VISION_PROGRESS__"


def build_visual_context_command(request: PipelineRequest) -> list[str]:
    # Segments must be the *effective* task-a output (speaker-corrected →
    # corrected → raw) — the same file task-c consumes, so the time axis the
    # visual units describe is the one translation will match against.
    return [
        sys.executable,
        "-m",
        "translip.vision.extract",
        "--input",
        str(request.input_path),
        "--task",
        "scene-context",
        "--segments",
        str(effective_task_a_segments_path(request)),
        "--output-dir",
        str(visual_context_dir(request)),
        "--backend",
        str(request.vision_backend),
        "--frames-per-unit",
        str(int(request.vision_frames_per_unit)),
        "--lang",
        str(request.vision_lang),
    ]


def parse_vision_progress_line(line: str) -> tuple[float, str] | None:
    """Parse one `__VISION_PROGRESS__\\t<pct>\\t<message>` line from the extractor."""
    if not line.startswith(_VISION_PROGRESS_PREFIX + "\t"):
        return None
    parts = line.split("\t", 2)
    if len(parts) < 2:
        return None
    try:
        percent = float(parts[1])
    except ValueError:
        return None
    return percent, parts[2] if len(parts) > 2 else "analyzing video"


def _build_progress_handler(monitor: "PipelineMonitor | None") -> Callable[[str], None] | None:
    if monitor is None:
        return None

    def _handle(line: str) -> None:
        parsed = parse_vision_progress_line(line)
        if parsed is not None:
            monitor.update_stage_progress("visual-context", parsed[0], parsed[1])

    return _handle


def run_visual_context(
    request: PipelineRequest,
    *,
    log_path: Path,
    monitor: "PipelineMonitor | None" = None,
    should_cancel: Callable[[], bool] | None = None,
) -> dict[str, object]:
    run_stage_command(
        build_visual_context_command(request),
        log_path=log_path,
        on_stdout_line=_build_progress_handler(monitor),
        should_cancel=should_cancel,
    )
    # The extractor writes scene-context-manifest.json itself (like ocr-detect).
    return {
        "manifest_path": str(visual_context_manifest_path(request)),
        "artifact_paths": [
            str(visual_context_path(request)),
            str(visual_context_manifest_path(request)),
        ],
        "log_path": str(log_path),
    }


__all__ = [
    "build_visual_context_command",
    "parse_vision_progress_line",
    "run_visual_context",
    "visual_context_dir",
    "visual_context_manifest_path",
    "visual_context_path",
]
