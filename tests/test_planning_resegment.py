"""Unit tests for dubbing.planning filter + resegment helpers (Sprint 2)."""

from __future__ import annotations

import pytest

from translip.config import (
    DEFAULT_TASK_D_PREFERRED_MAX_DURATION_SEC,
    DEFAULT_TASK_D_PREFERRED_MIN_DURATION_SEC,
    DEFAULT_TASK_D_USABLE_MAX_DURATION_SEC,
    DEFAULT_TASK_D_USABLE_MIN_DURATION_SEC,
)
from translip.dubbing.planning import (
    is_preferred_task_d_segment,
    is_usable_task_d_segment,
    try_resegment_for_task_d,
)


# --- is_usable_task_d_segment -----------------------------------------------


def test_usable_boundary_conditions() -> None:
    flags: set[str] = set()
    assert is_usable_task_d_segment(
        duration_sec=DEFAULT_TASK_D_USABLE_MIN_DURATION_SEC,
        qa_flags=flags,
    )
    assert is_usable_task_d_segment(
        duration_sec=DEFAULT_TASK_D_USABLE_MAX_DURATION_SEC,
        qa_flags=flags,
    )
    assert not is_usable_task_d_segment(
        duration_sec=DEFAULT_TASK_D_USABLE_MIN_DURATION_SEC - 0.01,
        qa_flags=flags,
    )
    assert not is_usable_task_d_segment(
        duration_sec=DEFAULT_TASK_D_USABLE_MAX_DURATION_SEC + 0.01,
        qa_flags=flags,
    )


def test_usable_rejects_too_short_source_flag() -> None:
    assert not is_usable_task_d_segment(
        duration_sec=2.0, qa_flags={"too_short_source"}
    )


# --- is_preferred_task_d_segment --------------------------------------------


def test_preferred_window_uses_config_defaults() -> None:
    flags: set[str] = set()
    assert is_preferred_task_d_segment(
        duration_sec=DEFAULT_TASK_D_PREFERRED_MIN_DURATION_SEC,
        qa_flags=flags,
    )
    assert is_preferred_task_d_segment(
        duration_sec=DEFAULT_TASK_D_PREFERRED_MAX_DURATION_SEC,
        qa_flags=flags,
    )
    assert not is_preferred_task_d_segment(
        duration_sec=DEFAULT_TASK_D_PREFERRED_MIN_DURATION_SEC - 0.1,
        qa_flags=flags,
    )


def test_preferred_rejects_duration_risky_flag() -> None:
    assert not is_preferred_task_d_segment(
        duration_sec=2.0, qa_flags={"duration_risky"}
    )


# --- try_resegment_for_task_d ------------------------------------------------


def test_try_resegment_produces_only_usable_children_for_spk_0002_case() -> None:
    """Regression guard for task-20260425-023015 spk_0002 segments."""

    # Synthetic but representative: a 34.9s monologue with three sentences.
    children = try_resegment_for_task_d(
        segment_id="spk_0002_seg_005",
        start=200.0,
        end=234.9,
        text=(
            "我们终于到了迪拜这座神奇的城市。"
            "哈利法塔高达八百二十八米，是世界第一高楼。"
            "今晚我们就要去棕榈岛和帆船酒店看音乐喷泉表演。"
        ),
    )
    assert children, "at least one usable child must be produced"
    for child in children:
        assert (
            DEFAULT_TASK_D_USABLE_MIN_DURATION_SEC
            <= child.duration
            <= DEFAULT_TASK_D_USABLE_MAX_DURATION_SEC
        ), f"child {child} escaped usable bounds"
        assert child.segment_id.startswith("spk_0002_seg_005_")


def test_try_resegment_returns_original_for_short_segment() -> None:
    children = try_resegment_for_task_d(
        segment_id="short_seg",
        start=0.0,
        end=2.0,
        text="你好",
    )
    assert len(children) == 1
    assert children[0].segment_id == "short_seg"
    assert children[0].duration == pytest.approx(2.0)


def test_try_resegment_skips_too_short_source_flag() -> None:
    children = try_resegment_for_task_d(
        segment_id="tiny",
        start=0.0,
        end=20.0,
        text="这段本来就被标为 too_short_source",
        qa_flags={"too_short_source"},
    )
    assert children == []


def test_try_resegment_handles_zero_duration_gracefully() -> None:
    assert (
        try_resegment_for_task_d(
            segment_id="x",
            start=5.0,
            end=5.0,
            text="whatever",
        )
        == []
    )


def test_try_resegment_empty_text_uses_uniform_fallback_but_keeps_bounds() -> None:
    children = try_resegment_for_task_d(
        segment_id="spk_0002_seg_002",
        start=0.0,
        end=18.0,
        text="",
    )
    assert children  # uniform slicing should still yield usable children
    for child in children:
        assert (
            DEFAULT_TASK_D_USABLE_MIN_DURATION_SEC
            <= child.duration
            <= DEFAULT_TASK_D_USABLE_MAX_DURATION_SEC
        )


def test_try_resegment_rejects_invalid_bounds_silently() -> None:
    """Caller-supplied invalid bounds should not crash the pipeline."""

    children = try_resegment_for_task_d(
        segment_id="invalid",
        start=0.0,
        end=10.0,
        text="test",
        min_duration=5.0,
        max_duration=1.0,
    )
    assert children == []
