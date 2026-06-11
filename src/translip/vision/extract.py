#!/usr/bin/env python3
"""In-tree entry point for video content analysis (Qwen3-VL).

Samples frames per analysis unit, runs the vision-language model, and writes
the per-task artifact + manifest contract downstream consumers expect:

    <output-dir>/visual_context.json            (scene-context)
    <output-dir>/erase_qc_report.json           (erase-qc)
    <output-dir>/ocr_events.classified.json     (ocr-classify)
    <output-dir>/speaker_visual.json            (speaker-visual)
    <output-dir>/freeform_answer.json           (freeform)
    <output-dir>/<task>-manifest.json

Invoke as a module so it works regardless of install mode:

    python -m translip.vision.extract --input video.mp4 \
        --task scene-context --output-dir visual-context/ \
        [--segments segments.zh.json] [--backend auto]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

# Parsed by orchestration/vision_bridge.py and the video-analyze atomic tool to
# drive progress bars. Kept as a literal there too so callers stay light.
PROGRESS_PREFIX = "__VISION_PROGRESS__"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="translip in-tree video content analysis")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--task",
        default="scene-context",
        choices=["scene-context", "erase-qc", "ocr-classify", "speaker-visual", "freeform"],
    )
    parser.add_argument(
        "--segments",
        default=None,
        help="Task-A segments JSON; omit to fall back to fixed-interval units",
    )
    parser.add_argument(
        "--detection",
        default=None,
        help="OCR ocr_events.json / detection.json (required for ocr-classify)",
    )
    parser.add_argument("--question", default=None, help="Free-form question (task=freeform)")
    parser.add_argument(
        "--sample-interval",
        type=float,
        default=10.0,
        help="Unit length in seconds when no --segments is given",
    )
    parser.add_argument("--backend", default=None, choices=["auto", "mlx", "ollama"])
    parser.add_argument("--frames-per-unit", type=int, default=None)
    parser.add_argument("--lang", default="zh", choices=["zh", "en"])
    parser.add_argument("--max-units", type=int, default=None, help="Evenly subsample to at most N units")
    return parser.parse_args(argv)


def analyze_to_dir(
    *,
    input_path: Path,
    output_dir: Path,
    task: str = "scene-context",
    segments_path: Path | None = None,
    detection_path: Path | None = None,
    question: str | None = None,
    sample_interval_sec: float = 10.0,
    backend: str | None = None,
    frames_per_unit: int | None = None,
    lang: str = "zh",
    max_units: int | None = None,
) -> dict:
    """Run vision analysis and write artifact + manifest; returns the manifest."""
    # Imported lazily so `--help` and the bridge stay cheap; the model stack
    # only loads when an analysis actually runs.
    from translip.vision.services.vision_service import AnalyzeRequest, analyze_video

    def _on_progress(percent: float, message: str) -> None:
        print(f"{PROGRESS_PREFIX}\t{int(percent)}\t{message}", flush=True)

    result = analyze_video(
        AnalyzeRequest(
            input_path=input_path.expanduser().resolve(),
            output_dir=output_dir.expanduser().resolve(),
            task=task,
            segments_path=segments_path.expanduser().resolve() if segments_path else None,
            detection_path=detection_path.expanduser().resolve() if detection_path else None,
            question=question,
            sample_interval_sec=sample_interval_sec,
            backend=backend,
            frames_per_unit=frames_per_unit,
            lang=lang,
            max_units=max_units,
        ),
        progress_callback=_on_progress,
    )
    return result.manifest


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    manifest = analyze_to_dir(
        input_path=Path(args.input),
        output_dir=Path(args.output_dir),
        task=args.task,
        segments_path=Path(args.segments) if args.segments else None,
        detection_path=Path(args.detection) if args.detection else None,
        question=args.question,
        sample_interval_sec=float(args.sample_interval),
        backend=args.backend,
        frames_per_unit=args.frames_per_unit,
        lang=args.lang,
        max_units=args.max_units,
    )
    # Final stdout line is the manifest JSON (same convention as ocr/erase).
    print(json.dumps(manifest, ensure_ascii=False))
    return 0 if manifest.get("status") == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
