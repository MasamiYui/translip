from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from ..types import TranscriptionSegment

MIN_REFERENCE_SEC = 1.5
MAX_REFERENCE_SEC = 15.0
MAX_REFERENCE_CLIPS = 5
MERGE_GAP_SEC = 0.6


@dataclass(slots=True)
class ReferenceClip:
    clip_id: str
    start: float
    end: float
    duration: float
    segment_ids: list[str]
    text: str
    rms: float
    path: Path | None = None
    embedding: np.ndarray | None = None


@dataclass(slots=True)
class SpeakerProfileDraft:
    profile_id: str
    source_label: str
    segments: list[TranscriptionSegment]
    total_speech_sec: float
    reference_clips: list[ReferenceClip] = field(default_factory=list)


def load_segments_payload(path: Path) -> tuple[dict[str, Any], list[TranscriptionSegment]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    segments = [
        TranscriptionSegment(
            segment_id=item["id"],
            start=float(item["start"]),
            end=float(item["end"]),
            text=item["text"],
            speaker_label=item["speaker_label"],
            language=item.get("language", "unknown"),
            duration=float(item.get("duration") or (float(item["end"]) - float(item["start"]))),
        )
        for item in payload.get("segments", [])
    ]
    return payload, segments


def _merge_adjacent_segments(segments: list[TranscriptionSegment]) -> list[list[TranscriptionSegment]]:
    if not segments:
        return []
    ordered = sorted(segments, key=lambda item: (item.start, item.end))
    merged: list[list[TranscriptionSegment]] = [[ordered[0]]]
    for segment in ordered[1:]:
        current = merged[-1]
        gap = max(0.0, segment.start - current[-1].end)
        if gap <= MERGE_GAP_SEC and (segment.end - current[0].start) <= MAX_REFERENCE_SEC:
            current.append(segment)
            continue
        merged.append([segment])
    return merged


def _segment_group_rms(
    waveform: np.ndarray,
    sample_rate: int,
    *,
    start: float,
    end: float,
) -> float:
    start_idx = max(0, int(start * sample_rate))
    end_idx = min(len(waveform), int(end * sample_rate))
    if end_idx <= start_idx:
        return 0.0
    clip = waveform[start_idx:end_idx]
    if clip.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(clip))))


def _select_reference_groups(
    waveform: np.ndarray,
    sample_rate: int,
    merged_groups: list[list[TranscriptionSegment]],
) -> list[ReferenceClip]:
    candidates: list[ReferenceClip] = []
    for group_index, group in enumerate(merged_groups, start=1):
        start = group[0].start
        end = group[-1].end
        duration = max(0.0, end - start)
        if duration < MIN_REFERENCE_SEC or duration > MAX_REFERENCE_SEC:
            continue
        candidates.append(
            ReferenceClip(
                clip_id=f"clip_{group_index:04d}",
                start=round(start, 3),
                end=round(end, 3),
                duration=round(duration, 3),
                segment_ids=[segment.segment_id for segment in group],
                text=" ".join(segment.text for segment in group).strip(),
                rms=_segment_group_rms(waveform, sample_rate, start=start, end=end),
            )
        )

    if candidates:
        ranked = sorted(candidates, key=lambda item: (item.duration, item.rms), reverse=True)
        return ranked[:MAX_REFERENCE_CLIPS]

    fallback_groups = sorted(
        merged_groups,
        key=lambda group: (group[-1].end - group[0].start),
        reverse=True,
    )[:MAX_REFERENCE_CLIPS]
    fallbacks: list[ReferenceClip] = []
    for group_index, group in enumerate(fallback_groups, start=1):
        start = group[0].start
        end = group[-1].end
        duration = max(0.0, end - start)
        if duration <= 0.0:
            continue
        fallbacks.append(
            ReferenceClip(
                clip_id=f"clip_{group_index:04d}",
                start=round(start, 3),
                end=round(end, 3),
                duration=round(duration, 3),
                segment_ids=[segment.segment_id for segment in group],
                text=" ".join(segment.text for segment in group).strip(),
                rms=_segment_group_rms(waveform, sample_rate, start=start, end=end),
            )
        )
    return fallbacks


def build_profile_drafts(
    segments: list[TranscriptionSegment],
    *,
    waveform: np.ndarray,
    sample_rate: int,
) -> list[SpeakerProfileDraft]:
    by_label: dict[str, list[TranscriptionSegment]] = {}
    for segment in segments:
        by_label.setdefault(segment.speaker_label, []).append(segment)

    drafts: list[SpeakerProfileDraft] = []
    for profile_index, source_label in enumerate(sorted(by_label.keys()), start=0):
        speaker_segments = sorted(by_label[source_label], key=lambda item: (item.start, item.end))
        merged_groups = _merge_adjacent_segments(speaker_segments)
        references = _select_reference_groups(waveform, sample_rate, merged_groups)
        total_speech_sec = round(sum(segment.duration for segment in speaker_segments), 3)
        drafts.append(
            SpeakerProfileDraft(
                profile_id=f"profile_{profile_index:04d}",
                source_label=source_label,
                segments=speaker_segments,
                total_speech_sec=total_speech_sec,
                reference_clips=references,
            )
        )
    return drafts


def export_reference_clips(
    drafts: list[SpeakerProfileDraft],
    *,
    waveform: np.ndarray,
    sample_rate: int,
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for draft in drafts:
        profile_dir = output_dir / draft.profile_id
        profile_dir.mkdir(parents=True, exist_ok=True)
        for index, clip in enumerate(draft.reference_clips, start=1):
            clip_path = profile_dir / f"clip_{index:04d}.wav"
            start_idx = max(0, int(clip.start * sample_rate))
            end_idx = min(len(waveform), int(clip.end * sample_rate))
            sf.write(clip_path, waveform[start_idx:end_idx], sample_rate)
            clip.path = clip_path
