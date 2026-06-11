from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from ..types import PipelineRequest
from .subprocess_runner import run_stage_command

if TYPE_CHECKING:
    from .monitor import PipelineMonitor

# Must match translip.ocr.extract.PROGRESS_PREFIX (imported lazily there; kept as
# a literal here so this module stays free of the heavy `ocr` extra at import).
_OCR_PROGRESS_PREFIX = "__OCR_PROGRESS__"


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


def ocr_events_path(request: PipelineRequest) -> Path:
    return request.output_root / "ocr-detect" / "ocr_events.json"


def ocr_detection_path(request: PipelineRequest) -> Path:
    return request.output_root / "ocr-detect" / "detection.json"


def ocr_source_srt_path(request: PipelineRequest) -> Path:
    return request.output_root / "ocr-detect" / "ocr_subtitles.source.srt"


def ocr_detect_manifest_path(request: PipelineRequest) -> Path:
    return request.output_root / "ocr-detect" / "ocr-detect-manifest.json"


def ocr_classified_events_path(request: PipelineRequest) -> Path:
    return request.output_root / "ocr-detect" / "ocr_events.classified.json"


def effective_ocr_events_path(request: PipelineRequest) -> Path:
    """OCR events file downstream consumers should read.

    The classified variant (each event annotated with kind: subtitle /
    scene_text / watermark / title_card) only applies when the user opted into
    classification AND the file exists — a stale classified file from an
    earlier run must not leak into a flag-off run.
    """
    classified = ocr_classified_events_path(request)
    if getattr(request, "ocr_classify_text", False) and classified.exists():
        return classified
    return ocr_events_path(request)


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
        str(request.ocr_sample_interval),
        "--position-mode",
        request.ocr_position_mode,
        "--extraction-mode",
        request.ocr_extraction_mode,
    ]


def parse_ocr_progress_line(line: str) -> tuple[float, str] | None:
    """Parse one `__OCR_PROGRESS__\\t<pct>\\t<message>` line emitted by
    `translip.ocr.extract`. Returns `(percent, message)` or None for other lines.

    Shared by the orchestration node and the atomic subtitle-detect tool so the
    progress wire format lives in exactly one place."""
    if not line.startswith(_OCR_PROGRESS_PREFIX + "\t"):
        return None
    parts = line.split("\t", 2)
    if len(parts) < 2:
        return None
    try:
        percent = float(parts[1])
    except ValueError:
        return None
    step = parts[2] if len(parts) > 2 else "recognizing subtitles"
    return percent, step


def _build_progress_handler(
    monitor: "PipelineMonitor | None",
) -> Callable[[str], None] | None:
    """Forward extractor progress lines to the pipeline monitor as ocr-detect progress."""
    if monitor is None:
        return None

    def _handle(line: str) -> None:
        parsed = parse_ocr_progress_line(line)
        if parsed is not None:
            monitor.update_stage_progress("ocr-detect", parsed[0], parsed[1])

    return _handle


def build_ocr_classify_command(request: PipelineRequest) -> list[str]:
    # Vision-based post-classification of OCR events (subtitle vs scene_text vs
    # watermark vs title_card). Same in-tree extractor as the visual-context
    # node; writes ocr_events.classified.json next to ocr_events.json.
    return [
        sys.executable,
        "-m",
        "translip.vision.extract",
        "--input",
        str(request.input_path),
        "--task",
        "ocr-classify",
        "--detection",
        str(ocr_events_path(request)),
        "--output-dir",
        str(request.output_root / "ocr-detect"),
        "--backend",
        str(request.vision_backend),
        "--lang",
        str(request.vision_lang),
    ]


def _build_classify_progress_handler(
    monitor: "PipelineMonitor | None",
) -> Callable[[str], None] | None:
    if monitor is None:
        return None
    # Vision progress lines use a different prefix; map the classify run onto
    # the tail (90-99%) of the ocr-detect stage band.
    vision_prefix = "__VISION_PROGRESS__"

    def _handle(line: str) -> None:
        if not line.startswith(vision_prefix + "\t"):
            return
        parts = line.split("\t", 2)
        try:
            percent = float(parts[1])
        except (IndexError, ValueError):
            return
        mapped = 90.0 + 9.0 * max(0.0, min(100.0, percent)) / 100.0
        message = parts[2] if len(parts) > 2 else "classifying on-screen text"
        monitor.update_stage_progress("ocr-detect", mapped, message)

    return _handle


def run_ocr_detect(
    request: PipelineRequest,
    *,
    log_path: Path,
    monitor: "PipelineMonitor | None" = None,
    should_cancel: Callable[[], bool] | None = None,
) -> dict[str, object]:
    run_stage_command(
        build_ocr_detect_command(request),
        log_path=log_path,
        on_stdout_line=_build_progress_handler(monitor),
        should_cancel=should_cancel,
    )
    artifact_paths = [
        str(ocr_events_path(request)),
        str(ocr_detection_path(request)),
        str(ocr_source_srt_path(request)),
    ]
    if getattr(request, "ocr_classify_text", False):
        if monitor is not None:
            monitor.update_stage_progress("ocr-detect", 90.0, "classifying on-screen text")
        run_stage_command(
            build_ocr_classify_command(request),
            log_path=log_path,
            on_stdout_line=_build_classify_progress_handler(monitor),
            should_cancel=should_cancel,
        )
        artifact_paths.append(str(ocr_classified_events_path(request)))
    return {
        "manifest_path": str(ocr_detect_manifest_path(request)),
        "artifact_paths": artifact_paths,
        "log_path": str(log_path),
    }
