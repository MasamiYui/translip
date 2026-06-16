from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("cv2")  # erase extra (opencv-contrib); skip cleanly without it (e.g. CI base)
pytest.importorskip("pydantic_settings")

from translip.erase.core import planning
from translip.erase.core.masks import create_mask, get_inpaint_bands
from translip.erase.models.domain import EraseBackend


def test_subtitle_frames_converts_box_order_and_drops_tall_thin() -> None:
    events = [
        # Horizontal subtitle line -> kept; box [x1,y1,x2,y2] -> (xmin,xmax,ymin,ymax)
        {"start_frame": 2, "end_frame": 4, "box": [100, 300, 340, 360]},
        # Tall-thin vertical element -> dropped (height-width skew > yx_diff_px)
        {"start_frame": 2, "end_frame": 2, "box": [10, 20, 30, 200]},
    ]
    frames = planning.subtitle_frames(events, yx_diff_px=10)
    assert set(frames.keys()) == {2, 3, 4}
    assert frames[2] == [(100, 340, 300, 360)]
    assert frames[3] == [(100, 340, 300, 360)]


def test_subtitle_frames_unions_polygon_wider_than_median_box() -> None:
    # The OCR median `box` under-sizes long lines; the wider `polygon` carries the
    # true text extent, so the mask box must cover the polygon (not just the box).
    events = [
        {
            "start_frame": 1,
            "end_frame": 1,
            "box": [521, 622, 756, 717],  # 235px-wide median box
            "polygon": [[441, 655], [839, 655], [839, 690], [441, 690]],  # 398px text
        }
    ]
    frames = planning.subtitle_frames(events, yx_diff_px=10)
    # x spans the polygon (441..839); y unions the padded box band (622..717).
    assert frames[1] == [(441, 839, 622, 717)]


def test_subtitle_frames_keeps_box_when_wider_than_polygon() -> None:
    # When the box is already wider (short line, padded box), unioning is a no-op.
    events = [
        {
            "start_frame": 3,
            "end_frame": 3,
            "box": [400, 600, 720, 760],  # x 400..720, y 600..760
            "polygon": [[450, 725], [560, 725], [560, 755], [450, 755]],  # x 450..560
        }
    ]
    frames = planning.subtitle_frames(events, yx_diff_px=10)
    assert frames[3] == [(400, 720, 600, 760)]


def test_plan_ranges_groups_and_merges_to_reference_length() -> None:
    events = [{"start_frame": 10, "end_frame": 12, "box": [100, 300, 340, 360]}]
    frames = planning.subtitle_frames(events)
    ranges = planning.plan_ranges(frames, total_frames=100, reference_length=10)
    assert ranges == [(10, 12)]
    # clamped to the last frame
    ranges_clamped = planning.plan_ranges(frames, total_frames=11, reference_length=10)
    assert ranges_clamped == [(10, 10)]


def test_boxes_for_range_unions_and_filters() -> None:
    frames = {
        5: [(100, 340, 300, 360)],
        6: [(100, 340, 300, 360), (400, 600, 300, 360)],
    }
    boxes = planning.boxes_for_range(frames, 5, 6)
    assert (100, 340, 300, 360) in boxes
    assert (400, 600, 300, 360) in boxes
    assert len(boxes) == 2


def test_regions_to_frames_scales_normalized_to_pixels() -> None:
    frames = planning.regions_to_frames(
        [(0.0, 0.8, 1.0, 0.95)], width=1000, height=200, total_frames=3
    )
    assert set(frames.keys()) == {0, 1, 2}
    assert frames[0] == [(0, 1000, 160, 190)]


def test_create_mask_dilates_and_fills() -> None:
    mask = create_mask((200, 400), [(100, 300, 150, 170)], dilate_x=10, dilate_y=5)
    assert mask.shape == (200, 400)
    assert mask.dtype == np.uint8
    # Inside the dilated rectangle is white, far outside is black.
    assert mask[160, 200] == 255
    assert mask[145, 95] == 255  # dilated edge (150-5, 100-10)
    assert mask[10, 10] == 0


def test_get_inpaint_bands_brackets_the_mask() -> None:
    mask = np.zeros((720, 1280), dtype=np.uint8)
    mask[640:680, 200:1000] = 255  # bottom subtitle band
    bands = get_inpaint_bands(1280, 720, band_height=355, mask=mask)
    assert len(bands) == 1
    ymin, ymax = bands[0]
    assert ymin <= 640 and ymax >= 680
    assert (ymax - ymin) == 355


def test_get_inpaint_bands_empty_mask_returns_nothing() -> None:
    assert get_inpaint_bands(640, 360, 100, np.zeros((360, 640), np.uint8)) == []


def test_erase_extract_sttn_empty_events_stream_copies(tmp_path: Path) -> None:
    """Smoke test for extract.erase_to_dir without requiring downloaded weights.

    Empty events trigger the stream-copy passthrough, so no inpainting backend is
    actually instantiated; we still exercise the CLI path with backend=sttn.
    """
    cv2 = pytest.importorskip("cv2")
    from translip.erase.extract import erase_to_dir

    width, height, frames, fps = 320, 176, 24, 24.0
    src = tmp_path / "src.mp4"
    writer = cv2.VideoWriter(str(src), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    for i in range(frames):
        writer.write(np.full((height, width, 3), (i * 7) % 255, np.uint8))
    writer.release()

    detection = {
        "video": {"fps": fps, "width": width, "height": height, "total_frames": frames, "duration": frames / fps},
        "events": [],
    }
    detection_path = tmp_path / "detection.json"
    detection_path.write_text(json.dumps(detection), encoding="utf-8")

    output_dir = tmp_path / "subtitle-erase"
    manifest = erase_to_dir(
        input_path=src,
        output_dir=output_dir,
        detection_path=detection_path,
        backend="sttn",
    )

    clean = output_dir / "clean_video.mp4"
    assert manifest["status"] == "succeeded"
    assert manifest["backend"] == "sttn"
    assert clean.exists()
    assert (output_dir / "subtitle-erase-manifest.json").exists()


def test_erase_empty_detection_stream_copies(tmp_path: Path) -> None:
    """No detected subtitles -> container-copy passthrough, not a lossy re-encode."""
    cv2 = pytest.importorskip("cv2")
    from translip.erase.extract import erase_to_dir

    width, height, frames, fps = 320, 176, 12, 24.0
    src = tmp_path / "src.mp4"
    writer = cv2.VideoWriter(str(src), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    for i in range(frames):
        writer.write(np.full((height, width, 3), (i * 11) % 255, np.uint8))
    writer.release()

    detection_path = tmp_path / "detection.json"
    detection_path.write_text(
        json.dumps({"video": {"fps": fps, "width": width, "height": height, "total_frames": frames}, "events": []}),
        encoding="utf-8",
    )

    output_dir = tmp_path / "subtitle-erase"
    manifest = erase_to_dir(input_path=src, output_dir=output_dir, detection_path=detection_path, backend="sttn")
    assert manifest["status"] == "succeeded"
    assert manifest["erased_range_count"] == 0
    assert (output_dir / "clean_video.mp4").exists()


def test_erase_backend_enum_values() -> None:
    assert {b.value for b in EraseBackend} == {"sttn", "lama"}
