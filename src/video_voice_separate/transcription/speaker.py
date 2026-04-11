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
    return embedding_for_clip(classifier, clip)


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
) -> tuple[list[str], dict[str, int | float | str]]:
    if not segments:
        return [], {"speaker_backend": "speechbrain-ecapa", "speaker_count": 0}

    waveform, sample_rate = read_audio_mono(audio_path)
    audio_duration = len(waveform) / float(sample_rate)
    device = resolve_speaker_device(requested_device)
    classifier = load_speechbrain_classifier(device)

    groups = _build_embedding_groups(segments)
    embeddings: list[np.ndarray | None] = []
    for group in groups:
        window = _expanded_bounds(group.start, group.end, audio_duration=audio_duration, min_window_sec=2.0)
        embeddings.append(_segment_embedding(classifier, waveform, sample_rate, window))

    valid_indices = [index for index, value in enumerate(embeddings) if value is not None]
    if not valid_indices:
        labels = ["SPEAKER_00"] * len(segments)
        return labels, {
            "speaker_backend": "speechbrain-ecapa",
            "speaker_device": device,
            "speaker_count": 1 if segments else 0,
            "valid_embeddings": 0,
            "group_count": len(groups),
        }

    matrix = np.stack([embeddings[index] for index in valid_indices]).astype(np.float32)
    valid_cluster_ids = _cluster_embeddings(matrix)

    group_cluster_ids: list[int | None] = [None] * len(groups)
    for group_index, cluster_id in zip(valid_indices, valid_cluster_ids, strict=True):
        group_cluster_ids[group_index] = int(cluster_id)

    fallback_cluster = int(valid_cluster_ids[0]) if len(valid_cluster_ids) else 0
    for index, cluster_id in enumerate(group_cluster_ids):
        if cluster_id is not None:
            continue
        nearest_index = min(valid_indices, key=lambda other: abs(other - index))
        group_cluster_ids[index] = (
            group_cluster_ids[nearest_index]
            if group_cluster_ids[nearest_index] is not None
            else fallback_cluster
        )

    final_group_cluster_ids = [
        int(cluster_id if cluster_id is not None else fallback_cluster)
        for cluster_id in group_cluster_ids
    ]
    final_cluster_ids = [0] * len(segments)
    for group, group_cluster_id in zip(groups, final_group_cluster_ids, strict=True):
        for segment_index in group.segment_indices:
            final_cluster_ids[segment_index] = group_cluster_id

    final_cluster_ids = _smooth_cluster_ids(final_cluster_ids, segments)
    labels = _stable_relabel(final_cluster_ids)
    speaker_count = len(set(labels))
    return labels, {
        "speaker_backend": "speechbrain-ecapa",
        "speaker_device": device,
        "speaker_count": speaker_count,
        "valid_embeddings": len(valid_indices),
        "group_count": len(groups),
    }
