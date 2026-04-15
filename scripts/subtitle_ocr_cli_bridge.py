#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from enum import Enum
from pathlib import Path

import cv2


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local bridge for subtitle-ocr")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--language", default="auto")
    parser.add_argument("--sample-interval", type=float, default=0.25)
    return parser.parse_args()


def _ffprobe_json(video_path: Path) -> dict:
    ffprobe = shutil.which("ffprobe") or "ffprobe"
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(video_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def _parse_fps(raw: str | None) -> float:
    if not raw:
        return 0.0
    if "/" in raw:
        left, right = raw.split("/", 1)
        denominator = float(right or 1.0)
        if denominator == 0:
            return 0.0
        return float(left) / denominator
    return float(raw)


def _video_info(video_path: Path) -> dict[str, float | int]:
    payload = _ffprobe_json(video_path)
    streams = payload.get("streams", [])
    format_info = payload.get("format", {})
    video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), {})
    duration = float(format_info.get("duration") or video_stream.get("duration") or 0.0)
    fps = _parse_fps(video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate"))
    reported_total_frames = int(video_stream.get("nb_frames") or round(duration * fps) or 0)
    readable_total_frames = _readable_total_frames(video_path, reported_total_frames)
    total_frames = readable_total_frames or reported_total_frames
    return {
        "fps": fps,
        "total_frames": total_frames,
        "reported_total_frames": reported_total_frames,
        "readable_total_frames": readable_total_frames,
        "width": int(video_stream.get("width") or 0),
        "height": int(video_stream.get("height") or 0),
        "duration": duration,
    }


def _readable_total_frames(video_path: Path, reported_total_frames: int) -> int | None:
    if reported_total_frames <= 0:
        return None
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return None
    try:
        low = 0
        high = reported_total_frames - 1
        highest_readable = -1
        while low <= high:
            mid = (low + high) // 2
            cap.set(cv2.CAP_PROP_POS_FRAMES, mid)
            ok, _ = cap.read()
            if ok:
                highest_readable = mid
                low = mid + 1
                continue
            high = mid - 1
        if highest_readable < 0:
            return None
        return highest_readable + 1
    finally:
        cap.release()


def _canonical_language(language: str) -> str:
    return {
        "ch": "zh",
        "japan": "ja",
        "korean": "ko",
    }.get(language, language)


def _time_to_frame(timestamp: float, fps: float) -> int:
    return max(0, int(round(timestamp * fps)))


def _jsonable(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "__dict__"):
        return {key: _jsonable(item) for key, item in value.__dict__.items()}
    return value


def main() -> int:
    args = _parse_args()
    project_root = Path(args.project_root).expanduser().resolve()
    input_path = Path(args.input).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from services.subtitle_service import SubtitleService

    service = SubtitleService()
    result = service.extract_subtitles(
        video_path=str(input_path),
        language=args.language,
        sample_interval=float(args.sample_interval),
        detect_region=True,
    )
    srt_content = service.generate_srt(result)
    video_info = _video_info(input_path)
    language = _canonical_language(getattr(result.language, "value", args.language))
    fps = float(video_info["fps"])

    events = []
    detection_events = []
    for index, subtitle in enumerate(result.subtitles, start=1):
        start_time = float(subtitle.start_time)
        end_time = float(subtitle.end_time)
        start_frame = _time_to_frame(start_time, fps)
        end_frame = max(start_frame, _time_to_frame(end_time, fps))
        polygon = subtitle.polygon or []
        box = list(subtitle.box) if subtitle.box else [0, 0, 0, 0]
        event_payload = {
            "event_id": f"evt-{index:04d}",
            "index": index,
            "start": start_time,
            "end": end_time,
            "start_frame": start_frame,
            "end_frame": end_frame,
            "text": subtitle.text,
            "language": language,
            "confidence": float(subtitle.confidence),
            "box": box,
            "polygon": polygon,
        }
        events.append(event_payload)
        detection_events.append(
            {
                "index": index,
                "start_time": start_time,
                "end_time": end_time,
                "start_frame": start_frame,
                "end_frame": end_frame,
                "text": subtitle.text,
                "confidence": float(subtitle.confidence),
                "box": box,
                "polygon": polygon,
            }
        )

    (output_dir / "ocr_events.json").write_text(
        json.dumps(
            {
                "video": video_info,
                "events": events,
                "anchors": [_jsonable(anchor) for anchor in result.anchors],
                "anchor_debug": _jsonable(result.anchor_debug),
                "source_language": language,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "detection.json").write_text(
        json.dumps(
            {
                "video": video_info,
                "mode": "auto",
                "requested_regions": None,
                "anchors": [_jsonable(anchor) for anchor in result.anchors],
                "events": detection_events,
                "anchor_debug": _jsonable(result.anchor_debug),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "ocr_subtitles.source.srt").write_text(srt_content, encoding="utf-8")
    (output_dir / "ocr-detect-manifest.json").write_text(
        json.dumps(
            {
                "status": "succeeded",
                "source_language": language,
                "artifacts": {
                    "ocr_events_json": str(output_dir / "ocr_events.json"),
                    "detection_json": str(output_dir / "detection.json"),
                    "source_srt": str(output_dir / "ocr_subtitles.source.srt"),
                },
                "video": video_info,
                "event_count": len(events),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
