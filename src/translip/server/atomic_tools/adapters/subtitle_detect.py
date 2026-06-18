from __future__ import annotations

import json
import sys
from pathlib import Path

from ....orchestration.ocr_bridge import parse_ocr_progress_line
from ....orchestration.subprocess_runner import run_stage_command
from ..cancellation import cancel_checker
from ..registry import ToolSpec, register_tool
from ..schemas import SubtitleDetectToolRequest
from . import ToolAdapter


class SubtitleDetectAdapter(ToolAdapter):
    def validate_params(self, params: dict) -> dict:
        return SubtitleDetectToolRequest(**params).model_dump()

    def run(self, params, input_dir, output_dir, on_progress):
        input_file = self.first_input(input_dir, "file")
        on_progress(5.0, "preparing")

        stage_dir = output_dir
        stage_dir.mkdir(parents=True, exist_ok=True)
        log_path = stage_dir / "ocr_detect.log"

        # In-tree PaddleOCR detection, run in an isolated subprocess so paddle's
        # heavy models are freed on exit (matches the orchestration ocr-detect node).
        cmd = [
            sys.executable,
            "-m",
            "translip.ocr.extract",
            "--input",
            str(input_file),
            "--output-dir",
            str(stage_dir),
            "--language",
            params.get("language", "ch"),
            "--sample-interval",
            str(params.get("sample_interval", 0.4)),
            "--position-mode",
            params.get("position_mode", "auto"),
            "--extraction-mode",
            params.get("extraction_mode", "conservative"),
        ]

        on_progress(15.0, "running_ocr")

        def _forward_progress(line: str) -> None:
            parsed = parse_ocr_progress_line(line)
            if parsed is None:
                return
            # Map the extractor's 0-100 onto this tool's 15-80 band.
            mapped = 15.0 + (80.0 - 15.0) * max(0.0, min(100.0, parsed[0])) / 100.0
            on_progress(mapped, parsed[1])

        run_stage_command(
            cmd,
            log_path=log_path,
            on_stdout_line=_forward_progress,
            should_cancel=cancel_checker(on_progress),
        )

        detection_path = stage_dir / "detection.json"
        if not detection_path.exists():
            raise RuntimeError("OCR detection did not produce detection.json")

        on_progress(80.0, "building_previews")
        detection_payload = json.loads(detection_path.read_text(encoding="utf-8"))
        events = detection_payload.get("events") or detection_payload.get("results") or []

        preview_files = _render_previews(
            video_path=input_file,
            events=events,
            output_dir=stage_dir,
            max_previews=int(params.get("preview_frames", 3)),
        )

        # The per-event language guess + consolidated source_language live in
        # ocr_events.json, not detection.json — read them for the language tally.
        ocr_events_path = stage_dir / "ocr_events.json"
        language_events = events
        source_language: str | None = None
        if ocr_events_path.exists():
            ocr_payload = json.loads(ocr_events_path.read_text(encoding="utf-8"))
            language_events = ocr_payload.get("events") or ocr_payload.get("results") or events
            source_language = ocr_payload.get("source_language")

        summary = _summarize_events(events, language_events=language_events, source_language=source_language)
        summary_path = stage_dir / "summary.json"
        self.write_json(summary_path, summary)

        on_progress(95.0, "collecting_artifacts")
        return {
            "detection_file": detection_path.name,
            # ocr_events.json carries start/end/event_id and is the transcript-correction-friendly OCR export.
            "ocr_events_file": ocr_events_path.name if ocr_events_path.exists() else None,
            "summary_file": summary_path.name,
            "event_count": summary["event_count"],
            "total_subtitle_seconds": summary["total_subtitle_seconds"],
            "dominant_position": summary["dominant_position"],
            "subtitle_language": summary["subtitle_language"],
            "language_breakdown": summary["language_breakdown"],
            "preview_files": [p.name for p in preview_files],
        }


def _summarize_events(
    events: list[dict],
    *,
    language_events: list[dict] | None = None,
    source_language: str | None = None,
) -> dict:
    event_count = len(events)
    total_seconds = 0.0
    position_counts: dict[str, int] = {}
    for ev in events:
        start = float(ev.get("start_time") or ev.get("start") or 0.0)
        end = float(ev.get("end_time") or ev.get("end") or 0.0)
        total_seconds += max(0.0, end - start)
        pos = str(ev.get("position") or ev.get("region") or "bottom")
        position_counts[pos] = position_counts.get(pos, 0) + 1
    dominant = max(position_counts.items(), key=lambda kv: kv[1])[0] if position_counts else "bottom"

    # Subtitle language = per-event script/charset guess (subtitle_detector.
    # _detect_language), majority-voted. This is distinct from the SPOKEN
    # language (use detect-language for that): a clip can be e.g. Japanese audio
    # with Chinese hard subs. The OCR pipeline's consolidated source_language
    # wins when present; otherwise fall back to the per-event majority.
    language_counts: dict[str, int] = {}
    for ev in language_events if language_events is not None else events:
        lang = ev.get("language")
        if lang:
            language_counts[str(lang)] = language_counts.get(str(lang), 0) + 1
    dominant_language = source_language or (
        max(language_counts.items(), key=lambda kv: kv[1])[0] if language_counts else None
    )
    return {
        "event_count": event_count,
        "total_subtitle_seconds": round(total_seconds, 3),
        "dominant_position": dominant,
        "position_breakdown": position_counts,
        "subtitle_language": dominant_language,
        "language_breakdown": language_counts,
    }


def _render_previews(
    *,
    video_path: Path,
    events: list[dict],
    output_dir: Path,
    max_previews: int,
) -> list[Path]:
    if max_previews <= 0 or not events:
        return []
    try:
        import cv2  # type: ignore
    except ImportError:
        return []
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return []
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    preview_paths: list[Path] = []
    try:
        step = max(1, len(events) // max_previews)
        picked = events[::step][:max_previews]
        for idx, ev in enumerate(picked):
            start = float(ev.get("start_time") or ev.get("start") or 0.0)
            end = float(ev.get("end_time") or ev.get("end") or start + 0.1)
            mid_frame = int(((start + end) / 2.0) * fps)
            mid_frame = max(0, min(total - 1, mid_frame)) if total > 0 else max(0, mid_frame)
            cap.set(cv2.CAP_PROP_POS_FRAMES, mid_frame)
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            box = ev.get("box") or ev.get("bbox") or ev.get("region_box")
            if box and len(box) == 4:
                x1, y1, x2, y2 = (int(v) for v in box)
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
                text = str(ev.get("text", "")).strip()
                if text:
                    cv2.putText(
                        frame,
                        text[:30],
                        (x1, max(0, y1 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        (0, 0, 255),
                        2,
                        cv2.LINE_AA,
                    )
            out_path = output_dir / f"preview_{idx:02d}.jpg"
            cv2.imwrite(str(out_path), frame)
            preview_paths.append(out_path)
    finally:
        cap.release()
    return preview_paths


register_tool(
    ToolSpec(
        tool_id="subtitle-detect",
        name_zh="字幕识别（OCR）",
        name_en="Subtitle Detection",
        description_zh="从视频中识别硬字幕位置和文本，输出检测 JSON 和预览图",
        description_en="Detect hardcoded subtitle positions/text from video",
        category="video",
        icon="ScanText",
        accept_formats=[".mp4", ".mkv", ".avi", ".mov"],
        max_file_size_mb=2048,
        max_files=1,
    ),
    SubtitleDetectAdapter,
)
