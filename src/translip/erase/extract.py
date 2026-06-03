#!/usr/bin/env python3
"""In-tree entry point for hard-subtitle erasure (inpainting).

Reads an OCR ``detection.json`` (the same artifact ``translip.ocr.extract``
writes) plus the source video, removes the detected subtitles with the selected
inpainting backend, and writes the cleaned video + manifest the downstream
pipeline expects:

    <output-dir>/clean_video.mp4
    <output-dir>/erase-report.json
    <output-dir>/subtitle-erase-manifest.json

Invoke as a module so it works regardless of install mode:

    python -m translip.erase.extract --input video.mp4 \
        --detection ocr-detect/detection.json --output-dir subtitle-erase/ \
        --backend sttn --device auto
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

# Parsed by orchestration/erase_bridge.py to drive the subtitle-erase progress
# bar. Kept as a literal there too so the bridge stays free of the heavy stack.
PROGRESS_PREFIX = "__ERASE_PROGRESS__"


def _parse_region(value: str) -> tuple[float, float, float, float]:
    parts = [float(p) for p in value.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("--region expects 'x1,y1,x2,y2' normalized floats")
    return (parts[0], parts[1], parts[2], parts[3])


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="translip in-tree subtitle erasure")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--detection", default=None, help="OCR detection.json (omit when using --region)")
    parser.add_argument("--backend", default="sttn", choices=["sttn", "lama"])
    parser.add_argument("--device", default="auto", choices=["auto", "mps", "cuda", "cpu"])
    parser.add_argument("--mask-dilate-x", type=int, default=12)
    parser.add_argument("--mask-dilate-y", type=int, default=8)
    parser.add_argument("--neighbor-stride", type=int, default=5)
    parser.add_argument("--reference-length", type=int, default=10)
    parser.add_argument("--max-load", type=int, default=50)
    parser.add_argument("--region", action="append", type=_parse_region, default=None)
    parser.add_argument("--output-name", default="clean_video.mp4")
    # Accepted for backward compatibility with the old external-bridge callers; ignored.
    parser.add_argument("--project-root", default=None, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def erase_to_dir(
    *,
    input_path: Path,
    output_dir: Path,
    detection_path: Path | None,
    backend: str = "sttn",
    device: str = "auto",
    mask_dilate_x: int = 12,
    mask_dilate_y: int = 8,
    neighbor_stride: int = 5,
    reference_length: int = 10,
    max_load: int = 50,
    regions: list[tuple[float, float, float, float]] | None = None,
    output_name: str = "clean_video.mp4",
) -> dict:
    """Run subtitle erasure and write the clean video + report + manifest.

    Returns the manifest dict written to ``subtitle-erase-manifest.json``.
    """
    # Imported lazily so plain `python -m translip.erase.extract --help` and the
    # bridge stay cheap; cv2/torch only load when an erase actually runs.
    from translip.erase.services.erase_service import EraseService

    input_path = input_path.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    clean_video = output_dir / output_name
    report_path = output_dir / "erase-report.json"
    manifest_path = output_dir / "subtitle-erase-manifest.json"

    def _on_progress(progress: int, message: str) -> None:
        print(f"{PROGRESS_PREFIX}\t{int(progress)}\t{message}", flush=True)

    result = EraseService().erase(
        video_path=input_path,
        detection_path=detection_path,
        output_path=clean_video,
        backend=backend,
        device=device,
        mask_dilate_x=mask_dilate_x,
        mask_dilate_y=mask_dilate_y,
        neighbor_stride=neighbor_stride,
        reference_length=reference_length,
        max_load=max_load,
        regions=regions,
        progress_callback=_on_progress,
    )

    video_info = {
        "fps": result.video.fps,
        "width": result.video.width,
        "height": result.video.height,
        "total_frames": result.video.total_frames,
        "duration": result.video.duration,
    }
    report = {
        "backend": result.backend.value,
        "device": result.device,
        "video": video_info,
        "erased_ranges": [list(r) for r in result.erased_ranges],
        "processed_frames": result.processed_frames,
        "audio_muxed": result.audio_muxed,
        "detection_json": str(detection_path) if detection_path is not None else None,
    }
    _write_json(report_path, report)

    manifest = {
        "status": "succeeded",
        "backend": result.backend.value,
        "device": result.device,
        "artifacts": {
            "clean_video": str(clean_video),
            "erase_report": str(report_path),
            "detection_json": str(detection_path) if detection_path is not None else None,
        },
        "video": video_info,
        "erased_range_count": len(result.erased_ranges),
        "audio_muxed": result.audio_muxed,
    }
    _write_json(manifest_path, manifest)
    return manifest


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    erase_to_dir(
        input_path=Path(args.input),
        output_dir=Path(args.output_dir),
        detection_path=Path(args.detection) if args.detection else None,
        backend=args.backend,
        device=args.device,
        mask_dilate_x=args.mask_dilate_x,
        mask_dilate_y=args.mask_dilate_y,
        neighbor_stride=args.neighbor_stride,
        reference_length=args.reference_length,
        max_load=args.max_load,
        regions=args.region,
        output_name=args.output_name,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
