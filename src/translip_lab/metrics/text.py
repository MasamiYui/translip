"""Text error rates: CER (char-level) and WER (token-level).

Self-contained Levenshtein so the core has no extra deps and is unit-testable.
The ASR scenario additionally prefers translip's own
``score_transcription_against_reference`` for parity with the in-tree benchmark;
these functions are the dependency-free fallback and the building blocks.
"""
from __future__ import annotations

from typing import Sequence


def edit_distance(a: Sequence, b: Sequence) -> int:
    """Levenshtein edit distance between two sequences (chars or tokens)."""
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if la == 0:
        return lb
    if lb == 0:
        return la
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        ai = a[i - 1]
        for j in range(1, lb + 1):
            cost = 0 if ai == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[lb]


def _norm_chars(text: str, *, ignore_space: bool = True, lower: bool = True) -> list[str]:
    if lower:
        text = text.lower()
    if ignore_space:
        text = "".join(text.split())
    return list(text)


def cer(reference: str, hypothesis: str, *, ignore_space: bool = True) -> float:
    """Character Error Rate = edit_distance / len(reference_chars).

    Whitespace is ignored by default (it carries no meaning in Chinese). A perfect
    match is 0.0; an empty reference returns 0.0 if the hypothesis is also empty,
    else 1.0 (everything inserted).
    """
    ref = _norm_chars(reference, ignore_space=ignore_space)
    hyp = _norm_chars(hypothesis, ignore_space=ignore_space)
    if not ref:
        return 0.0 if not hyp else 1.0
    return edit_distance(ref, hyp) / len(ref)


def wer(reference: str, hypothesis: str) -> float:
    """Word Error Rate = token edit_distance / len(reference_tokens). Whitespace-tokenized."""
    ref = reference.lower().split()
    hyp = hypothesis.lower().split()
    if not ref:
        return 0.0 if not hyp else 1.0
    return edit_distance(ref, hyp) / len(ref)
