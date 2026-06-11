"""Vision analysis orchestration: units → frames → inference → artifacts.

Load the backend once, loop over analysis units, tolerate per-unit failures
(parse errors degrade, backend errors are recorded and skipped), and write the
per-task artifact + ``<task>-manifest.json`` contract the rest of translip
expects. Heavy backends are created lazily so this module imports cheaply.
"""
from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ..backends import create_backend
from ..backends.base import VisionBackend
from ..config import VALID_LANGS, VALID_TASKS, VisionSettings, load_settings
from ..frames import (
    AnalysisUnit,
    extract_frame,
    frame_times_for_unit,
    load_detection_events,
    load_segments_file,
    units_from_events,
    units_from_interval,
    units_from_segments,
    video_duration_sec,
)
from ..prompts import render_prompt
from ..schema import parse_unit_output

ProgressCallback = Callable[[float, str], None]

# Consecutive backend failures before the stage fails fast (backend is down,
# not a content problem).
MAX_CONSECUTIVE_FAILURES = 5

ARTIFACT_NAMES = {
    "scene-context": "visual_context.json",
    "erase-qc": "erase_qc_report.json",
    "ocr-classify": "ocr_events.classified.json",
    "speaker-visual": "speaker_visual.json",
    "freeform": "freeform_answer.json",
}


@dataclass(slots=True)
class AnalyzeRequest:
    input_path: Path
    output_dir: Path
    task: str = "scene-context"
    segments_path: Path | None = None
    detection_path: Path | None = None
    question: str | None = None
    sample_interval_sec: float = 10.0
    backend: str | None = None  # overrides VISION_BACKEND when set
    frames_per_unit: int | None = None  # overrides VISION_FRAMES_PER_UNIT when set
    lang: str = "zh"
    max_units: int | None = None


@dataclass(slots=True)
class AnalyzeResult:
    manifest: dict[str, Any]
    manifest_path: Path
    artifact_path: Path
    unit_count: int = 0
    error_count: int = 0
    frames_dir: Path | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def _validated(request: AnalyzeRequest) -> AnalyzeRequest:
    if request.task not in VALID_TASKS:
        raise ValueError(f"Unsupported vision task: {request.task} (choose from {', '.join(VALID_TASKS)})")
    if request.task == "ocr-classify" and request.detection_path is None:
        raise ValueError("ocr-classify requires --detection (ocr_events.json or detection.json)")
    if request.task == "freeform" and not (request.question or "").strip():
        raise ValueError("freeform requires --question")
    if request.lang not in VALID_LANGS:
        raise ValueError(f"Unsupported vision lang: {request.lang} (choose from {', '.join(VALID_LANGS)})")
    if not request.input_path.exists():
        raise FileNotFoundError(f"Input video does not exist: {request.input_path}")
    return request


def _subsample(units: list[AnalysisUnit], max_units: int | None) -> tuple[list[AnalysisUnit], int]:
    """Evenly subsample units to ``max_units``; returns (units, dropped_count)."""
    if not max_units or max_units <= 0 or len(units) <= max_units:
        return units, 0
    step = len(units) / max_units
    picked = [units[int(index * step)] for index in range(max_units)]
    return picked, len(units) - len(picked)


def _build_units(request: AnalyzeRequest) -> list[AnalysisUnit]:
    if request.task == "ocr-classify":
        return units_from_events(load_detection_events(request.detection_path))
    if request.task == "erase-qc" and request.detection_path is not None:
        # QC the spots where subtitles used to be (clean video + old detection).
        return units_from_events(load_detection_events(request.detection_path))
    if request.task == "freeform":
        duration = video_duration_sec(request.input_path)
        return [AnalysisUnit(unit_id="vis-0001", start=0.0, end=duration)]
    if request.segments_path is not None:
        return units_from_segments(load_segments_file(request.segments_path))
    duration = video_duration_sec(request.input_path)
    return units_from_interval(duration, interval_sec=request.sample_interval_sec)


def _unit_prompt(request: AnalyzeRequest, unit: AnalysisUnit, events_by_id: dict[str, dict]) -> str:
    if request.task == "ocr-classify":
        event = events_by_id.get(unit.unit_id, {})
        return render_prompt(request.task, request.lang, text=str(event.get("text") or ""))
    if request.task == "freeform":
        return render_prompt(request.task, request.lang, question=(request.question or "").strip())
    return render_prompt(request.task, request.lang)


def _frames_for_unit(
    request: AnalyzeRequest,
    unit: AnalysisUnit,
    *,
    settings: VisionSettings,
    frames_dir: Path,
) -> tuple[list[Path], list[float]]:
    if request.task == "ocr-classify":
        frames_per_unit = 1  # one midpoint frame per OCR event
    elif request.task == "freeform":
        frames_per_unit = 8  # spread over the whole video
    else:
        frames_per_unit = request.frames_per_unit or settings.frames_per_unit
    times = frame_times_for_unit(unit, frames_per_unit=frames_per_unit)
    paths = [
        extract_frame(
            request.input_path,
            timestamp,
            frames_dir / f"{unit.unit_id}_{index:02d}.jpg",
            max_edge=settings.frame_max_edge,
        )
        for index, timestamp in enumerate(times)
    ]
    return paths, times


