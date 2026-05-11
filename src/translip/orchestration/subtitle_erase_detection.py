from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..utils.ffmpeg import ffmpeg_binary


@dataclass(frozen=True, slots=True)
class VisualFallbackEvent:
    start_frame: int
    end_frame: int
    box: tuple[int, int, int, int]
    confidence: float


@dataclass(frozen=True, slots=True)
class SubtitleGeometryHint:
    band: tuple[int, int, int, int]
    center_x: float | None = None
    center_y: float | None = None
    min_width: int | None = None
    min_height: int | None = None
    max_width: int | None = None
    max_height: int | None = None
    max_center_dx: int | None = None
    max_center_dy: int | None = None


def prepare_subtitle_erase_detection(
    source_path: Path,
    output_path: Path,
    *,
    lead_frames: int,
    trail_frames: int,
    video_path: Path | None = None,
) -> Path:
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    expanded = expand_detection_payload(
        payload,
        lead_frames=lead_frames,
        trail_frames=trail_frames,
        source_path=source_path,
    )
    if video_path is not None:
        expanded = add_visual_fallback_events(
            expanded,
            video_path=video_path,
            lead_frames=lead_frames,
            trail_frames=trail_frames,
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if expanded is payload:
        shutil.copy2(source_path, output_path)
    else:
        output_path.write_text(
            json.dumps(expanded, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return output_path


def add_visual_fallback_events(
    payload: dict[str, Any],
    *,
    video_path: Path,
    lead_frames: int,
    trail_frames: int,
) -> dict[str, Any]:
    video = payload.get("video") if isinstance(payload.get("video"), dict) else {}
    fps = _optional_float(video.get("fps"))
    events = payload.get("events") if isinstance(payload.get("events"), list) else []
    existing_intervals = [
        (start, end)
        for event in events
        if isinstance(event, dict)
        for start, end in [_event_interval(event)]
        if start is not None and end is not None
    ]
    canonical_box = _canonical_subtitle_box(payload)
    nearby_gap_frames = max(max(0, lead_frames) + max(0, trail_frames), int(round((fps or 0.0) * 1.2)))
    visual_events = _detect_visual_fallback_events(
        video_path=video_path,
        payload=payload,
        lead_frames=lead_frames,
        trail_frames=trail_frames,
    )

    added: list[dict[str, Any]] = []
    for visual_event in visual_events:
        candidate = (visual_event.start_frame, visual_event.end_frame)
        if _is_interval_covered(candidate, existing_intervals):
            continue
        if not _has_nearby_interval(candidate, existing_intervals, max_gap_frames=nearby_gap_frames):
            continue
        event = visual_event
        if canonical_box is not None:
            event = VisualFallbackEvent(
                start_frame=visual_event.start_frame,
                end_frame=visual_event.end_frame,
                box=canonical_box,
                confidence=visual_event.confidence,
            )
        added.append(_visual_event_to_payload(event, index=len(events) + len(added) + 1, fps=fps))
        existing_intervals.append(candidate)

    prepared = dict(payload)
    prepared["events"] = sorted([*events, *added], key=lambda item: _optional_int(item.get("start_frame")) or 0)
    preprocess = dict(prepared.get("subtitle_erase_preprocess") or {})
    preprocess["visual_fallback_events"] = len(added)
    prepared["subtitle_erase_preprocess"] = preprocess
    return prepared


def expand_detection_payload(
    payload: dict[str, Any],
    *,
    lead_frames: int,
    trail_frames: int,
    source_path: Path | None = None,
) -> dict[str, Any]:
    events = payload.get("events")
    if not isinstance(events, list) or not events:
        return payload

    video = payload.get("video") if isinstance(payload.get("video"), dict) else {}
    fps = _optional_float(video.get("fps"))
    total_frames = _optional_int(video.get("total_frames") or video.get("readable_total_frames"))
    max_frame = total_frames - 1 if total_frames and total_frames > 0 else None
    lead = max(0, int(lead_frames))
    trail = max(0, int(trail_frames))

    expanded_payload = dict(payload)
    expanded_events: list[Any] = []
    for raw_event in events:
        if not isinstance(raw_event, dict):
            expanded_events.append(raw_event)
            continue
        expanded_events.append(
            _expand_event(
                raw_event,
                lead_frames=lead,
                trail_frames=trail,
                fps=fps,
                max_frame=max_frame,
            )
        )

    expanded_payload["events"] = expanded_events
    expanded_payload["subtitle_erase_preprocess"] = {
        "lead_frames": lead,
        "trail_frames": trail,
        "source_path": str(source_path) if source_path is not None else None,
    }
    return expanded_payload


def _expand_event(
    event: dict[str, Any],
    *,
    lead_frames: int,
    trail_frames: int,
    fps: float | None,
    max_frame: int | None,
) -> dict[str, Any]:
    start_frame = _optional_int(event.get("start_frame"))
    end_frame = _optional_int(event.get("end_frame"))
    if start_frame is None or end_frame is None:
        return dict(event)

    new_start = max(0, start_frame - lead_frames)
    new_end = end_frame + trail_frames
    if max_frame is not None:
        new_end = min(max_frame, new_end)
    new_end = max(new_start, new_end)

    expanded = dict(event)
    expanded["start_frame"] = new_start
    expanded["end_frame"] = new_end
    if fps and fps > 0:
        expanded["start_time"] = new_start / fps
        expanded["end_time"] = new_end / fps
        if "start" in expanded:
            expanded["start"] = expanded["start_time"]
        if "end" in expanded:
            expanded["end"] = expanded["end_time"]
    return expanded


def _detect_visual_fallback_events(
    *,
    video_path: Path,
    payload: dict[str, Any],
    lead_frames: int,
    trail_frames: int,
) -> list[VisualFallbackEvent]:
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
    except ImportError:
        return _detect_visual_fallback_events_with_ffmpeg(
            video_path=video_path,
            payload=payload,
            lead_frames=lead_frames,
            trail_frames=trail_frames,
        )

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return []

    try:
        video = payload.get("video") if isinstance(payload.get("video"), dict) else {}
        fps = _optional_float(video.get("fps")) or float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
        total_frames = _optional_int(video.get("total_frames") or video.get("readable_total_frames"))
        if total_frames is None or total_frames <= 0:
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = _optional_int(video.get("width")) or int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = _optional_int(video.get("height")) or int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        if width <= 0 or height <= 0:
            return []

        geometry = _infer_subtitle_geometry(payload, width=width, height=height)
        band = geometry.band
        stride = _visual_sample_stride(fps)
        hits: list[tuple[int, tuple[int, int, int, int], float]] = []
        frame_idx = 0
        while frame_idx < total_frames:
            ok, frame = cap.read()
            if not ok:
                break
            if frame_idx % stride == 0:
                result = _detect_subtitle_like_box(frame, band=band, cv2=cv2, np=np)
                if result is not None and _box_matches_subtitle_geometry(result[0], geometry):
                    box, confidence = result
                    hits.append((frame_idx, box, confidence))
            frame_idx += 1
    finally:
        cap.release()

    return _filter_visual_events(
        _merge_visual_hits(
            hits,
            total_frames=total_frames,
            fps=fps,
            stride=stride,
            lead_frames=lead_frames,
            trail_frames=trail_frames,
        ),
        geometry,
    )


def _infer_subtitle_geometry(
    payload: dict[str, Any],
    *,
    width: int,
    height: int,
) -> SubtitleGeometryHint:
    events = payload.get("events") if isinstance(payload.get("events"), list) else []
    boxes: list[tuple[int, int, int, int]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        box = event.get("box") or event.get("bbox") or event.get("region_box")
        if isinstance(box, (list, tuple)) and len(box) == 4:
            x1, y1, x2, y2 = (int(box[0]), int(box[1]), int(box[2]), int(box[3]))
            if x2 > x1 and y2 > y1:
                boxes.append((x1, y1, x2, y2))
    if boxes:
        y1s = [box[1] for box in boxes]
        y2s = [box[3] for box in boxes]
        widths = [box[2] - box[0] for box in boxes]
        heights = [box[3] - box[1] for box in boxes]
        x_centers = [(box[0] + box[2]) / 2.0 for box in boxes]
        y_centers = [(box[1] + box[3]) / 2.0 for box in boxes]
        y1 = max(0, min(y1s) - max(10, int(height * 0.035)))
        y2 = min(height, max(y2s) + max(10, int(height * 0.035)))
        p50_width = _percentile(widths, 50)
        p95_width = _percentile(widths, 95)
        p05_width = _percentile(widths, 5)
        p50_height = _percentile(heights, 50)
        p95_height = _percentile(heights, 95)
        y_center_spread = _percentile(y_centers, 90) - _percentile(y_centers, 10)
        max_width = min(width, max(48, int(max(p95_width * 1.3, p50_width * 1.8))))
        max_width = min(max_width, int(width * 0.6))
        max_height = min(height, max(18, int(max(p95_height * 1.15, p50_height * 1.3))))
        max_height = min(max_height, int(height * 0.28))
        return SubtitleGeometryHint(
            band=(0, y1, width, max(y1 + 1, y2)),
            center_x=_percentile(x_centers, 50),
            center_y=_percentile(y_centers, 50),
            min_width=max(50, int(p05_width * 0.75)),
            min_height=max(10, int(_percentile(heights, 5) * 0.18)),
            max_width=max_width,
            max_height=max_height,
            max_center_dx=max(70, int(max(p95_width * 0.5, width * 0.12))),
            max_center_dy=max(26, int(max(y_center_spread * 3.0 + 18, height * 0.06))),
        )
    return SubtitleGeometryHint(band=(0, int(height * 0.68), width, int(height * 0.98)))


def _infer_subtitle_search_band(
    payload: dict[str, Any],
    *,
    width: int,
    height: int,
) -> tuple[int, int, int, int]:
    return _infer_subtitle_geometry(payload, width=width, height=height).band


def _canonical_subtitle_box(payload: dict[str, Any]) -> tuple[int, int, int, int] | None:
    events = payload.get("events") if isinstance(payload.get("events"), list) else []
    boxes: list[tuple[int, int, int, int]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        box = event.get("box") or event.get("bbox") or event.get("region_box")
        if isinstance(box, (list, tuple)) and len(box) == 4:
            x1, y1, x2, y2 = (int(box[0]), int(box[1]), int(box[2]), int(box[3]))
            if x2 > x1 and y2 > y1:
                boxes.append((x1, y1, x2, y2))
    if not boxes:
        return None
    return (
        int(round(_percentile([box[0] for box in boxes], 50))),
        int(round(_percentile([box[1] for box in boxes], 50))),
        int(round(_percentile([box[2] for box in boxes], 50))),
        int(round(_percentile([box[3] for box in boxes], 50))),
    )


def _detect_visual_fallback_events_with_ffmpeg(
    *,
    video_path: Path,
    payload: dict[str, Any],
    lead_frames: int,
    trail_frames: int,
) -> list[VisualFallbackEvent]:
    try:
        import numpy as np  # type: ignore
    except ImportError:
        return []

    video = payload.get("video") if isinstance(payload.get("video"), dict) else {}
    fps = _optional_float(video.get("fps")) or 25.0
    total_frames = _optional_int(video.get("total_frames") or video.get("readable_total_frames"))
    width = _optional_int(video.get("width"))
    height = _optional_int(video.get("height"))
    if width is None or height is None or width <= 0 or height <= 0:
        return []
    if total_frames is None or total_frames <= 0:
        total_frames = int(max(1, round((_optional_float(video.get("duration")) or 0.0) * fps)))

    geometry = _infer_subtitle_geometry(payload, width=width, height=height)
    band = geometry.band
    x1, y1, x2, y2 = band
    crop_width = max(1, x2 - x1)
    crop_height = max(1, y2 - y1)
    frame_size = crop_width * crop_height * 3
    stride = _visual_sample_stride(fps)
    filter_spec = f"select='not(mod(n\\,{stride}))',crop={crop_width}:{crop_height}:{x1}:{y1}"
    command = [
        ffmpeg_binary(),
        "-v",
        "error",
        "-i",
        str(video_path),
        "-an",
        "-vf",
        filter_spec,
        "-vsync",
        "0",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-",
    ]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert process.stdout is not None
    hits: list[tuple[int, tuple[int, int, int, int], float]] = []
    sample_index = 0
    try:
        while True:
            chunk = process.stdout.read(frame_size)
            if not chunk:
                break
            if len(chunk) != frame_size:
                break
            crop = np.frombuffer(chunk, dtype=np.uint8).reshape((crop_height, crop_width, 3))
            result = _detect_subtitle_like_box_numpy(crop, band=(0, 0, crop_width, crop_height))
            if result is not None:
                box, confidence = result
                absolute_box = (box[0] + x1, box[1] + y1, box[2] + x1, box[3] + y1)
                if _box_matches_subtitle_geometry(absolute_box, geometry):
                    hits.append((sample_index * stride, absolute_box, confidence))
            sample_index += 1
    finally:
        stderr = process.stderr.read() if process.stderr is not None else b""
        process.stdout.close()
        process.wait()
        if process.returncode != 0 and stderr:
            return []

    return _filter_visual_events(
        _merge_visual_hits(
            hits,
            total_frames=total_frames,
            fps=fps,
            stride=stride,
            lead_frames=lead_frames,
            trail_frames=trail_frames,
        ),
        geometry,
    )


def _visual_sample_stride(fps: float) -> int:
    return max(2, min(8, int(round(max(1.0, fps) * 0.22))))


def _detect_subtitle_like_box(
    frame: Any,
    *,
    band: tuple[int, int, int, int],
    cv2: Any,
    np: Any,
) -> tuple[tuple[int, int, int, int], float] | None:
    x1, y1, x2, y2 = band
    roi = frame[y1:y2, x1:x2]
    if roi.size == 0:
        return None

    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    p92 = float(np.percentile(gray, 92))
    bright_threshold = int(min(245, max(145, round(p92))))
    b, g, r = cv2.split(roi)
    bright = gray >= bright_threshold
    yellow = (r > 155) & (g > 135) & (b < 130) & (gray > 120)
    core = bright | yellow
    if float(core.mean()) < 0.0004:
        return None

    edges = cv2.Canny(gray, 35, 120) > 0
    near_edges = cv2.dilate(edges.astype("uint8"), np.ones((3, 3), np.uint8), iterations=1).astype(bool)
    text_mask = (core & near_edges).astype("uint8") * 255
    text_mask = cv2.morphologyEx(
        text_mask,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 3)),
    )

    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(text_mask, connectivity=8)
    cleaned = np.zeros_like(text_mask)
    component_count = 0
    roi_area = max(1, int(text_mask.shape[0] * text_mask.shape[1]))
    for label in range(1, num_labels):
        area = int(stats[label, cv2.CC_STAT_AREA])
        comp_width = int(stats[label, cv2.CC_STAT_WIDTH])
        comp_height = int(stats[label, cv2.CC_STAT_HEIGHT])
        if area < 6 or area > roi_area * 0.08:
            continue
        if comp_width < 2 or comp_height < 4 or comp_height > text_mask.shape[0] * 0.75:
            continue
        cleaned[labels == label] = 255
        component_count += 1

    if component_count < 2:
        return None

    row_window = _select_text_row_window((cleaned > 0).sum(axis=1), cleaned.shape[1])
    if row_window is None:
        return None
    window_y1, window_y2 = row_window
    cleaned_window = cleaned[window_y1:window_y2]

    ys, xs = np.where(cleaned_window > 0)
    if xs.size == 0 or ys.size == 0:
        return None
    local_x1 = int(xs.min())
    local_x2 = int(xs.max()) + 1
    local_y1 = window_y1 + int(ys.min())
    local_y2 = window_y1 + int(ys.max()) + 1
    box_width = local_x2 - local_x1
    box_height = local_y2 - local_y1
    if box_width < 18 or box_height < 8:
        return None
    if box_width > roi.shape[1] * 0.86 or box_height > roi.shape[0] * 0.72:
        return None
    coverage = float(cleaned.mean()) / 255.0
    if coverage < 0.0004 or coverage > 0.14:
        return None

    pad_x = max(12, int(box_width * 0.08))
    pad_y = max(8, int(box_height * 0.35))
    box = (
        max(0, x1 + local_x1 - pad_x),
        max(0, y1 + local_y1 - pad_y),
        min(frame.shape[1], x1 + local_x2 + pad_x),
        min(frame.shape[0], y1 + local_y2 + pad_y),
    )
    confidence = min(0.95, 0.45 + min(0.35, component_count / 40.0) + min(0.15, coverage * 3.0))
    return box, confidence


def _detect_subtitle_like_box_numpy(
    frame: Any,
    *,
    band: tuple[int, int, int, int],
) -> tuple[tuple[int, int, int, int], float] | None:
    import numpy as np  # type: ignore

    x1, y1, x2, y2 = band
    roi = frame[y1:y2, x1:x2]
    if roi.size == 0:
        return None

    roi_float = roi.astype(np.float32)
    r = roi_float[:, :, 0]
    g = roi_float[:, :, 1]
    b = roi_float[:, :, 2]
    gray = 0.299 * r + 0.587 * g + 0.114 * b
    p92 = float(np.percentile(gray, 92))
    bright_threshold = min(245.0, max(145.0, round(p92)))
    bright = gray >= bright_threshold
    yellow = (r > 155) & (g > 135) & (b < 130) & (gray > 120)
    core = bright | yellow
    if float(core.mean()) < 0.0004:
        return None

    edge = np.zeros(gray.shape, dtype=bool)
    dx = np.abs(np.diff(gray, axis=1)) > 18
    dy = np.abs(np.diff(gray, axis=0)) > 18
    edge[:, 1:] |= dx
    edge[:, :-1] |= dx
    edge[1:, :] |= dy
    edge[:-1, :] |= dy
    text_mask = core & _binary_dilate(edge, radius_y=1, radius_x=1)
    if float(text_mask.mean()) < 0.00025:
        text_mask = core

    row_window = _select_text_row_window(text_mask.sum(axis=1), text_mask.shape[1])
    if row_window is None:
        return None
    window_y1, window_y2 = row_window
    text_window = text_mask[window_y1:window_y2]

    row_counts = text_window.sum(axis=1)
    col_counts = text_window.sum(axis=0)
    active_rows = row_counts >= 2
    active_cols = col_counts >= 2
    if not active_rows.any() or not active_cols.any():
        return None

    ys = np.where(active_rows)[0]
    xs = np.where(active_cols)[0]
    local_x1, local_x2 = int(xs.min()), int(xs.max()) + 1
    local_y1 = window_y1 + int(ys.min())
    local_y2 = window_y1 + int(ys.max()) + 1
    box_width = local_x2 - local_x1
    box_height = local_y2 - local_y1
    if box_width < 18 or box_height < 6:
        return None
    if box_width > roi.shape[1] * 0.86 or box_height > roi.shape[0] * 0.72:
        return None

    coverage = float(text_mask.mean())
    if coverage < 0.0003 or coverage > 0.16:
        return None

    column_runs = _count_true_runs(active_cols)
    if column_runs < 2 and box_width < 80:
        return None

    pad_x = max(12, int(box_width * 0.08))
    pad_y = max(8, int(box_height * 0.35))
    box = (
        max(0, x1 + local_x1 - pad_x),
        max(0, y1 + local_y1 - pad_y),
        min(frame.shape[1], x1 + local_x2 + pad_x),
        min(frame.shape[0], y1 + local_y2 + pad_y),
    )
    confidence = min(0.92, 0.45 + min(0.25, column_runs / 20.0) + min(0.18, coverage * 2.5))
    return box, confidence


def _binary_dilate(mask: Any, *, radius_y: int, radius_x: int) -> Any:
    import numpy as np  # type: ignore

    padded = np.pad(mask, ((radius_y, radius_y), (radius_x, radius_x)), mode="constant")
    out = np.zeros(mask.shape, dtype=bool)
    for y_offset in range(0, radius_y * 2 + 1):
        for x_offset in range(0, radius_x * 2 + 1):
            out |= padded[y_offset : y_offset + mask.shape[0], x_offset : x_offset + mask.shape[1]]
    return out


def _count_true_runs(values: Any) -> int:
    count = 0
    in_run = False
    for value in values:
        if bool(value):
            if not in_run:
                count += 1
                in_run = True
        else:
            in_run = False
    return count


def _select_text_row_window(row_counts: Any, width: int) -> tuple[int, int] | None:
    import numpy as np  # type: ignore

    if row_counts.size == 0:
        return None
    min_pixels = max(2, int(width * 0.003))
    active = _dilate_bool_1d(row_counts >= min_pixels, radius=2)
    runs: list[tuple[int, int, float]] = []
    start: int | None = None
    for index, is_active in enumerate(active):
        if bool(is_active):
            if start is None:
                start = index
        elif start is not None:
            runs.append((start, index, float(np.sum(row_counts[start:index]))))
            start = None
    if start is not None:
        runs.append((start, len(active), float(np.sum(row_counts[start:]))))
    if not runs:
        return None

    max_height = max(9, int(len(active) * 0.46))
    plausible = [run for run in runs if 2 <= run[1] - run[0] <= max_height]
    if not plausible:
        return None
    best_start, best_end, best_score = max(plausible, key=lambda item: item[2])
    if best_score < max(8.0, width * 0.02):
        return None
    return best_start, best_end


def _dilate_bool_1d(values: Any, *, radius: int) -> Any:
    import numpy as np  # type: ignore

    if radius <= 0:
        return values
    padded = np.pad(values, (radius, radius), mode="constant")
    out = np.zeros(values.shape, dtype=bool)
    for offset in range(0, radius * 2 + 1):
        out |= padded[offset : offset + values.shape[0]]
    return out


def _box_matches_subtitle_geometry(
    box: tuple[int, int, int, int],
    geometry: SubtitleGeometryHint,
) -> bool:
    width = box[2] - box[0]
    height = box[3] - box[1]
    if width <= 0 or height <= 0:
        return False
    if geometry.min_width is not None and width < geometry.min_width:
        return False
    if geometry.min_height is not None and height < geometry.min_height:
        return False
    if geometry.max_width is not None and width > geometry.max_width:
        return False
    if geometry.max_height is not None and height > geometry.max_height:
        return False
    center_x = (box[0] + box[2]) / 2.0
    center_y = (box[1] + box[3]) / 2.0
    if (
        geometry.center_x is not None
        and geometry.max_center_dx is not None
        and abs(center_x - geometry.center_x) > geometry.max_center_dx
    ):
        return False
    if (
        geometry.center_y is not None
        and geometry.max_center_dy is not None
        and abs(center_y - geometry.center_y) > geometry.max_center_dy
    ):
        return False
    return True


def _filter_visual_events(
    events: list[VisualFallbackEvent],
    geometry: SubtitleGeometryHint,
) -> list[VisualFallbackEvent]:
    return [event for event in events if _box_matches_subtitle_geometry(event.box, geometry)]


def _merge_visual_hits(
    hits: list[tuple[int, tuple[int, int, int, int], float]],
    *,
    total_frames: int,
    fps: float,
    stride: int,
    lead_frames: int,
    trail_frames: int,
) -> list[VisualFallbackEvent]:
    if not hits:
        return []

    max_gap = max(stride * 2, int(round(fps * 0.35)))
    merged: list[VisualFallbackEvent] = []
    run_start, run_end, box, confidences = _start_visual_run(hits[0], total_frames, stride, lead_frames, trail_frames)

    for hit in hits[1:]:
        frame_idx, hit_box, confidence = hit
        if frame_idx <= run_end + max_gap:
            run_end = min(total_frames - 1, max(run_end, frame_idx + stride * 3 + max(0, trail_frames)))
            box = _union_box(box, hit_box)
            confidences.append(confidence)
            continue
        merged.append(
            VisualFallbackEvent(
                start_frame=run_start,
                end_frame=run_end,
                box=box,
                confidence=sum(confidences) / len(confidences),
            )
        )
        run_start, run_end, box, confidences = _start_visual_run(hit, total_frames, stride, lead_frames, trail_frames)

    merged.append(
        VisualFallbackEvent(
            start_frame=run_start,
            end_frame=run_end,
            box=box,
            confidence=sum(confidences) / len(confidences),
        )
    )
    return merged


def _start_visual_run(
    hit: tuple[int, tuple[int, int, int, int], float],
    total_frames: int,
    stride: int,
    lead_frames: int,
    trail_frames: int,
) -> tuple[int, int, tuple[int, int, int, int], list[float]]:
    frame_idx, box, confidence = hit
    return (
        max(0, frame_idx - stride * 2 - max(0, lead_frames)),
        min(total_frames - 1, frame_idx + stride * 3 + max(0, trail_frames)),
        box,
        [confidence],
    )


def _visual_event_to_payload(
    event: VisualFallbackEvent,
    *,
    index: int,
    fps: float | None,
) -> dict[str, Any]:
    payload = {
        "index": index,
        "start_frame": event.start_frame,
        "end_frame": event.end_frame,
        "text": "",
        "confidence": event.confidence,
        "box": list(event.box),
        "polygon": None,
        "source": "visual_fallback",
    }
    if fps and fps > 0:
        payload["start_time"] = event.start_frame / fps
        payload["end_time"] = event.end_frame / fps
    return payload


def _event_interval(event: dict[str, Any]) -> tuple[int | None, int | None]:
    start = _optional_int(event.get("start_frame"))
    end = _optional_int(event.get("end_frame"))
    if start is None or end is None:
        return None, None
    return start, max(start, end)


def _is_interval_covered(
    candidate: tuple[int, int],
    existing_intervals: list[tuple[int, int]],
) -> bool:
    start, end = candidate
    candidate_frames = max(1, end - start + 1)
    covered = 0
    for existing_start, existing_end in existing_intervals:
        overlap_start = max(start, existing_start)
        overlap_end = min(end, existing_end)
        if overlap_end >= overlap_start:
            covered += overlap_end - overlap_start + 1
    return (covered / candidate_frames) >= 0.5


def _has_nearby_interval(
    candidate: tuple[int, int],
    existing_intervals: list[tuple[int, int]],
    *,
    max_gap_frames: int,
) -> bool:
    if not existing_intervals:
        return False
    start, end = candidate
    max_gap = max(0, max_gap_frames)
    for existing_start, existing_end in existing_intervals:
        if existing_end >= start and existing_start <= end:
            return True
        if existing_start > end and existing_start - end <= max_gap:
            return True
        if start > existing_end and start - existing_end <= max_gap:
            return True
    return False


def _union_box(
    left: tuple[int, int, int, int],
    right: tuple[int, int, int, int],
) -> tuple[int, int, int, int]:
    return (
        min(left[0], right[0]),
        min(left[1], right[1]),
        max(left[2], right[2]),
        max(left[3], right[3]),
    )


def _percentile(values: list[int] | list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * min(100.0, max(0.0, percentile)) / 100.0
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
