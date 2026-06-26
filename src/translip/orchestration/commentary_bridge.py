from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from ..types import PipelineRequest
from .commands import (
    commentary_path,
    commentary_recap_path,
    commentary_render_dir,
    commentary_render_manifest_path,
    commentary_render_report_path,
    commentary_script_dir,
    commentary_script_manifest_path,
    effective_task_a_segments_path,
    visual_context_path,
)
from .subprocess_runner import run_stage_command

if TYPE_CHECKING:
    from .monitor import PipelineMonitor

# Must match translip.commentary.extract.PROGRESS_PREFIX (kept as a literal here so
# this module stays free of the commentary/TTS stack at import time).
_COMMENTARY_PROGRESS_PREFIX = "__COMMENTARY_PROGRESS__"


def build_commentary_script_command(request: PipelineRequest) -> list[str]:
    # Segments are the *effective* transcription output (the same file translation
    # would consume), so the script grounds on the corrected timeline. Visual
    # context is appended only when the optional visual-context node produced it.
    command = [
        sys.executable,
        "-m",
        "translip.commentary.extract",
        "--task",
        "script",
        "--segments",
        str(effective_task_a_segments_path(request)),
        "--output-dir",
        str(commentary_script_dir(request)),
        "--style",
        str(request.commentary_style),
        "--genre",
        str(request.commentary_genre),
        "--language",
        str(request.commentary_narration_language),
        "--original-sound-ratio",
        str(int(request.commentary_original_sound_ratio)),
    ]
    if visual_context_path(request).exists():
        command.extend(["--visual-context", str(visual_context_path(request))])
    return command


def build_commentary_render_command(request: PipelineRequest) -> list[str]:
    return [
        sys.executable,
        "-m",
        "translip.commentary.extract",
        "--task",
        "render",
        "--commentary",
        str(commentary_path(request)),
        "--input",
        str(request.input_path),
        "--output-dir",
        str(commentary_render_dir(request)),
        "--backend",
        str(request.commentary_backend),
        "--language",
        str(request.commentary_narration_language),
        "--original-gain-db",
        str(float(request.commentary_original_gain_db)),
    ]


def parse_commentary_progress_line(line: str) -> tuple[float, str] | None:
    """Parse one `__COMMENTARY_PROGRESS__\\t<pct>\\t<message>` line from the extractor."""
    if not line.startswith(_COMMENTARY_PROGRESS_PREFIX + "\t"):
        return None
    parts = line.split("\t", 2)
    if len(parts) < 2:
        return None
    try:
        percent = float(parts[1])
    except ValueError:
        return None
    return percent, parts[2] if len(parts) > 2 else "working"


def _build_progress_handler(
    monitor: "PipelineMonitor | None", stage_name: str
) -> Callable[[str], None] | None:
    if monitor is None:
        return None

    def _handle(line: str) -> None:
        parsed = parse_commentary_progress_line(line)
        if parsed is not None:
            monitor.update_stage_progress(stage_name, parsed[0], parsed[1])

    return _handle


def run_commentary_script(
    request: PipelineRequest,
    *,
    log_path: Path,
    monitor: "PipelineMonitor | None" = None,
    should_cancel: Callable[[], bool] | None = None,
) -> dict[str, object]:
    run_stage_command(
        build_commentary_script_command(request),
        log_path=log_path,
        on_stdout_line=_build_progress_handler(monitor, "commentary-script"),
        should_cancel=should_cancel,
    )
    return {
        "manifest_path": str(commentary_script_manifest_path(request)),
        "artifact_paths": [
            str(commentary_path(request)),
            str(commentary_script_manifest_path(request)),
        ],
        "log_path": str(log_path),
    }


def run_commentary_render(
    request: PipelineRequest,
    *,
    log_path: Path,
    monitor: "PipelineMonitor | None" = None,
    should_cancel: Callable[[], bool] | None = None,
) -> dict[str, object]:
    run_stage_command(
        build_commentary_render_command(request),
        log_path=log_path,
        on_stdout_line=_build_progress_handler(monitor, "commentary-render"),
        should_cancel=should_cancel,
    )
    return {
        "manifest_path": str(commentary_render_manifest_path(request)),
        "artifact_paths": [
            str(commentary_recap_path(request)),
            str(commentary_render_report_path(request)),
            str(commentary_render_manifest_path(request)),
        ],
        "log_path": str(log_path),
    }


__all__ = [
    "build_commentary_render_command",
    "build_commentary_script_command",
    "parse_commentary_progress_line",
    "run_commentary_render",
    "run_commentary_script",
]
