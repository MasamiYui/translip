"""High-level subtitle-erase facade.

Reads an OCR ``detection.json`` (or manual regions), plans the masked frame
ranges, runs the chosen inpainting backend over the subtitle frames only, and
writes a cleaned video with the original audio re-muxed. This is the single
heavy public entry point of :mod:`translip.erase` (it pulls cv2/torch), so it is
exposed lazily from the package ``__init__``.
"""
from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from ..config import settings
from ..core import planning
from ..core.backends import InpaintBackend, LamaBackend, SttnBackend
from ..core.masks import create_mask
from ..core.video_io import FFmpegVideoWriter, FramePrefetcher, has_audio_stream, remux_audio, stream_copy
from ..models.domain import EraseBackend, EraseResult, VideoInfo
from ..utils.devices import resolve_device

ProgressCallback = Callable[[int, str], None]


class EraseService:
    def erase(
        self,
        *,
        video_path: str | Path,
        detection_path: str | Path | None,
        output_path: str | Path,
        backend: str = "sttn",
        device: str = "auto",
        mask_dilate_x: int = 12,
        mask_dilate_y: int = 8,
        neighbor_stride: int = 5,
        reference_length: int = 10,
        max_load: int = 50,
        regions: list[tuple[float, float, float, float]] | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> EraseResult:
        video_path = Path(video_path)
        output_path = Path(output_path)
        backend_kind = EraseBackend(backend)

        detection = _load_detection(detection_path)
        video = _video_info(video_path, detection)
        frames_plan = _build_frame_plan(detection, regions, video)
        ranges = planning.plan_ranges(
            frames_plan, total_frames=video.total_frames, reference_length=reference_length
        )

        engine = self._make_backend(
            backend_kind,
            device=device,
            neighbor_stride=neighbor_stride,
            reference_length=reference_length,
            progress_callback=progress_callback,
        )

        result = _run(
            video_path=video_path,
            output_path=output_path,
            video=video,
            frames_plan=frames_plan,
            ranges=ranges,
            engine=engine,
            backend_kind=backend_kind,
            device=str(engine_device(engine)),
            mask_dilate_x=mask_dilate_x,
            mask_dilate_y=mask_dilate_y,
            max_load=max_load,
            yx_diff_px=settings.ERASE_YX_DIFF_PX,
            progress_callback=progress_callback,
        )
        return result

    def _make_backend(
        self,
        kind: EraseBackend,
        *,
        device: str,
        neighbor_stride: int,
        reference_length: int,
        progress_callback: ProgressCallback | None,
    ) -> InpaintBackend:
        from ..utils.weights import ensure_weight

        torch_device = resolve_device(device)
        models_dir = Path(settings.SUBTITLE_ERASE_MODELS_DIR).expanduser()
        local_only = settings.SUBTITLE_ERASE_LOCAL_MODELS_ONLY

        def _weight_progress(message: str) -> None:
            if progress_callback is not None:
                progress_callback(2, message)

        if kind is EraseBackend.STTN:
            weight = ensure_weight("sttn", models_dir=models_dir, local_only=local_only, on_progress=_weight_progress)
            return SttnBackend(
                device=torch_device,
                model_path=weight,
                neighbor_stride=neighbor_stride,
                reference_length=reference_length,
            )
        weight = ensure_weight("lama", models_dir=models_dir, local_only=local_only, on_progress=_weight_progress)
        return LamaBackend(device=torch_device, model_path=weight)


def engine_device(engine: InpaintBackend) -> Any:
    return getattr(engine, "device", "cpu")


def _load_detection(detection_path: str | Path | None) -> dict[str, Any]:
    if detection_path is None:
        return {}
    payload = json.loads(Path(detection_path).read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _video_info(video_path: Path, detection: dict[str, Any]) -> VideoInfo:
    video = detection.get("video") if isinstance(detection.get("video"), dict) else {}
    fps = _as_float(video.get("fps"))
    width = _as_int(video.get("width"))
    height = _as_int(video.get("height"))
    total = _as_int(video.get("total_frames") or video.get("readable_total_frames"))
    if not (fps and width and height and total):
        cap = cv2.VideoCapture(str(video_path))
        try:
            fps = fps or float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
            width = width or int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            height = height or int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
            total = total or int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        finally:
            cap.release()
    return VideoInfo(
        fps=float(fps or 25.0),
        width=int(width or 0),
        height=int(height or 0),
        total_frames=int(total or 0),
        duration=_as_float(video.get("duration")) or 0.0,
    )


def _build_frame_plan(
    detection: dict[str, Any],
    regions: list[tuple[float, float, float, float]] | None,
    video: VideoInfo,
) -> planning.FrameBoxes:
    if regions:
        return planning.regions_to_frames(
            regions, width=video.width, height=video.height, total_frames=video.total_frames
        )
    events = detection.get("events")
    if not isinstance(events, list):
        return {}
    return planning.subtitle_frames(events, yx_diff_px=settings.ERASE_YX_DIFF_PX)


def _run(
    *,
    video_path: Path,
    output_path: Path,
    video: VideoInfo,
    frames_plan: planning.FrameBoxes,
    ranges: list[tuple[int, int]],
    engine: InpaintBackend,
    backend_kind: EraseBackend,
    device: str,
    mask_dilate_x: int,
    mask_dilate_y: int,
    max_load: int,
    yx_diff_px: int,
    progress_callback: ProgressCallback | None,
) -> EraseResult:
    if video.width <= 0 or video.height <= 0 or video.total_frames <= 0:
        raise ValueError(
            f"Cannot erase: invalid video geometry ({video.width}x{video.height}, "
            f"{video.total_frames} frames). Check the input video and detection.json."
        )

    # Nothing detected to erase: container-copy the source instead of running a
    # pointless lossy re-encode, and make the no-op explicit.
    if not ranges:
        if progress_callback is not None:
            progress_callback(50, "no subtitle regions to erase — copying source")
        stream_copy(video_path, output_path)
        if progress_callback is not None:
            progress_callback(100, "done")
        return EraseResult(
            clean_video=str(output_path),
            backend=backend_kind,
            device=device,
            video=video,
            erased_ranges=[],
            processed_frames=video.total_frames,
            audio_muxed=has_audio_stream(video_path),
        )

    start_map = {start: end for start, end in ranges}
    total = video.total_frames or 0
    temp_video = output_path.with_name(output_path.stem + ".video-only.mp4")

    capture = cv2.VideoCapture(str(video_path))
    reader = FramePrefetcher(capture)
    writer = FFmpegVideoWriter(
        temp_video,
        video.fps,
        (video.width, video.height),
        crf=settings.ERASE_X264_CRF,
        preset=settings.ERASE_X264_PRESET,
    )

    processed = 0
    erased_ranges: list[tuple[int, int]] = []

    def _report() -> None:
        if progress_callback is not None and total > 0:
            progress_callback(min(97, int(processed / total * 95) + 2), f"erasing subtitles ({processed}/{total})")

    try:
        index = -1
        while True:
            ok, frame = reader.read()
            if not ok:
                break
            index += 1
            if index not in start_map:
                writer.write(frame)
                processed += 1
                if processed % 50 == 0:
                    _report()
                continue

            start = index
            end = start_map[index]
            batch = [frame]
            while index < end:
                ok, frame = reader.read()
                if not ok:
                    break
                index += 1
                batch.append(frame)

            boxes = planning.boxes_for_range(frames_plan, start, end, yx_diff_px=yx_diff_px)
            if boxes:
                mask = create_mask((video.height, video.width), boxes, dilate_x=mask_dilate_x, dilate_y=mask_dilate_y)
                erased_ranges.append((start, start + len(batch) - 1))
                for chunk in _chunks(batch, max_load):
                    for cleaned in engine(chunk, mask):
                        writer.write(cleaned)
                        processed += 1
            else:
                for passthrough in batch:
                    writer.write(passthrough)
                    processed += 1
            _report()
    finally:
        reader.stop()
        capture.release()
        writer.release()

    if progress_callback is not None:
        progress_callback(98, "muxing audio")
    audio_muxed = remux_audio(temp_video, video_path, output_path)
    temp_video.unlink(missing_ok=True)
    if progress_callback is not None:
        progress_callback(100, "done")

    return EraseResult(
        clean_video=str(output_path),
        backend=backend_kind,
        device=device,
        video=video,
        erased_ranges=erased_ranges,
        processed_frames=processed,
        audio_muxed=audio_muxed,
    )


def _chunks(items: list, max_size: int) -> Iterator[list]:
    count = len(items)
    if count <= max_size or max_size < 1:
        yield items
        return
    num_batches = (count + max_size - 1) // max_size
    size = (count + num_batches - 1) // num_batches
    for start in range(0, count, size):
        yield items[start : start + size]


def _as_int(value: Any) -> int | None:
    try:
        result = int(round(float(value)))
        return result if result > 0 else None
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


__all__ = ["EraseService"]
