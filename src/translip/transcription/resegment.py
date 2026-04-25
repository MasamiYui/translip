"""Heuristic resegmentation for overly-long ASR segments.

Motivation
----------
``translip.dubbing.planning.is_usable_task_d_segment`` originally enforced a
hard 1.0s ≤ duration ≤ 6.0s window. Segments outside the window were silently
dropped from the TTS cloning pipeline, which in ``task-20260425-023015``
caused the whole speaker ``spk_0002`` (6 segments, 8.9s–34.9s each) to vanish
from the final dub.

Root cause was not the filter itself but *upstream* ASR over-merging: the
original audio for those long segments contains a single short utterance
surrounded by long silences. In principle we would want a real VAD (silero /
pyannote) to re-split them before sending to task-d. To stay within the "no
new model downloads" constraint of Sprint 2, we implement a lightweight
offline resegmenter that works purely on:

* text-level punctuation cues (Chinese / English), and
* a uniform time-budget fallback when no cue is present.

It produces sub-segments whose duration is inside ``[min_duration,
max_duration]`` (default: the task-d usable window) whenever possible.

The algorithm is:

1. Split the text at strong punctuation (。！？.!?) and preserve weaker
   punctuation (，,、;；) as secondary cues.
2. Allocate time-windows *proportionally to character count* across those
   sub-sentences.
3. Greedily merge adjacent tiny sub-sentences until every window is at least
   ``min_duration`` long, and greedily split any window longer than
   ``max_duration`` into uniform slices.
4. Return a list of dictionaries containing a new sub-``segment_id``, the
   derived ``start`` / ``end`` / ``duration`` / ``text``, and a "resegmented"
   flag for observability.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Sequence

from ..config import (
    DEFAULT_TASK_D_USABLE_MAX_DURATION_SEC,
    DEFAULT_TASK_D_USABLE_MIN_DURATION_SEC,
)

_STRONG_SPLIT_RE = re.compile(r"(?<=[。！？!?\.])\s*")
_WEAK_SPLIT_RE = re.compile(r"(?<=[，,、；;:])\s*")

__all__ = [
    "Subsegment",
    "split_sentence_text",
    "resegment_by_heuristics",
    "MIN_DURATION_FLOOR",
    "MAX_DURATION_CEILING",
]

#: Safety caps. Regardless of caller configuration we refuse to accept
#: nonsensical bounds (non-positive or inverted).
MIN_DURATION_FLOOR = 0.2
MAX_DURATION_CEILING = 60.0


@dataclass(slots=True)
class Subsegment:
    """A single resegmented slice ready to be fed to task-d planning."""

    segment_id: str
    start: float
    end: float
    text: str
    notes: list[str] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def as_dict(self) -> dict[str, object]:
        return {
            "segment_id": self.segment_id,
            "start": round(self.start, 4),
            "end": round(self.end, 4),
            "duration": round(self.duration, 4),
            "text": self.text,
            "notes": list(self.notes),
        }


def split_sentence_text(text: str) -> list[str]:
    """Split ``text`` into sentence-ish chunks using punctuation heuristics.

    The order of preference is:
    1. Strong punctuation (``。！？.!?``) – hard sentence boundary.
    2. Weak punctuation (``，,、；;:``) – soft break, only used if a strong
       split did not yield enough chunks.
    3. Whitespace fallback (for Latin text without CJK punctuation).

    The returned chunks always preserve the characters of ``text`` except for
    leading/trailing whitespace.
    """

    stripped = text.strip()
    if not stripped:
        return []

    strong_chunks = [chunk.strip() for chunk in _STRONG_SPLIT_RE.split(stripped) if chunk.strip()]
    if len(strong_chunks) > 1:
        return strong_chunks

    weak_chunks = [chunk.strip() for chunk in _WEAK_SPLIT_RE.split(stripped) if chunk.strip()]
    if len(weak_chunks) > 1:
        return weak_chunks

    # Final fallback: split on whitespace clusters for Latin/multilingual text.
    whitespace_chunks = [chunk for chunk in re.split(r"\s{2,}|\n+", stripped) if chunk.strip()]
    if len(whitespace_chunks) > 1:
        return [chunk.strip() for chunk in whitespace_chunks]

    return [stripped]


def resegment_by_heuristics(
    *,
    segment_id: str,
    start: float,
    end: float,
    text: str,
    min_duration: float = DEFAULT_TASK_D_USABLE_MIN_DURATION_SEC,
    max_duration: float = DEFAULT_TASK_D_USABLE_MAX_DURATION_SEC,
) -> list[Subsegment]:
    """Split a possibly-too-long segment into TTS-usable sub-segments.

    Parameters
    ----------
    segment_id:
        Stable identifier of the source segment. Children get suffixes
        ``"_a", "_b", ...``.
    start, end:
        Source timestamps in seconds. ``end`` must be greater than ``start``.
    text:
        Transcribed text for the full segment.
    min_duration, max_duration:
        Target duration bounds for children. The function will:
            * merge greedily if any child would be shorter than ``min_duration``
            * split uniformly if any child would be longer than ``max_duration``

    Returns
    -------
    A list of :class:`Subsegment` entries. Always non-empty as long as
    ``end > start``; returns a single-element list that mirrors the input
    when no further splitting is possible or makes sense (e.g. an already
    short segment, or an empty text).
    """

    if end <= start:
        return []
    if min_duration <= 0 or max_duration <= 0 or min_duration > max_duration:
        raise ValueError(
            f"invalid duration bounds: min={min_duration}, max={max_duration}"
        )

    min_duration = max(MIN_DURATION_FLOOR, min_duration)
    max_duration = min(MAX_DURATION_CEILING, max_duration)
    total_duration = end - start

    # Short-circuit 1: segment is already within the window – no work.
    if total_duration <= max_duration:
        return [
            Subsegment(
                segment_id=segment_id,
                start=start,
                end=end,
                text=text.strip(),
                notes=["within_bounds"],
            )
        ]

    chunks = split_sentence_text(text)
    if not chunks:
        # No textual cue to work with – fall back to uniform slicing.
        return _uniform_slice(
            segment_id=segment_id,
            start=start,
            end=end,
            text=text,
            min_duration=min_duration,
            max_duration=max_duration,
        )

    # Allocate a duration share to each chunk proportional to character count.
    weights = [max(1, len(chunk)) for chunk in chunks]
    total_weight = sum(weights)
    raw_durations = [total_duration * weight / total_weight for weight in weights]

    # Merge tiny trailing chunks into their neighbours so that nobody is below
    # min_duration. We sweep from left to right then right to left for balance.
    merged_texts, merged_durations = _merge_small_chunks(
        chunks=list(chunks),
        durations=raw_durations,
        min_duration=min_duration,
    )

    # If after merging a single chunk still exceeds max_duration, uniformly
    # sub-slice that chunk.
    expanded_texts: list[str] = []
    expanded_durations: list[float] = []
    for chunk_text, chunk_duration in zip(merged_texts, merged_durations, strict=True):
        if chunk_duration <= max_duration:
            expanded_texts.append(chunk_text)
            expanded_durations.append(chunk_duration)
            continue
        slices = max(2, math.ceil(chunk_duration / max_duration))
        slice_duration = chunk_duration / slices
        # We keep the original text attached to the first slice so downstream
        # consumers still have it; trailing slices get placeholder text to keep
        # alignment honest.
        for slice_index in range(slices):
            expanded_texts.append(chunk_text if slice_index == 0 else "")
            expanded_durations.append(slice_duration)

    return _build_subsegments(
        segment_id=segment_id,
        start=start,
        end=end,
        texts=expanded_texts,
        durations=expanded_durations,
        min_duration=min_duration,
        max_duration=max_duration,
        source_note="resegmented_by_heuristics",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _uniform_slice(
    *,
    segment_id: str,
    start: float,
    end: float,
    text: str,
    min_duration: float,
    max_duration: float,
) -> list[Subsegment]:
    total_duration = end - start
    slices = max(2, math.ceil(total_duration / max_duration))
    slice_duration = total_duration / slices
    if slice_duration < min_duration:
        # cap slices so each still >= min_duration
        slices = max(1, math.floor(total_duration / min_duration))
        slice_duration = total_duration / max(1, slices)

    texts: list[str] = [text.strip() if i == 0 else "" for i in range(slices)]
    durations: list[float] = [slice_duration] * slices
    return _build_subsegments(
        segment_id=segment_id,
        start=start,
        end=end,
        texts=texts,
        durations=durations,
        min_duration=min_duration,
        max_duration=max_duration,
        source_note="uniform_fallback",
    )


def _merge_small_chunks(
    *,
    chunks: list[str],
    durations: list[float],
    min_duration: float,
) -> tuple[list[str], list[float]]:
    texts = list(chunks)
    dur = list(durations)

    # Sweep left-to-right: merge any too-short chunk into its right neighbour.
    i = 0
    while i < len(dur) - 1:
        if dur[i] < min_duration:
            dur[i + 1] = dur[i + 1] + dur[i]
            texts[i + 1] = (texts[i] + " " + texts[i + 1]).strip()
            dur.pop(i)
            texts.pop(i)
            continue
        i += 1

    # Sweep right-to-left: fold the tail into its left neighbour if still short.
    if dur and dur[-1] < min_duration and len(dur) > 1:
        dur[-2] = dur[-2] + dur[-1]
        texts[-2] = (texts[-2] + " " + texts[-1]).strip()
        dur.pop()
        texts.pop()

    return texts, dur


def _build_subsegments(
    *,
    segment_id: str,
    start: float,
    end: float,
    texts: Sequence[str],
    durations: Sequence[float],
    min_duration: float,
    max_duration: float,
    source_note: str,
) -> list[Subsegment]:
    if not texts or not durations:
        return []
    assert len(texts) == len(durations)
    result: list[Subsegment] = []
    cursor = start
    total_duration = end - start
    scale = total_duration / sum(durations) if sum(durations) else 1.0

    suffixes = _suffix_generator(len(texts))

    for index, (chunk_text, chunk_duration) in enumerate(
        zip(texts, durations, strict=True)
    ):
        scaled = chunk_duration * scale
        next_cursor = end if index == len(texts) - 1 else cursor + scaled
        notes = [source_note]
        if scaled < min_duration:
            notes.append("below_min_duration")
        if scaled > max_duration:
            notes.append("above_max_duration")
        result.append(
            Subsegment(
                segment_id=f"{segment_id}_{suffixes[index]}",
                start=cursor,
                end=next_cursor,
                text=chunk_text.strip(),
                notes=notes,
            )
        )
        cursor = next_cursor
    return result


def _suffix_generator(count: int) -> list[str]:
    """Return deterministic alphabetical suffixes (a, b, ..., z, aa, ab, ...)."""

    suffixes: list[str] = []
    for index in range(count):
        suffixes.append(_int_to_alpha(index))
    return suffixes


def _int_to_alpha(index: int) -> str:
    result = ""
    current = index
    while True:
        result = chr(ord("a") + current % 26) + result
        current = current // 26 - 1
        if current < 0:
            break
    return result
