"""Unit tests for rendering.export quality gate golden metrics (Sprint 2)."""

from __future__ import annotations

from translip.config import (
    DEFAULT_QUALITY_GATE_AVG_SPEAKER_SIMILARITY_MIN,
    DEFAULT_QUALITY_GATE_COVERAGE_MIN,
    DEFAULT_QUALITY_GATE_FAILED_MAX,
    DEFAULT_QUALITY_GATE_INTELLIGIBILITY_FAILED_MAX,
    DEFAULT_QUALITY_GATE_SKIPPED_RATIO_BLOCK,
    DEFAULT_QUALITY_GATE_SPEAKER_FAILED_MAX,
    DEFAULT_QUALITY_GATE_SPEAKER_SIMILARITY_LOWBAND_MAX,
    DEFAULT_QUALITY_GATE_SPEAKER_SIMILARITY_REVIEW_FLOOR,
)
from translip.rendering.export import _build_content_quality


def _quality_summary(
    *,
    total_count: int,
    overall_failed: int = 0,
    speaker_failed: int = 0,
    intelligibility_failed: int = 0,
) -> dict[str, object]:
    return {
        "total_count": total_count,
        "overall_status_counts": {"failed": overall_failed, "passed": total_count - overall_failed},
        "speaker_status_counts": {"failed": speaker_failed, "passed": total_count - speaker_failed},
        "intelligibility_status_counts": {"failed": intelligibility_failed},
    }


def _empty_audible() -> dict[str, object]:
    return {"failed_count": 0}


def test_deliverable_when_all_metrics_pass() -> None:
    placed = [
        {"speaker_similarity": 0.80, "qa_flags": []},
        {"speaker_similarity": 0.75, "qa_flags": []},
    ]
    report = _build_content_quality(
        placed_count=2,
        skipped_count=0,
        quality_summary=_quality_summary(total_count=2),
        audible_coverage=_empty_audible(),
        placed_items=placed,
        skipped_items=[],
    )
    assert report["status"] == "deliverable"
    assert report["reasons"] == []
    assert report["speaker_similarity_lowband_ratio"] == 0.0
    assert report["avg_speaker_similarity"] > 0.7


def test_reports_thresholds_block() -> None:
    report = _build_content_quality(
        placed_count=0,
        skipped_count=0,
        quality_summary=_quality_summary(total_count=0),
        audible_coverage=_empty_audible(),
        placed_items=[],
        skipped_items=[],
    )
    assert set(report["thresholds"].keys()) == {
        "coverage_min",
        "failed_max",
        "speaker_failed_max",
        "intelligibility_failed_max",
        "speaker_similarity_review_floor",
        "speaker_similarity_lowband_max",
        "avg_speaker_similarity_min",
        "skipped_ratio_block",
    }
    assert report["thresholds"]["coverage_min"] == DEFAULT_QUALITY_GATE_COVERAGE_MIN
    assert (
        report["thresholds"]["speaker_similarity_review_floor"]
        == DEFAULT_QUALITY_GATE_SPEAKER_SIMILARITY_REVIEW_FLOOR
    )


def test_speaker_similarity_lowband_triggers_review() -> None:
    """Regression: task-20260425-023015 had 161/164 < 0.5 similarity."""

    placed = [
        # 5 out of 10 below floor => 0.5 ratio, exceeds 0.30 cap
        *[{"speaker_similarity": 0.20, "qa_flags": []} for _ in range(5)],
        *[{"speaker_similarity": 0.80, "qa_flags": []} for _ in range(5)],
    ]
    report = _build_content_quality(
        placed_count=10,
        skipped_count=0,
        quality_summary=_quality_summary(total_count=10),
        audible_coverage=_empty_audible(),
        placed_items=placed,
        skipped_items=[],
    )
    assert report["speaker_similarity_lowband_ratio"] == 0.5
    assert "speaker_similarity_lowband_exceeded" in report["reasons"]
    assert report["status"] == "review_required"


