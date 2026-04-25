"""Unit tests for the heuristic resegmenter (Sprint 2).

The goal: ensure that very long ASR segments (like spk_0002 in
task-20260425-023015) can be split into 1.0–6.0s children before
``planning.is_usable_task_d_segment`` rejects them.
"""

from __future__ import annotations

import pytest

from translip.transcription.resegment import (
    MIN_DURATION_FLOOR,
    Subsegment,
    resegment_by_heuristics,
    split_sentence_text,
)


class TestSplitSentenceText:
    def test_returns_empty_for_whitespace(self) -> None:
        assert split_sentence_text("   ") == []

    def test_splits_on_chinese_strong_punctuation(self) -> None:
        text = "你好。今天天气很好。我们出去玩吧！"
        chunks = split_sentence_text(text)
        assert chunks == ["你好。", "今天天气很好。", "我们出去玩吧！"]

    def test_splits_on_english_strong_punctuation(self) -> None:
        text = "Hello world. This is a test! Is it?"
        chunks = split_sentence_text(text)
        assert chunks == ["Hello world.", "This is a test!", "Is it?"]

    def test_falls_back_to_weak_punctuation(self) -> None:
        text = "哈利法塔，是世界第一高楼，我们去参观了它"
        chunks = split_sentence_text(text)
        assert len(chunks) == 3
        assert chunks[0].endswith("，")
        assert chunks[-1] == "我们去参观了它"

    def test_returns_single_chunk_if_no_cue(self) -> None:
        text = "这是一个没有任何标点的句子"
        assert split_sentence_text(text) == [text]


class TestResegmentByHeuristics:
    def test_short_segment_is_returned_unchanged(self) -> None:
        subs = resegment_by_heuristics(
            segment_id="seg-0001",
            start=10.0,
            end=13.5,
            text="你好世界",
            min_duration=1.0,
            max_duration=6.0,
        )
        assert len(subs) == 1
        only = subs[0]
        assert only.segment_id == "seg-0001"
        assert only.start == 10.0
        assert only.end == 13.5
        assert only.duration == pytest.approx(3.5)
        assert "within_bounds" in only.notes

    def test_rejects_empty_duration(self) -> None:
        assert resegment_by_heuristics(
            segment_id="seg",
            start=1.0,
            end=1.0,
            text="x",
        ) == []

    def test_raises_on_invalid_bounds(self) -> None:
        with pytest.raises(ValueError):
            resegment_by_heuristics(
                segment_id="seg",
                start=0.0,
                end=10.0,
                text="x",
                min_duration=0.0,
                max_duration=6.0,
            )
        with pytest.raises(ValueError):
            resegment_by_heuristics(
                segment_id="seg",
                start=0.0,
                end=10.0,
                text="x",
                min_duration=5.0,
                max_duration=1.0,
            )

    def test_splits_long_segment_on_chinese_punctuation(self) -> None:
        # 30 seconds with 3 natural sentences. Expect each roughly 10s long
        # which exceeds the 6s cap, so some uniform sub-slicing should happen.
        subs = resegment_by_heuristics(
            segment_id="seg-0002",
            start=100.0,
            end=130.0,
            text="迪拜是阿联酋最大的城市。哈利法塔高达828米。我们今天就要去参观棕榈岛和帆船酒店。",
            min_duration=1.0,
            max_duration=6.0,
        )
        assert len(subs) >= 5  # 3 sentences × at least 2 slices each
        # Cumulative duration must equal the source duration (within float eps).
        total_duration = sum(sub.duration for sub in subs)
        assert total_duration == pytest.approx(30.0, abs=1e-3)
        # No slice may exceed max_duration by more than a tiny tolerance.
        for sub in subs:
            assert sub.duration <= 6.0 + 1e-6, f"{sub} exceeds max_duration"
        # The first sub-segment preserves the opening sentence verbatim.
        assert subs[0].text.startswith("迪拜是阿联酋最大的城市")

    def test_long_segment_without_punctuation_uses_uniform_slicing(self) -> None:
        subs = resegment_by_heuristics(
            segment_id="seg-0003",
            start=0.0,
            end=24.0,
            text="",  # simulate missing ASR text
            min_duration=1.0,
            max_duration=6.0,
        )
        # 24s / 6s = 4 uniform slices
        assert len(subs) == 4
        assert all(sub.duration == pytest.approx(6.0) for sub in subs)
        assert all("uniform_fallback" in sub.notes for sub in subs)

    def test_unique_segment_ids(self) -> None:
        subs = resegment_by_heuristics(
            segment_id="spk_0002_seg_005",
            start=200.0,
            end=234.9,
            text="很多，很多，很多，很多个短句",  # forces weak-split path
            min_duration=1.0,
            max_duration=6.0,
        )
        ids = [sub.segment_id for sub in subs]
        assert len(ids) == len(set(ids))
        assert all(sub_id.startswith("spk_0002_seg_005_") for sub_id in ids)

    def test_min_duration_floor_is_respected(self) -> None:
        """Even if user passes a ridiculous min_duration, we sanitize upward."""

        subs = resegment_by_heuristics(
            segment_id="seg",
            start=0.0,
            end=20.0,
            text="短。短。短。短。短。短。短。短。",
            min_duration=MIN_DURATION_FLOOR,
            max_duration=6.0,
        )
        assert len(subs) >= 2
        assert sum(sub.duration for sub in subs) == pytest.approx(20.0)

    def test_notes_contain_source_information(self) -> None:
        subs = resegment_by_heuristics(
            segment_id="seg",
            start=0.0,
            end=15.0,
            text="迪拜很美。哈利法塔很高。",
        )
        assert len(subs) >= 2
        assert all(
            "resegmented_by_heuristics" in sub.notes for sub in subs
        )

    def test_as_dict_is_serializable(self) -> None:
        sub = Subsegment(segment_id="seg_a", start=0.0, end=1.2, text="x")
        payload = sub.as_dict()
        assert payload["segment_id"] == "seg_a"
        assert payload["start"] == 0.0
        assert payload["end"] == 1.2
        assert payload["duration"] == pytest.approx(1.2)
        assert payload["text"] == "x"
        assert payload["notes"] == []
