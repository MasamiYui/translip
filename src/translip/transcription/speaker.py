from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from sklearn.cluster import AgglomerativeClustering

from ..speaker_embedding import (
    embedding_for_clip,
    extract_audio_clip,
    load_speechbrain_classifier,
    read_audio_mono,
    resolve_speaker_device,
)
from .asr import AsrSegment

logger = logging.getLogger(__name__)

DEFAULT_SAME_SPEAKER_SIMILARITY = 0.62
DEFAULT_SINGLE_SPEAKER_FLOOR = 0.52


@dataclass(slots=True)
class SpeakerWindow:
    start: float
    end: float


@dataclass(slots=True)
class EmbeddingGroup:
    start: float
    end: float
    segment_indices: list[int]

def _expanded_window(
    segment: AsrSegment,
    *,
    audio_duration: float,
    margin_sec: float = 0.2,
    min_window_sec: float = 1.6,
) -> SpeakerWindow:
    start = max(0.0, segment.start - margin_sec)
    end = min(audio_duration, segment.end + margin_sec)
    duration = end - start
    if duration >= min_window_sec:
        return SpeakerWindow(start=start, end=end)

    pad = (min_window_sec - duration) / 2.0
    start = max(0.0, start - pad)
    end = min(audio_duration, end + pad)
    duration = end - start
    if duration >= min_window_sec:
        return SpeakerWindow(start=start, end=end)

    if start <= 0.0:
        end = min(audio_duration, min_window_sec)
    elif end >= audio_duration:
        start = max(0.0, audio_duration - min_window_sec)
    return SpeakerWindow(start=start, end=end)


def _expanded_bounds(
    start: float,
    end: float,
    *,
    audio_duration: float,
    margin_sec: float = 0.2,
    min_window_sec: float = 1.6,
) -> SpeakerWindow:
    return _expanded_window(
        AsrSegment(
            segment_id="group",
            start=start,
            end=end,
            text="",
            language="",
        ),
        audio_duration=audio_duration,
        margin_sec=margin_sec,
        min_window_sec=min_window_sec,
    )


def _build_embedding_groups(
    segments: list[AsrSegment],
    *,
    max_gap_sec: float = 0.45,
    max_group_sec: float = 8.0,
    max_segments: int = 5,
) -> list[EmbeddingGroup]:
    if not segments:
        return []

    groups: list[EmbeddingGroup] = []
    current_indices = [0]
    current_start = segments[0].start
    current_end = segments[0].end

    for index in range(1, len(segments)):
        segment = segments[index]
        gap = max(0.0, segment.start - current_end)
        proposed_duration = segment.end - current_start
        if (
            gap <= max_gap_sec
            and proposed_duration <= max_group_sec
            and len(current_indices) < max_segments
        ):
            current_indices.append(index)
            current_end = segment.end
            continue

        groups.append(
            EmbeddingGroup(
                start=current_start,
                end=current_end,
                segment_indices=current_indices[:],
            )
        )
        current_indices = [index]
        current_start = segment.start
        current_end = segment.end

    groups.append(
        EmbeddingGroup(
            start=current_start,
            end=current_end,
            segment_indices=current_indices[:],
        )
    )
    return groups
def _segment_embedding(
    classifier,
    waveform: np.ndarray,
    sample_rate: int,
    window: SpeakerWindow,
) -> np.ndarray | None:
    clip = extract_audio_clip(
        waveform,
        sample_rate,
        start=window.start,
        end=window.end,
    )
    if clip.size < int(0.25 * sample_rate):
        return None
    return embedding_for_clip(classifier, clip, sample_rate)


def _pairwise_similarities(embeddings: np.ndarray) -> np.ndarray:
    sims = embeddings @ embeddings.T
    upper = sims[np.triu_indices_from(sims, k=1)]
    return upper.astype(np.float32)


def _is_single_speaker(embeddings: np.ndarray) -> bool:
    if len(embeddings) <= 1:
        return True
    sims = _pairwise_similarities(embeddings)
    if sims.size == 0:
        return True
    return float(np.percentile(sims, 20)) >= DEFAULT_SINGLE_SPEAKER_FLOOR


