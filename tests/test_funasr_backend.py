from __future__ import annotations

from translip.transcription.funasr_backend import (
    _extract_vad_intervals,
    _merge_intervals,
    _normalize_language,
    _resolve_model_id,
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
