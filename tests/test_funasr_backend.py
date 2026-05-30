from __future__ import annotations

from translip.transcription.funasr_backend import (
    _distribute_region_time,
    _extract_vad_intervals,
    _merge_intervals,
    _normalize_language,
    _resolve_model_id,
    _split_region_sentences,
    _strip_sensevoice_tags,
)


def test_strip_sensevoice_tags_removes_compact_and_spaced_forms() -> None:
    compact = "<|zh|><|NEUTRAL|><|Speech|><|woitn|>奶奶你好"
    assert _strip_sensevoice_tags(compact) == "奶奶你好"

    # Tags can survive into a tokenizer as a spaced form; those must go too so
    # emotion/event/language markers never leak into the transcript.
    spaced = "< | zh | > < | HAPPY | > < | S pe ech | >你知道哈利法塔吗"
    assert _strip_sensevoice_tags(spaced) == "你知道哈利法塔吗"

    assert _strip_sensevoice_tags("") == ""
    assert _strip_sensevoice_tags("plain text") == "plain text"


def test_extract_vad_intervals_converts_ms_to_seconds() -> None:
    vad_results = [{"key": "audio", "value": [[0, 5000], [5400, 12000]]}]
    assert _extract_vad_intervals(vad_results) == [(0.0, 5.0), (5.4, 12.0)]


def test_extract_vad_intervals_tolerates_empty_or_malformed() -> None:
    assert _extract_vad_intervals([]) == []
    assert _extract_vad_intervals(None) == []
    assert _extract_vad_intervals([{"value": None}]) == []
    # Malformed pairs are skipped, valid ones retained.
    assert _extract_vad_intervals([{"value": [["x", 1], [1000, 2000]]}]) == [(1.0, 2.0)]


def test_merge_intervals_bridges_small_gaps_and_caps_length() -> None:
    # Gap of 0.3s (< 0.5s) -> merged into one region.
    assert _merge_intervals([(0.0, 5.0), (5.3, 8.0)]) == [(0.0, 8.0)]

    # Gap of 2.0s (> 0.5s) -> kept separate.
    assert _merge_intervals([(0.0, 5.0), (7.0, 9.0)]) == [(0.0, 5.0), (7.0, 9.0)]

    # Merging would exceed the 30s cap -> kept separate even with a tiny gap.
    assert _merge_intervals([(0.0, 29.0), (29.2, 35.0)]) == [(0.0, 29.0), (29.2, 35.0)]

    assert _merge_intervals([]) == []


def test_normalize_language_and_model_resolution() -> None:
    assert _normalize_language("zh") == "zh"
    assert _normalize_language("ZH") == "zh"
    assert _normalize_language(None) == "auto"
    assert _normalize_language("unsupported") == "auto"

    assert _resolve_model_id("") == "iic/SenseVoiceSmall"
    assert _resolve_model_id("small") == "iic/SenseVoiceSmall"
    assert _resolve_model_id("iic/SenseVoiceSmall") == "iic/SenseVoiceSmall"
    assert _resolve_model_id("custom/model") == "custom/model"


def test_split_region_sentences_splits_and_collapses_double_punctuation() -> None:
    # A multi-utterance region with the doubled SenseVoice+CT-Punc marks.
    text = "你知道哈利法塔吗？？哈利法塔是全世界最高的塔。哦，，那他在哪儿啊？"
    assert _split_region_sentences(text) == [
        "你知道哈利法塔吗",
        "哈利法塔是全世界最高的塔",
        "哦 那他在哪儿啊",  # internal pause commas become a space, no trailing mark
    ]


def test_split_region_sentences_keeps_single_short_utterance() -> None:
    assert _split_region_sentences("奶奶") == ["奶奶"]
    assert _split_region_sentences("。？！") == []
    assert _split_region_sentences("") == []


def test_distribute_region_time_allocates_by_length_and_is_monotonic() -> None:
    spans = _distribute_region_time(10.0, 16.0, ["四个字呀", "两字"])
    # 6s split ∝ length (4 vs 2 chars) → 4s + 2s, contiguous, last ends exactly at region end.
    assert spans == [(10.0, 14.0, "四个字呀"), (14.0, 16.0, "两字")]
    starts_ends = [(s, e) for s, e, _ in spans]
    assert all(s <= e for s, e in starts_ends)
    assert starts_ends[0][1] == starts_ends[1][0]  # no gap/overlap between lines

    single = _distribute_region_time(3.0, 5.0, ["一句话"])
    assert single == [(3.0, 5.0, "一句话")]
