from __future__ import annotations

import pytest

from translip.vision.frames import (
    AnalysisUnit,
    frame_times_for_unit,
    units_from_events,
    units_from_interval,
    units_from_segments,
)


def test_units_from_segments_groups_by_gap_and_caps() -> None:
    segments = [
        {"id": "seg-0001", "start": 0.0, "end": 2.0},
        {"id": "seg-0002", "start": 2.5, "end": 4.0},  # gap 0.5 -> same unit
        {"id": "seg-0003", "start": 9.0, "end": 11.0},  # gap 5.0 -> new unit
    ]
    units = units_from_segments(segments, max_gap_sec=2.0)
    assert [unit.unit_id for unit in units] == ["vis-0001", "vis-0002"]
    assert units[0].start == 0.0 and units[0].end == 4.0
    assert units[0].segment_ids == ["seg-0001", "seg-0002"]
    assert units[1].segment_ids == ["seg-0003"]


def test_units_from_segments_respects_duration_and_count_caps() -> None:
    # Six contiguous 3s segments: a 12s duration cap splits after four.
    segments = [
        {"id": f"seg-{index}", "start": index * 3.0, "end": index * 3.0 + 3.0} for index in range(6)
    ]
    units = units_from_segments(segments, max_gap_sec=1.0, max_unit_duration_sec=12.0)
    assert len(units) == 2
    assert units[0].end - units[0].start <= 12.0

    units_by_count = units_from_segments(segments, max_gap_sec=1.0, max_unit_duration_sec=100.0, max_unit_segments=2)
    assert len(units_by_count) == 3


def test_units_from_segments_skips_malformed_and_sorts() -> None:
    segments = [
        {"id": "b", "start": 5.0, "end": 6.0},
        {"id": "bad", "start": 3.0, "end": 2.0},  # end <= start dropped
        {"no_time": True},
        {"id": "a", "start": 0.0, "end": 1.0},
    ]
    units = units_from_segments(segments, max_gap_sec=1.0)
    assert [unit.segment_ids for unit in units] == [["a"], ["b"]]


def test_units_from_interval_covers_duration() -> None:
    units = units_from_interval(25.0, interval_sec=10.0)
    assert [(unit.start, unit.end) for unit in units] == [(0.0, 10.0), (10.0, 20.0), (20.0, 25.0)]
    assert units[-1].unit_id == "vis-0003"
    assert units_from_interval(0.0) == []
    assert units_from_interval(10.0, interval_sec=0.0) == []


def test_units_from_interval_merges_subsecond_tail() -> None:
    # A 60.001s probe with 12s intervals must not yield a 1ms tail unit —
    # seeking at the very last frame makes ffmpeg extraction fail.
    units = units_from_interval(60.001, interval_sec=12.0)
    assert len(units) == 5
    assert units[-1].end == 60.001
    # A single short video is left as one unit, never merged away.
    assert len(units_from_interval(0.5, interval_sec=10.0)) == 1


def test_units_from_events_uses_event_ids_and_time_aliases() -> None:
    events = [
        {"event_id": "evt-0001", "start": 1.0, "end": 2.0},
        {"start_time": 3.0, "end_time": 4.0},  # detection.json style
        {"start": 9.0, "end": 5.0},  # inverted -> dropped
    ]
    units = units_from_events(events)
    assert [unit.unit_id for unit in units] == ["evt-0001", "evt-0002"]
    assert units[1].start == 3.0 and units[1].end == 4.0


def test_frame_times_short_unit_takes_midpoint() -> None:
    unit = AnalysisUnit(unit_id="vis-0001", start=10.0, end=11.0)
    assert frame_times_for_unit(unit, frames_per_unit=4) == [10.5]


def test_frame_times_uniform_sampling_stays_inside_unit() -> None:
    unit = AnalysisUnit(unit_id="vis-0001", start=0.0, end=8.0)
    times = frame_times_for_unit(unit, frames_per_unit=4)
    assert times == [1.0, 3.0, 5.0, 7.0]
    assert all(unit.start < timestamp < unit.end for timestamp in times)


def test_frame_times_clamps_frames_per_unit() -> None:
    unit = AnalysisUnit(unit_id="vis-0001", start=0.0, end=100.0)
    assert len(frame_times_for_unit(unit, frames_per_unit=99)) == 8
    assert len(frame_times_for_unit(unit, frames_per_unit=0)) == 1


@pytest.mark.parametrize("frames_per_unit", [1, 2, 8])
def test_frame_times_count_matches_request(frames_per_unit: int) -> None:
    unit = AnalysisUnit(unit_id="vis-0001", start=0.0, end=60.0)
    assert len(frame_times_for_unit(unit, frames_per_unit=frames_per_unit)) == frames_per_unit
