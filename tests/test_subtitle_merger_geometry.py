from __future__ import annotations

from translip.ocr.core.subtitle_merger import SubtitleMerger
from translip.ocr.models.domain import DetectedText


def _det(text: str, box, *, conf: float = 0.9, ts: float = 0.0, idx: int = 0) -> DetectedText:
    return DetectedText(text=text, confidence=conf, box=box, timestamp=ts, frame_index=idx)


def test_full_extent_covers_long_line_even_from_low_confidence_frame() -> None:
    # Most frames show a short line; one (lower-confidence) frame shows the full
    # long line. The median box underestimates the width, but box_full_extent must
    # capture the true span so erase/overlay don't clip it (SUB-3).
    merger = SubtitleMerger()
    detections = [
        _det("hello", (10, 100, 110, 120), conf=0.95, ts=0.0, idx=0),
        _det("hello", (10, 100, 110, 120), conf=0.95, ts=0.1, idx=1),
        _det("hello world there", (10, 100, 310, 120), conf=0.5, ts=0.2, idx=2),
    ]

    stable_box, _polygon, _rotated, full_extent, debug = merger._compute_stable_geometry(detections)

    # median-based box stays near the short width…
    assert stable_box[2] < 200
    # …but the union reaches the long frame's right edge (plus padding).
    assert full_extent[2] >= 310
    # full extent never shrinks below the stable box on any side.
    assert full_extent[0] <= stable_box[0]
    assert full_extent[1] <= stable_box[1]
    assert full_extent[2] >= stable_box[2]
    assert full_extent[3] >= stable_box[3]
    assert debug["full_extent"] == list(full_extent)


def test_full_extent_equals_stable_box_for_single_detection() -> None:
    merger = SubtitleMerger()
    stable_box, _polygon, _rotated, full_extent, _debug = merger._compute_stable_geometry(
        [_det("solo", (10, 100, 120, 130))]
    )
    assert full_extent == stable_box


def test_merge_detected_texts_attaches_full_extent_to_subtitle() -> None:
    merger = SubtitleMerger()
    subtitles = merger.merge_detected_texts(
        [
            _det("一行字幕", (10, 100, 110, 120), conf=0.9, ts=0.0, idx=0),
            _det("一行字幕", (10, 100, 320, 120), conf=0.9, ts=0.2, idx=1),
        ]
    )
    assert subtitles
    sub = subtitles[0]
    assert sub.box_full_extent is not None
    assert sub.box_full_extent[2] >= sub.box[2]
