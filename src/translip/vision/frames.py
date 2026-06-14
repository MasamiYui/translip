"""Analysis-unit construction and ffmpeg frame sampling for the vision module.

Pure planning logic (unit building, frame-time selection) is separated from the
actual ffmpeg invocation so it can be unit-tested without media files. Units are
plain ``(start, end)`` intervals — the service layer does not care whether they
came from ASR segments or a fixed sampling interval (see the integration plan
§3.3: consumers match by time overlap, never by unit numbering).
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from ..utils.ffmpeg import ffmpeg_binary, probe_media

# Units shorter than this sample a single midpoint frame.
SHORT_UNIT_SEC = 2.0
# Hard cap on frames per inference call (memory bound on 16 GB hosts).
MAX_FRAMES_PER_UNIT = 8


@dataclass(slots=True)
class AnalysisUnit:
    unit_id: str
    start: float
    end: float
    segment_ids: list[str] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


def units_from_segments(
    segments: list[dict],
    *,
    max_gap_sec: float = 2.0,
    max_unit_duration_sec: float = 12.0,
    max_unit_segments: int = 6,
) -> list[AnalysisUnit]:
    """Group ASR segments into analysis units.

    This is vision's own grouping — it intentionally does NOT mirror
    translation's ``build_context_units`` numbering; downstream consumers match by
    time overlap. Speaker changes do not split a unit (the camera does not cut
    on every speaker turn) — only temporal gaps and size caps do.
    """
    cleaned: list[tuple[float, float, str]] = []
    for raw in segments:
        if not isinstance(raw, dict):
            continue
        try:
            start = float(raw["start"])
            end = float(raw["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if end <= start:
            continue
        cleaned.append((start, end, str(raw.get("id") or "")))
    cleaned.sort(key=lambda item: item[0])

    units: list[AnalysisUnit] = []
    current: list[tuple[float, float, str]] = []

    def flush() -> None:
        if not current:
            return
        units.append(
            AnalysisUnit(
                unit_id=f"vis-{len(units) + 1:04d}",
                start=current[0][0],
                end=max(item[1] for item in current),
                segment_ids=[seg_id for _, _, seg_id in current if seg_id],
            )
        )

    for item in cleaned:
        if not current:
            current = [item]
            continue
        gap = item[0] - max(prev[1] for prev in current)
        candidate_duration = item[1] - current[0][0]
        if gap <= max_gap_sec and candidate_duration <= max_unit_duration_sec and len(current) < max_unit_segments:
            current.append(item)
            continue
        flush()
        current = [item]
    flush()
    return units


def units_from_interval(duration_sec: float, *, interval_sec: float = 10.0) -> list[AnalysisUnit]:
    """Slice ``[0, duration)`` into fixed-interval units (bare-video mode).

    A sub-second tail sliver (e.g. a 60.001s probe duration with 12s intervals)
    is merged into the previous unit instead of becoming its own unit — seeking
    at/past the last frame makes ffmpeg extraction fail.
    """
    if duration_sec <= 0 or interval_sec <= 0:
        return []
    units: list[AnalysisUnit] = []
    start = 0.0
    index = 1
    while start < duration_sec:
        end = min(start + interval_sec, duration_sec)
        units.append(AnalysisUnit(unit_id=f"vis-{index:04d}", start=start, end=end))
        start = end
        index += 1
    if len(units) > 1 and units[-1].duration < 1.0:
        tail = units.pop()
        units[-1].end = tail.end
    return units


def units_from_events(events: list[dict]) -> list[AnalysisUnit]:
    """One unit per OCR event (erase-qc / ocr-classify drive off detections)."""
    units: list[AnalysisUnit] = []
    for raw in events:
        if not isinstance(raw, dict):
            continue
        try:
            start = float(raw.get("start", raw.get("start_time")))
            end = float(raw.get("end", raw.get("end_time")))
        except (TypeError, ValueError):
            continue
        if end < start:
            continue
        event_id = str(raw.get("event_id") or f"evt-{len(units) + 1:04d}")
        units.append(AnalysisUnit(unit_id=event_id, start=start, end=end))
    return units


def frame_times_for_unit(unit: AnalysisUnit, *, frames_per_unit: int) -> list[float]:
    """Pick sample timestamps inside a unit.

    Short units (< 2s) take the midpoint only. Longer units sample k frames
    uniformly, inset by half a step so frames stay inside the interval.
    """
    k = max(1, min(MAX_FRAMES_PER_UNIT, frames_per_unit))
    if unit.duration < SHORT_UNIT_SEC or k == 1:
        return [round(unit.start + unit.duration / 2.0, 3)]
    step = unit.duration / k
    return [round(unit.start + step * (index + 0.5), 3) for index in range(k)]


def extract_frame(
    video_path: Path,
    timestamp: float,
    output_path: Path,
    *,
    max_edge: int = 768,
) -> Path:
    """Extract one frame at ``timestamp`` scaled so its long edge is ``max_edge``."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    scale = f"scale='if(gt(iw,ih),{max_edge},-2)':'if(gt(iw,ih),-2,{max_edge})'"
    command = [
        ffmpeg_binary(),
        "-y",
        "-v",
        "error",
        "-ss",
        f"{max(0.0, timestamp):.3f}",
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        "-vf",
        scale,
        "-q:v",
        "3",
        # mjpeg refuses non-full-range YUV sources at default strictness.
        "-strict",
        "unofficial",
        str(output_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0 or not output_path.exists():
        raise RuntimeError(
            f"ffmpeg frame extraction failed at {timestamp:.3f}s: {result.stderr.strip()[:500]}"
        )
    return output_path


def extract_frames_batch(
    video_path: Path,
    timestamps: list[float],
    output_paths: list[Path],
    *,
    max_edge: int = 768,
) -> list[Path]:
    """Extract several frames of one unit with a single ffmpeg invocation.

    One input seek to the earliest timestamp + a ``select`` filter picking each
    requested time — one process start and one decode pass per unit instead of
    per frame (a 300-unit film at 4 frames/unit would otherwise spawn 1200
    ffmpeg processes, each re-seeking from scratch). Falls back to per-frame
    extraction when the batch path fails or produces fewer frames than asked.
    """
    if len(timestamps) != len(output_paths):
        raise ValueError("timestamps and output_paths must be the same length")
    if not timestamps:
        return []
    if len(timestamps) == 1:
        return [extract_frame(video_path, timestamps[0], output_paths[0], max_edge=max_edge)]

    for path in output_paths:
        path.parent.mkdir(parents=True, exist_ok=True)
    out_dir = output_paths[0].parent
    base = max(0.0, min(timestamps))
    # select by in-segment time (t is relative to the -ss seek point). For each
    # target offset pick exactly the frame that crosses it: prev frame was
    # before the offset (or there is no prev frame) and this one is at/after.
    # A window like lt(t,o+0.5) would pass every frame inside the window and
    # -frames:v would then take them all from the first offset.
    offsets = sorted(round(max(0.0, t - base), 3) for t in timestamps)
    select_expr = "+".join(
        f"gte(t,{offset})*(isnan(prev_t)+lt(prev_t,{offset}))" for offset in offsets
    )
    scale = f"scale='if(gt(iw,ih),{max_edge},-2)':'if(gt(iw,ih),-2,{max_edge})'"
    pattern = out_dir / f".batch_{output_paths[0].stem}_%02d.jpg"
    command = [
        ffmpeg_binary(),
        "-y",
        "-v",
        "error",
        "-ss",
        f"{base:.3f}",
        "-i",
        str(video_path),
        "-vf",
        f"select='{select_expr}',{scale}",
        "-fps_mode",
        "passthrough",
        "-frames:v",
        str(len(timestamps)),
        "-q:v",
        "3",
        "-strict",
        "unofficial",
        str(pattern),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    produced = sorted(out_dir.glob(f".batch_{output_paths[0].stem}_*.jpg"))
    if result.returncode != 0 or len(produced) < len(timestamps):
        for stale in produced:
            stale.unlink(missing_ok=True)
        return [
            extract_frame(video_path, timestamp, path, max_edge=max_edge)
            for timestamp, path in zip(timestamps, output_paths)
        ]
    for src, dst in zip(produced, output_paths):
        src.replace(dst)
    for extra in produced[len(output_paths) :]:
        extra.unlink(missing_ok=True)
    return list(output_paths)


def frame_signature(image_path: Path, *, grid: int = 16) -> list[int] | None:
    """Tiny grayscale thumbnail signature for cheap frame similarity.

    Returns ``grid*grid`` luma values, or None when Pillow is unavailable or
    the image cannot be read (callers must treat None as "cannot compare").
    """
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(image_path) as img:
            small = img.convert("L").resize((grid, grid))
            return list(small.getdata())
    except OSError:
        return None


def signature_distance(a: list[int], b: list[int]) -> float:
    """Mean absolute luma difference (0 = identical, 255 = inverted)."""
    if not a or not b or len(a) != len(b):
        return 255.0
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


def video_duration_sec(video_path: Path) -> float:
    return float(probe_media(video_path).duration_sec or 0.0)


def load_segments_file(path: Path) -> list[dict]:
    """Read a transcription style segments JSON (``{"segments": [...]}`` or bare list)."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        segments = payload.get("segments", [])
    else:
        segments = payload
    return [seg for seg in segments if isinstance(seg, dict)]


def load_detection_events(path: Path) -> list[dict]:
    """Read OCR events from ``ocr_events.json`` / ``detection.json``."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        events = payload.get("events") or payload.get("results") or []
    else:
        events = payload
    return [event for event in events if isinstance(event, dict)]


__all__ = [
    "MAX_FRAMES_PER_UNIT",
    "SHORT_UNIT_SEC",
    "AnalysisUnit",
    "extract_frame",
    "extract_frames_batch",
    "frame_signature",
    "frame_times_for_unit",
    "load_detection_events",
    "load_segments_file",
    "signature_distance",
    "units_from_events",
    "units_from_interval",
    "units_from_segments",
    "video_duration_sec",
]