def test_avg_speaker_similarity_below_floor_surfaces_reason() -> None:
    placed = [{"speaker_similarity": 0.30, "qa_flags": []} for _ in range(4)]
    report = _build_content_quality(
        placed_count=4,
        skipped_count=0,
        quality_summary=_quality_summary(total_count=4),
        audible_coverage=_empty_audible(),
        placed_items=placed,
        skipped_items=[],
    )
    # avg is 0.30 < 0.45 floor
    assert report["avg_speaker_similarity"] == 0.30
    assert "avg_speaker_similarity_below_floor" in report["reasons"]
    # Also lowband ratio = 1.0 > 0.30 so another reason
    assert "speaker_similarity_lowband_exceeded" in report["reasons"]


def test_overflow_unfitted_counted_from_qa_flags() -> None:
    placed = [
        {"speaker_similarity": 0.8, "qa_flags": ["overflow_unfitted"]},
        {"speaker_similarity": 0.8, "qa_flags": []},
        {"speaker_similarity": 0.8, "notes": ["overflow_unfitted", "some_other"]},
    ]
    report = _build_content_quality(
        placed_count=3,
        skipped_count=0,
        quality_summary=_quality_summary(total_count=3),
        audible_coverage=_empty_audible(),
        placed_items=placed,
        skipped_items=[],
    )
    assert report["overflow_unfitted_count"] == 2


def test_skipped_ratio_block_still_triggers_blocked_status() -> None:
    """21 skipped out of 100 total (> 20% threshold) should be 'blocked'."""

    placed = [{"speaker_similarity": 0.8, "qa_flags": []} for _ in range(79)]
    report = _build_content_quality(
        placed_count=79,
        skipped_count=21,
        quality_summary=_quality_summary(total_count=100),
        audible_coverage=_empty_audible(),
        placed_items=placed,
        skipped_items=[{"segment_id": f"s_{i}"} for i in range(21)],
    )
    assert report["status"] == "blocked"
    assert report["skipped_ratio"] > DEFAULT_QUALITY_GATE_SKIPPED_RATIO_BLOCK


def test_avg_speaker_similarity_none_when_no_placed() -> None:
    report = _build_content_quality(
        placed_count=0,
        skipped_count=5,
        quality_summary=_quality_summary(total_count=5),
        audible_coverage=_empty_audible(),
        placed_items=[],
        skipped_items=[{"segment_id": f"s_{i}"} for i in range(5)],
    )
    assert report["avg_speaker_similarity"] is None
    assert report["status"] == "blocked"  # 100% skipped


def test_backward_compatibility_without_placed_items_keyword() -> None:
    """The old signature (no placed_items arg) must still produce a sane result.

    Some older callers (and now-unlikely importers) may not pass the new
    optional args; the function should not crash and should return defaults.
    """

    report = _build_content_quality(
        placed_count=2,
        skipped_count=0,
        quality_summary=_quality_summary(total_count=2),
        audible_coverage=_empty_audible(),
    )
    assert report["status"] == "deliverable"
    assert report["speaker_similarity_lowband_ratio"] == 0.0
    assert report["avg_speaker_similarity"] is None
    assert report["overflow_unfitted_count"] == 0


def test_threshold_constants_are_internally_consistent() -> None:
    # Sanity: failed_max <= speaker_failed_max and both below 1.0
    assert 0 < DEFAULT_QUALITY_GATE_FAILED_MAX <= DEFAULT_QUALITY_GATE_SPEAKER_FAILED_MAX <= 1.0
    assert 0 < DEFAULT_QUALITY_GATE_INTELLIGIBILITY_FAILED_MAX <= 1.0
    # Review floor and avg floor must be sensible
    assert 0 < DEFAULT_QUALITY_GATE_AVG_SPEAKER_SIMILARITY_MIN < 1.0
    assert 0 < DEFAULT_QUALITY_GATE_SPEAKER_SIMILARITY_REVIEW_FLOOR < 1.0
    # Low-band ratio cap must be strictly below 1
    assert 0 < DEFAULT_QUALITY_GATE_SPEAKER_SIMILARITY_LOWBAND_MAX < 1.0
    # Coverage minimum must be reasonably high (we expect near-full coverage)
    assert DEFAULT_QUALITY_GATE_COVERAGE_MIN >= 0.9
