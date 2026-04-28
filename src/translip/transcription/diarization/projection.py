from __future__ import annotations

from dataclasses import dataclass

from ..asr import AsrSegment
from .base import DiarizedTurn

DEFAULT_LONG_SEGMENT_SPLIT_SEC = 10.0
DEFAULT_MIN_SPLIT_GAP_SEC = 0.6
DEFAULT_OVERLAP_TIE_BREAKER_SEC = 0.05


@dataclass(slots=True)
class ProjectionOutcome:
    """Result of projecting a diarization timeline onto ASR segments."""

    segments: list[AsrSegment]
    segment_speaker_ids: list[int]
    stats: dict[str, int | float]


def _overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def _turns_within(segment: AsrSegment, turns: list[DiarizedTurn]) -> list[DiarizedTurn]:
    hits: list[DiarizedTurn] = []
    for turn in turns:
        if turn.end <= segment.start or turn.start >= segment.end:
            continue
        if turn.duration <= 0.0:
            continue
        hits.append(turn)
    return hits


def _best_turn_for(segment: AsrSegment, turns: list[DiarizedTurn]) -> DiarizedTurn | None:
    best: DiarizedTurn | None = None
    best_overlap = -1.0
    for turn in turns:
        overlap = _overlap(segment.start, segment.end, turn.start, turn.end)
        if overlap > best_overlap + DEFAULT_OVERLAP_TIE_BREAKER_SEC:
            best = turn
            best_overlap = overlap
    return best


def _nearest_turn(segment: AsrSegment, turns: list[DiarizedTurn]) -> DiarizedTurn | None:
    if not turns:
        return None
    center = 0.5 * (segment.start + segment.end)
    return min(
        turns,
        key=lambda turn: abs(0.5 * (turn.start + turn.end) - center),
    )


def _split_segment(
    segment: AsrSegment,
    hits: list[DiarizedTurn],
    *,
    min_split_gap_sec: float,
) -> list[tuple[AsrSegment, int]]:
    """Split an ASR segment along diarization boundaries inside it."""

    if not hits:
        return [(segment, -1)]

    ordered = sorted(hits, key=lambda turn: turn.start)
    sub_segments: list[tuple[AsrSegment, int]] = []
    cursor = segment.start
    current_speaker = ordered[0].speaker_id

    def flush(new_start: float, new_end: float, speaker_id: int) -> None:
        if new_end - new_start < min_split_gap_sec:
            return
        suffix = f"-{len(sub_segments) + 1:02d}"
        sub_segments.append(
            (
                AsrSegment(
                    segment_id=f"{segment.segment_id}{suffix}",
                    start=round(new_start, 3),
                    end=round(new_end, 3),
                    text=segment.text,
                    language=segment.language,
                ),
                speaker_id,
            )
        )

    for idx, turn in enumerate(ordered):
        turn_end = min(segment.end, turn.end)
        turn_start = max(segment.start, turn.start)
        if turn.speaker_id != current_speaker and turn_start > cursor:
            flush(cursor, turn_start, current_speaker)
            cursor = turn_start
            current_speaker = turn.speaker_id
        if idx == len(ordered) - 1:
            flush(cursor, max(turn_end, segment.end), current_speaker)
            cursor = segment.end
    if cursor < segment.end:
        flush(cursor, segment.end, current_speaker)

    if not sub_segments:
        return [(segment, current_speaker)]
    return sub_segments


def assign_turns_to_segments(
    segments: list[AsrSegment],
    turns: list[DiarizedTurn],
    *,
    long_segment_split_sec: float = DEFAULT_LONG_SEGMENT_SPLIT_SEC,
    min_split_gap_sec: float = DEFAULT_MIN_SPLIT_GAP_SEC,
) -> ProjectionOutcome:
    """Project a diarization timeline onto ASR segments.

    Long segments (>= ``long_segment_split_sec``) that straddle multiple
    speakers are split at turn boundaries so low-frequency speakers are
    preserved instead of being absorbed by the dominant turn.
    """

    emitted_segments: list[AsrSegment] = []
    emitted_speakers: list[int] = []
    fallback_speaker = turns[0].speaker_id if turns else 0
    split_count = 0
    fallback_count = 0

    for segment in segments:
        hits = _turns_within(segment, turns)
        if not hits:
            nearest = _nearest_turn(segment, turns)
            speaker = nearest.speaker_id if nearest is not None else fallback_speaker
            emitted_segments.append(segment)
            emitted_speakers.append(speaker)
            fallback_count += 1
            continue

        speakers_in_hits = {turn.speaker_id for turn in hits}
        if (
            len(speakers_in_hits) > 1
            and segment.duration >= long_segment_split_sec
        ):
            parts = _split_segment(segment, hits, min_split_gap_sec=min_split_gap_sec)
            if len(parts) > 1:
                split_count += 1
            for sub_segment, speaker_id in parts:
                emitted_segments.append(sub_segment)
                emitted_speakers.append(speaker_id)
            continue

        best = _best_turn_for(segment, hits)
        speaker = best.speaker_id if best is not None else fallback_speaker
        emitted_segments.append(segment)
        emitted_speakers.append(speaker)

    stats = {
        "input_segment_count": len(segments),
        "output_segment_count": len(emitted_segments),
        "split_segment_count": split_count,
        "fallback_segment_count": fallback_count,
    }
    return ProjectionOutcome(
        segments=emitted_segments,
        segment_speaker_ids=emitted_speakers,
        stats=stats,
    )


def refine_with_change_detection(
    outcome: ProjectionOutcome,
    *,
    sandwich_max_sec: float = 1.5,
) -> ProjectionOutcome:
    """Stabilize speaker assignments by smoothing short sandwiched segments.

    If speaker ids form a pattern ``A B A`` and the middle segment is short,
    collapse it to ``A`` to remove jitter introduced by overlapping music or
    non-speech noise.  This mirrors ``_smooth_cluster_ids`` but runs on the
    projected output rather than raw cluster ids.
    """

    ids = list(outcome.segment_speaker_ids)
    if len(ids) < 3:
        return outcome
    for index in range(1, len(ids) - 1):
        prev_id = ids[index - 1]
        curr_id = ids[index]
        next_id = ids[index + 1]
        duration = outcome.segments[index].duration
        if prev_id == next_id and curr_id != prev_id and duration <= sandwich_max_sec:
            ids[index] = prev_id
    outcome.segment_speaker_ids = ids
    return outcome