def _speaker_cap(num_embeddings: int) -> int:
    if num_embeddings <= 1:
        return 1
    if num_embeddings <= 6:
        return num_embeddings
    return max(2, min(8, num_embeddings // 6 + 1))


def _cluster_embeddings(embeddings: np.ndarray) -> np.ndarray:
    if len(embeddings) <= 1:
        return np.zeros(len(embeddings), dtype=np.int32)
    if _is_single_speaker(embeddings):
        return np.zeros(len(embeddings), dtype=np.int32)

    clusterer = AgglomerativeClustering(
        n_clusters=None,
        metric="cosine",
        linkage="average",
        distance_threshold=1.0 - DEFAULT_SAME_SPEAKER_SIMILARITY,
    )
    cluster_ids = clusterer.fit_predict(embeddings).astype(np.int32)
    cluster_count = len(set(cluster_ids.tolist()))
    cap = _speaker_cap(len(embeddings))
    if cluster_count <= cap:
        return cluster_ids

    logger.info(
        "Speaker clustering produced %s clusters for %s embedding groups. Re-clustering with cap=%s.",
        cluster_count,
        len(embeddings),
        cap,
    )
    capped_clusterer = AgglomerativeClustering(
        n_clusters=cap,
        metric="cosine",
        linkage="average",
    )
    return capped_clusterer.fit_predict(embeddings).astype(np.int32)


def _stable_relabel(cluster_ids: list[int]) -> list[str]:
    mapping: dict[int, str] = {}
    labels: list[str] = []
    next_id = 0
    for cluster_id in cluster_ids:
        if cluster_id not in mapping:
            mapping[cluster_id] = f"SPEAKER_{next_id:02d}"
            next_id += 1
        labels.append(mapping[cluster_id])
    return labels


def _smooth_cluster_ids(cluster_ids: list[int], segments: list[AsrSegment]) -> list[int]:
    if len(cluster_ids) < 3:
        return cluster_ids
    smoothed = cluster_ids[:]
    for index in range(1, len(cluster_ids) - 1):
        prev_id = smoothed[index - 1]
        curr_id = smoothed[index]
        next_id = smoothed[index + 1]
        if prev_id == next_id and curr_id != prev_id and segments[index].duration <= 1.5:
            smoothed[index] = prev_id
    return smoothed


def assign_speaker_labels(
    audio_path: Path,
    segments: list[AsrSegment],
    *,
    requested_device: str,
    backend: str | None = None,
) -> tuple[list[str], dict[str, int | float | str]]:
    """Assign speaker labels by running diarization and projecting onto ASR segments.

    The actual diarization is delegated to a pluggable backend
    (:mod:`translip.transcription.diarization`).  Legacy callers can keep
    the historic ECAPA+Agglomerative behaviour by setting
    ``backend="legacy_ecapa"`` or via the ``TRANSLIP_DIARIZATION_BACKEND``
    environment variable; ``"auto"`` prefers the Chinese-optimised
    3D-Speaker pipeline and falls back to ``legacy_ecapa`` when the
    optional modelscope dependency is unavailable.
    """

    from .diarization import (
        assign_turns_to_segments,
        create_backend,
        refine_with_change_detection,
        resolve_backend_name,
    )

    if not segments:
        return [], {
            "speaker_backend": "speechbrain-ecapa",
            "diarization_backend": resolve_backend_name(backend),
            "speaker_count": 0,
        }

    diarizer = create_backend(backend)
    result = diarizer.diarize(
        audio_path,
        segments=segments,
        requested_device=requested_device,
    )

    outcome = assign_turns_to_segments(segments, result.turns)
    outcome = refine_with_change_detection(outcome)

    # task-a's public contract guarantees a one-to-one mapping with the
    # original ASR segments; merge any turn-boundary splits back to the
    # dominant label of the parent segment.
    labels_by_index: dict[str, list[int]] = {}
    for seg, speaker_id in zip(outcome.segments, outcome.segment_speaker_ids, strict=True):
        parent_id = seg.segment_id.split("-")[0:2]
        key = "-".join(parent_id)
        labels_by_index.setdefault(key, []).append(speaker_id)

    speaker_ids_per_segment: list[int] = []
    for segment in segments:
        votes = labels_by_index.get(segment.segment_id, [])
        if not votes:
            votes = [0]
        speaker_ids_per_segment.append(_majority(votes))

    labels = _stable_relabel(speaker_ids_per_segment)
    metadata: dict[str, int | float | str] = {
        "speaker_backend": str(result.metadata.get("speaker_backend", "speechbrain-ecapa")),
        "diarization_backend": diarizer.name,
        "speaker_count": len(set(labels)),
    }
    # Surface backend-specific telemetry without clobbering core fields.
    for key, value in result.metadata.items():
        if key in {"speaker_backend", "speaker_count"}:
            continue
        if isinstance(value, (int, float, str)):
            metadata[f"diarization_{key}"] = value
    metadata["diarization_turn_count"] = len(result.turns)
    metadata["diarization_split_segments"] = int(outcome.stats.get("split_segment_count", 0))
    metadata["diarization_fallback_segments"] = int(outcome.stats.get("fallback_segment_count", 0))
    return labels, metadata


def _majority(values: list[int]) -> int:
    counts: dict[int, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return max(counts.items(), key=lambda item: (item[1], -item[0]))[0]