def analyze_video(
    request: AnalyzeRequest,
    *,
    backend_override: VisionBackend | None = None,
    progress_callback: ProgressCallback | None = None,
) -> AnalyzeResult:
    request = _validated(request)
    settings = load_settings()
    if request.backend:
        # Per-run override of the env default (mirrors erase's CLI precedence).
        settings = dataclasses.replace(settings, backend=request.backend)
    output_dir = request.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    frames_dir = output_dir / "frames"
    artifact_path = output_dir / ARTIFACT_NAMES[request.task]
    manifest_path = output_dir / f"{request.task}-manifest.json"

    def report(percent: float, message: str) -> None:
        if progress_callback is not None:
            progress_callback(max(0.0, min(100.0, percent)), message)

    report(1.0, "planning_units")
    units = _build_units(request)
    units, dropped = _subsample(units, request.max_units)
    events_by_id: dict[str, dict] = {}
    original_events_payload: Any = None
    if request.task == "ocr-classify":
        original_events_payload = json.loads(request.detection_path.read_text(encoding="utf-8"))
        for event in load_detection_events(request.detection_path):
            event_id = str(event.get("event_id") or f"evt-{int(event.get('index', 0)):04d}")
            events_by_id[event_id] = event

    backend = backend_override if backend_override is not None else create_backend(settings)
    report(3.0, "loading_model")
    backend.load()

    unit_rows: list[dict[str, Any]] = []
    error_count = 0
    consecutive_failures = 0
    aborted_reason: str | None = None
    total = len(units)
    try:
        for index, unit in enumerate(units):
            percent = 5.0 + (90.0 * index / total) if total else 95.0
            report(percent, f"analyzing unit {index + 1}/{total}")
            row: dict[str, Any] = {
                "unit_id": unit.unit_id,
                "start": round(unit.start, 3),
                "end": round(unit.end, 3),
                "segment_ids": list(unit.segment_ids),
            }
            try:
                frame_paths, frame_times = _frames_for_unit(
                    request, unit, settings=settings, frames_dir=frames_dir
                )
                row["frames_sampled"] = frame_times
                prompt = _unit_prompt(request, unit, events_by_id)
                output_text = backend.chat(frame_paths, prompt)
            except Exception as exc:  # backend/extraction failure: record + continue
                row["error"] = str(exc)[:500]
                unit_rows.append(row)
                error_count += 1
                consecutive_failures += 1
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    aborted_reason = (
                        f"{MAX_CONSECUTIVE_FAILURES} consecutive unit failures — backend "
                        f"likely unavailable; last error: {str(exc)[:200]}"
                    )
                    break
                continue
            consecutive_failures = 0
            payload = parse_unit_output(request.task, output_text)
            if "error" in payload:
                error_count += 1
            row.update(payload)
            unit_rows.append(row)
    finally:
        backend.close()

    report(96.0, "writing_artifacts")
    model_info = {"backend": backend.backend_name, "model": backend.model_id}
    artifact_payload = _artifact_payload(
        request,
        model_info=model_info,
        unit_rows=unit_rows,
        original_events_payload=original_events_payload,
        dropped_units=dropped,
    )
    artifact_path.write_text(
        json.dumps(artifact_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    status = "failed" if aborted_reason else "succeeded"
    manifest: dict[str, Any] = {
        "status": status,
        "task": request.task,
        "model": model_info,
        "lang": request.lang,
        "unit_count": len(unit_rows),
        "planned_unit_count": total,
        "dropped_unit_count": dropped,
        "error_count": error_count,
        "artifacts": {
            "result_json": str(artifact_path),
            "frames_dir": str(frames_dir) if frames_dir.exists() else None,
        },
    }
    if aborted_reason:
        manifest["error"] = aborted_reason
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report(100.0, "completed")
    return AnalyzeResult(
        manifest=manifest,
        manifest_path=manifest_path,
        artifact_path=artifact_path,
        unit_count=len(unit_rows),
        error_count=error_count,
        frames_dir=frames_dir if frames_dir.exists() else None,
    )


def _artifact_payload(
    request: AnalyzeRequest,
    *,
    model_info: dict[str, str],
    unit_rows: list[dict[str, Any]],
    original_events_payload: Any,
    dropped_units: int,
) -> dict[str, Any]:
    if request.task == "ocr-classify":
        # Preserve the original events file shape; annotate each event in place.
        classified_by_id = {row["unit_id"]: row for row in unit_rows}
        payload = original_events_payload if isinstance(original_events_payload, dict) else {"events": []}
        events = payload.get("events") or payload.get("results") or []
        for event in events:
            if not isinstance(event, dict):
                continue
            event_id = str(event.get("event_id") or f"evt-{int(event.get('index', 0)):04d}")
            row = classified_by_id.get(event_id)
            if row is None:
                continue
            if "kind" in row:
                event["kind"] = row["kind"]
                event["kind_confidence"] = row.get("confidence")
            else:
                event["kind_error"] = row.get("error") or row.get("raw")
        payload["classification"] = {"task": request.task, "model": model_info}
        return payload

    if request.task == "erase-qc":
        flagged = [row for row in unit_rows if row.get("residual_text") or row.get("artifact")]
        checked = [row for row in unit_rows if "error" not in row]
        return {
            "task": request.task,
            "model": model_info,
            "samples": unit_rows,
            "summary": {
                "checked": len(checked),
                "flagged": len(flagged),
                "pass_rate": round(1.0 - len(flagged) / len(checked), 4) if checked else None,
            },
        }

    if request.task == "freeform":
        row = unit_rows[0] if unit_rows else {}
        return {
            "task": request.task,
            "model": model_info,
            "question": (request.question or "").strip(),
            "answer": row.get("answer"),
            "confidence": row.get("confidence"),
            "frames_sampled": row.get("frames_sampled", []),
            "error": row.get("error"),
        }

    # scene-context / speaker-visual share the units-list envelope.
    return {
        "task": request.task,
        "model": model_info,
        "dropped_unit_count": dropped_units,
        "units": unit_rows,
    }


__all__ = ["AnalyzeRequest", "AnalyzeResult", "analyze_video"]
