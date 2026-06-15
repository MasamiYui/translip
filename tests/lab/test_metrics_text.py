"""CER / WER / edit-distance unit tests (hand-computed expectations)."""
from __future__ import annotations

from translip_lab.metrics.text import cer, edit_distance, wer


def test_edit_distance_basic():
    assert edit_distance("kitten", "sitting") == 3
    assert edit_distance("", "abc") == 3
    assert edit_distance("abc", "") == 3
    assert edit_distance("same", "same") == 0


def test_cer_perfect_and_substitution():
    assert cer("你好世界", "你好世界") == 0.0
    # one of four chars wrong → 0.25
    assert cer("你好世界", "你好世节") == 0.25


def test_cer_ignores_whitespace():
    assert cer("a b c", "abc") == 0.0


def test_cer_empty_reference():
    assert cer("", "") == 0.0
    assert cer("", "x") == 1.0


def test_wer_token_level():
    assert wer("the cat sat", "the cat sat") == 0.0
    assert wer("the cat", "the dog") == 0.5
