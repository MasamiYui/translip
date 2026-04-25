"""Unit tests for dubbing runner quality-retry heuristics (Sprint 2)."""

from __future__ import annotations

from types import SimpleNamespace

from translip.config import (
    DEFAULT_TTS_GENERATED_DURATION_HARD_RATIO,
    DEFAULT_TTS_GENERATED_DURATION_LOWER_RATIO,
)
from translip.dubbing.runner import _quality_retry_reasons


def _eval(
    *,
    duration_status: str = "passed",
    duration_ratio: float = 1.0,
    intelligibility_status: str = "passed",
    text_similarity: float = 0.9,
    speaker_status: str = "passed",
    speaker_similarity: float | None = 0.9,
) -> SimpleNamespace:
    return SimpleNamespace(
        duration_status=duration_status,
        duration_ratio=duration_ratio,
        intelligibility_status=intelligibility_status,
        text_similarity=text_similarity,
        speaker_status=speaker_status,
        speaker_similarity=speaker_similarity,
    )


def test_passes_when_all_metrics_are_good() -> None:
    assert _quality_retry_reasons(_eval()) == []


def test_triggers_on_upper_hard_ratio_even_when_status_passed() -> None:
    """Regression: task-20260425-023015 had ratio ~1.6 with status='review'."""

    ratio = DEFAULT_TTS_GENERATED_DURATION_HARD_RATIO + 0.01
    reasons = _quality_retry_reasons(
        _eval(duration_status="passed", duration_ratio=ratio)
    )
    assert "pathological_duration" in reasons


def test_triggers_on_lower_hard_ratio() -> None:
    ratio = DEFAULT_TTS_GENERATED_DURATION_LOWER_RATIO - 0.01
    reasons = _quality_retry_reasons(
        _eval(duration_status="passed", duration_ratio=ratio)
    )
    assert "pathological_duration" in reasons


def test_does_not_trigger_near_unity_ratio() -> None:
    reasons = _quality_retry_reasons(_eval(duration_ratio=1.1))
    assert "pathological_duration" not in reasons


def test_preserves_legacy_failed_status_behavior() -> None:
    """Even if the new ratio is within bounds, a 'failed' status with the old
    extreme thresholds should still trigger the retry."""

    ratio = 0.4  # below new lower bound 0.5 as well, so should still fire
    reasons = _quality_retry_reasons(
        _eval(duration_status="failed", duration_ratio=ratio)
    )
    assert "pathological_duration" in reasons


def test_poor_backread_triggered_by_intelligibility_failure() -> None:
    reasons = _quality_retry_reasons(
        _eval(intelligibility_status="failed", text_similarity=0.3)
    )
    assert "poor_backread" in reasons


def test_poor_speaker_match_triggered_on_low_similarity() -> None:
    reasons = _quality_retry_reasons(
        _eval(speaker_status="failed", speaker_similarity=0.2)
    )
    assert "poor_speaker_match" in reasons


def test_missing_speaker_similarity_counts_as_poor_when_status_failed() -> None:
    reasons = _quality_retry_reasons(
        _eval(speaker_status="failed", speaker_similarity=None)
    )
    assert "poor_speaker_match" in reasons


def test_multiple_reasons_may_coexist() -> None:
    reasons = _quality_retry_reasons(
        _eval(
            duration_ratio=2.0,
            intelligibility_status="failed",
            text_similarity=0.4,
            speaker_status="failed",
            speaker_similarity=0.2,
        )
    )
    assert set(reasons) == {"pathological_duration", "poor_backread", "poor_speaker_match"}


def test_ratio_exactly_at_hard_upper_triggers() -> None:
    reasons = _quality_retry_reasons(
        _eval(duration_ratio=DEFAULT_TTS_GENERATED_DURATION_HARD_RATIO)
    )
    assert "pathological_duration" in reasons
