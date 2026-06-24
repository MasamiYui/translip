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

        # Carry video geometry forward to the frontend overlay. The OCR extractor
        # already writes `video.{width,height,fps,total_frames}` into detection.json,
        # but we surface it on the tool result so the UI does not have to fetch
        # detection.json just to read intrinsic size.
        video_block = detection_payload.get("video") or {}
        video_meta = {
            "width": int(video_block.get("width") or 0),
            "height": int(video_block.get("height") or 0),
            "fps": float(video_block.get("fps") or 0.0),
            "total_frames": int(video_block.get("total_frames") or 0),
        }

        preview_files, keyframe_files, keyframes_index = _render_previews(
            video_path=input_file,
            events=events,
            output_dir=stage_dir,
            max_previews=int(params.get("preview_frames", 3)),
            keyframe_density=int(params.get("preview_keyframe_density", 3)),
            with_annotations=bool(params.get("preview_with_annotations", True)),
        )

        # Persist the keyframe ↔ events mapping so the interactive preview can
        # restore its state without re-deriving it on the client. Only written
        # when at least one keyframe was produced.
        keyframes_file_name: str | None = None
        if keyframe_files:
            keyframes_path = stage_dir / "keyframes.json"
            keyframes_path.write_text(
                json.dumps(
                    {"video": video_meta, "frames": keyframes_index},
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            keyframes_file_name = keyframes_path.name

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
            # New: clean keyframes + their event mapping power the interactive
            # overlay in the UI. Old consumers ignore unknown fields.
            "keyframe_files": [k.name for k in keyframe_files],
            "keyframes_file": keyframes_file_name,
            "video_meta": video_meta,
            # Observability hint for the UI: which uploaded file was processed.
            # No HTTP route currently serves this file_id directly, so the
            # frontend still primarily relies on its blob URL from the upload step.
            "source_filename": input_file.name,
            "source_file_id": str(params.get("file_id") or ""),
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
    keyframe_density: int = 0,
    with_annotations: bool = True,
) -> tuple[list[Path], list[Path], list[dict]]:
    """Render preview frames for the subtitle-detect atomic tool.

    Returns a 3-tuple ``(annotated_paths, clean_keyframe_paths, keyframes_index)``:

    * ``annotated_paths``  — legacy ``preview_NN.jpg`` with the red box / text
      burned in. Kept for backward-compatible CLI / lab consumers; controlled by
      ``with_annotations``.
    * ``clean_keyframe_paths`` — ``kf_NN.jpg`` without any overlay. The interactive
      preview UI loads these and draws an SVG overlay on top.
    * ``keyframes_index`` — list of ``{frame_index, timestamp, image, event_ids}``
      records, one per clean keyframe, persisted as ``keyframes.json``.

    Either branch can be disabled by passing 0 to the corresponding density.
    """
    sample_count = max(max_previews if with_annotations else 0, keyframe_density)
    if sample_count <= 0 or not events:
        return [], [], []
    try:
        import cv2  # type: ignore
    except ImportError:
        return [], [], []
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return [], [], []
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    annotated_paths: list[Path] = []
    keyframe_paths: list[Path] = []
    keyframes_index: list[dict] = []
    try:
        step = max(1, len(events) // sample_count)
        picked = events[::step][:sample_count]
        for idx, ev in enumerate(picked):
            start = float(ev.get("start_time") or ev.get("start") or 0.0)
            end = float(ev.get("end_time") or ev.get("end") or start + 0.1)
            mid_time = (start + end) / 2.0
            mid_frame = int(mid_time * fps)
            mid_frame = max(0, min(total - 1, mid_frame)) if total > 0 else max(0, mid_frame)
            cap.set(cv2.CAP_PROP_POS_FRAMES, mid_frame)
            ok, frame = cap.read()
            if not ok or frame is None:
                continue

            # Clean keyframe (no overlay) — used by the interactive UI as a
            # poster image + frame-by-frame fallback before the <video> seeks.
            if idx < keyframe_density:
                kf_path = output_dir / f"kf_{idx:02d}.jpg"
                cv2.imwrite(str(kf_path), frame)
                keyframe_paths.append(kf_path)
                # Collect every event whose [start_time, end_time] window covers
                # this keyframe — that is exactly what the overlay shows when
                # the video is paused at this timestamp.
                event_ids = [
                    str(other.get("event_id") or "")
                    for other in events
                    if str(other.get("event_id") or "")
                    and float(other.get("start_time") or other.get("start") or 0.0) <= mid_time
                    <= float(other.get("end_time") or other.get("end") or 0.0)
                ]
                keyframes_index.append(
                    {
                        "frame_index": mid_frame,
                        "timestamp": round(mid_time, 3),
                        "image": kf_path.name,
                        "event_ids": event_ids,
                    }
                )

            # Legacy annotated preview (red box + truncated text) — only emitted
            # when the caller still wants it.
            if with_annotations and idx < max_previews:
                annotated = frame.copy()
                box = ev.get("box") or ev.get("bbox") or ev.get("region_box")
                if box and len(box) == 4:
                    x1, y1, x2, y2 = (int(v) for v in box)
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 0, 255), 2)
                    text = str(ev.get("text", "")).strip()
                    if text:
                        cv2.putText(
                            annotated,
                            text[:30],
                            (x1, max(0, y1 - 6)),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.6,
                            (0, 0, 255),
                            2,
                            cv2.LINE_AA,
                        )
                out_path = output_dir / f"preview_{idx:02d}.jpg"
                cv2.imwrite(str(out_path), annotated)
                annotated_paths.append(out_path)
    finally:
        cap.release()
    return annotated_paths, keyframe_paths, keyframes_index


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
        max_file_size_mb=4096,
        max_files=1,
    ),
    SubtitleDetectAdapter,
)
