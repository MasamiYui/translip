from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class SegmentRecord:
    segment_id: str
    start: float
    end: float
    duration: float
    speaker_label: str
    speaker_id: str | None
    text: str
    language: str


@dataclass(slots=True)
class ContextUnit:
    unit_id: str
    speaker_label: str
    speaker_id: str | None
    start: float
    end: float
    segments: list[SegmentRecord]

    @property
    def source_text(self) -> str:
        return " ".join(segment.text for segment in self.segments).strip()


def build_context_units(
    segments: list[SegmentRecord],
    *,
    max_gap_sec: float = 0.8,
    max_unit_duration_sec: float = 12.0,
    max_unit_segments: int = 6,
) -> list[ContextUnit]:
    if not segments:
        return []

    units: list[ContextUnit] = []
    current: list[SegmentRecord] = [segments[0]]

    def flush() -> None:
        if not current:
            return
        first = current[0]
        last = current[-1]
        units.append(
            ContextUnit(
                unit_id=f"unit-{len(units) + 1:04d}",
                speaker_label=first.speaker_label,
                speaker_id=first.speaker_id,
                start=first.start,
                end=last.end,
                segments=list(current),
            )
        )

    for segment in segments[1:]:
        last = current[-1]
        same_speaker = (
            segment.speaker_id == last.speaker_id
            if segment.speaker_id is not None and last.speaker_id is not None
            else segment.speaker_label == last.speaker_label
        )
        gap = max(0.0, segment.start - last.end)
        candidate_duration = segment.end - current[0].start
        if (
            same_speaker
            and gap <= max_gap_sec
            and candidate_duration <= max_unit_duration_sec
            and len(current) < max_unit_segments
        ):
            current.append(segment)
            continue
        flush()
        current = [segment]

    flush()
    return units
