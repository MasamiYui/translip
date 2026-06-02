from translip.quality.source_coverage import reconcile_speech


def test_reconcile_speech_flags_uncovered_window() -> None:
    # Speech 0-2 and 5-8; the transcript only covers 0-2 and 5-6, so ~6.2-8 has
    # speech with no line over it — a line likely dropped before task-c.
    result = reconcile_speech(
        speech_windows=[(0.0, 2.0), (5.0, 8.0)],
        asr_spans=[(0.0, 2.0), (5.0, 6.0)],
    )
    assert result["detected_speech_sec"] == 5.0
    assert result["uncovered_window_count"] == 1
    assert result["status"] == "review"
    assert result["uncovered_windows"][0]["duration"] >= 1.0
    assert result["transcript_coverage"] < 0.90


def test_reconcile_speech_full_coverage_is_ok() -> None:
    # Every speech window overlaps a transcript span (within tolerance) → nothing to flag.
    result = reconcile_speech(
        speech_windows=[(0.0, 2.0), (3.0, 4.0)],
        asr_spans=[(0.0, 2.5), (2.8, 4.5)],
    )
    assert result["status"] == "ok"
    assert result["transcript_coverage"] == 1.0
    assert result["uncovered_window_count"] == 0


def test_reconcile_speech_ignores_sub_threshold_gaps() -> None:
    # A 0.3s gap between transcript spans is below the 1.0s window floor → not flagged.
    result = reconcile_speech(
        speech_windows=[(0.0, 5.0)],
        asr_spans=[(0.0, 2.0), (2.3, 5.0)],
    )
    assert result["uncovered_window_count"] == 0
    assert result["status"] == "ok"
