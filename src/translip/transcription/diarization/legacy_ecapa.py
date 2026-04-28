from __future__ import annotations

import importlib
import logging
import os
from pathlib import Path

import numpy as np

from ...speaker_embedding import (
    extract_audio_clip,
    get_speaker_embedder,
    read_audio_mono,
    resolve_speaker_device,
)
from ..asr import AsrSegment
from .base import DiarizationBackend, DiarizationResult, DiarizedTurn

logger = logging.getLogger(__name__)

RECLUSTER_ENV = "TRANSLIP_DIARIZATION_RECLUSTER"


class LegacyEcapaBackend(DiarizationBackend):
    """Reconstruct diarization turns from the legacy ECAPA+Agglomerative logic.

    This backend reproduces the cluster ids produced by
    ``translip.transcription.speaker`` so that switching to the new
    diarization pipeline is a pure no-op when ``backend=legacy_ecapa``.
    """

    name = "legacy_ecapa"

    def is_available(self) -> bool:
        return True

    def diarize(
        self,
        audio_path: Path,
        *,
        segments: list[AsrSegment],
        requested_device: str,
    ) -> DiarizationResult:
        # Import here to avoid a circular import with speaker.py (which imports
        # the diarization package to dispatch backends).
        from ..speaker import (
            _build_embedding_groups,
            _cluster_embeddings,
            _expanded_bounds,
            _smooth_cluster_ids,
        )

        if not segments:
            return DiarizationResult(
                turns=[],
                backend=self.name,
                metadata={
                    "speaker_backend": "speechbrain-ecapa",
                    "speaker_count": 0,
                    "group_count": 0,
                    "valid_embeddings": 0,
                },
            )

        waveform, sample_rate = read_audio_mono(audio_path)
        audio_duration = len(waveform) / float(sample_rate)
        device = resolve_speaker_device(requested_device)
        embedder = get_speaker_embedder(device)

        groups = _build_embedding_groups(segments)
        embeddings: list[np.ndarray | None] = []
        for group in groups:
            window = _expanded_bounds(
                group.start,
                group.end,
                audio_duration=audio_duration,
                min_window_sec=2.0,
            )
            clip = extract_audio_clip(
                waveform,
                sample_rate,
                start=window.start,
                end=window.end,
            )
            if clip.size < int(0.25 * sample_rate):
                embeddings.append(None)
                continue
            embeddings.append(embedder.encode(clip, sample_rate))

        valid_indices = [index for index, value in enumerate(embeddings) if value is not None]
        if not valid_indices:
            # Every segment collapses to a single speaker.
            turn = DiarizedTurn(
                start=float(segments[0].start),
                end=float(segments[-1].end),
                speaker_id=0,
            )
            return DiarizationResult(
                turns=[turn],
                backend=self.name,
                metadata={
                    "speaker_backend": embedder.name,
                    "speaker_device": device,
                    "speaker_count": 1,
                    "group_count": len(groups),
                    "valid_embeddings": 0,
                },
            )

        matrix = np.stack([embeddings[index] for index in valid_indices]).astype(np.float32)
        valid_cluster_ids = _cluster_embeddings(matrix)
        recluster_mode = _resolve_recluster_mode()
        valid_cluster_ids, recluster_info = _maybe_recluster(matrix, valid_cluster_ids, recluster_mode)

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

        turns = _contiguous_turns(segments, final_cluster_ids)
        metadata: dict[str, object] = {
            "speaker_backend": embedder.name,
            "speaker_device": device,
            "speaker_count": len({turn.speaker_id for turn in turns}),
            "group_count": len(groups),
            "valid_embeddings": len(valid_indices),
        }
        metadata.update(recluster_info)
        return DiarizationResult(
            turns=turns,
            backend=self.name,
            metadata=metadata,
        )


def _contiguous_turns(segments: list[AsrSegment], cluster_ids: list[int]) -> list[DiarizedTurn]:
    """Collapse consecutive same-speaker segments into a single diarized turn."""

    turns: list[DiarizedTurn] = []
    if not segments:
        return turns
    current_start = segments[0].start
    current_end = segments[0].end
    current_speaker = cluster_ids[0]
    for segment, cluster_id in zip(segments[1:], cluster_ids[1:], strict=True):
        if cluster_id == current_speaker:
            current_end = segment.end
            continue
        turns.append(
            DiarizedTurn(
                start=float(current_start),
                end=float(current_end),
                speaker_id=int(current_speaker),
            )
        )
        current_start = segment.start
        current_end = segment.end
        current_speaker = cluster_id
    turns.append(
        DiarizedTurn(
            start=float(current_start),
            end=float(current_end),
            speaker_id=int(current_speaker),
        )
    )
    return turns


def _resolve_recluster_mode(raw: str | None = None) -> str:
    """Return the active reclustering strategy.

    ``off`` disables the second pass entirely (default).  ``hdbscan`` runs an
    HDBSCAN refinement over the ECAPA/ERes2NetV2 embeddings if the optional
    dependency is installed; ``auto`` picks ``hdbscan`` when available and
    otherwise falls back to ``off`` silently.
    """

    value = (raw or os.environ.get(RECLUSTER_ENV) or "off").strip().lower()
    if value in {"", "off", "none", "false", "0"}:
        return "off"
    if value in {"hdbscan"}:
        return "hdbscan"
    if value == "auto":
        return "hdbscan" if importlib.util.find_spec("hdbscan") is not None else "off"
    return "off"


def _maybe_recluster(
    matrix: np.ndarray,
    cluster_ids: np.ndarray,
    mode: str,
) -> tuple[np.ndarray, dict[str, object]]:
    if mode != "hdbscan" or matrix.shape[0] < 3:
        return cluster_ids, {"recluster": "off"}
    try:
        import hdbscan
    except ImportError:
        logger.info("hdbscan requested but not installed; skipping reclustering.")
        return cluster_ids, {"recluster": "off", "recluster_error": "hdbscan-missing"}

    try:
        clusterer = hdbscan.HDBSCAN(
            metric="euclidean",
            min_cluster_size=max(2, int(round(matrix.shape[0] * 0.05))),
            min_samples=1,
            cluster_selection_method="leaf",
            allow_single_cluster=True,
        )
        refined = clusterer.fit_predict(matrix.astype(np.float64))
    except Exception as exc:  # pragma: no cover - defensive; HDBSCAN rarely raises
        logger.warning("HDBSCAN reclustering failed: %s", exc)
        return cluster_ids, {"recluster": "off", "recluster_error": str(exc)}

    refined_ids = np.asarray(refined, dtype=np.int32)
    # HDBSCAN marks outliers as -1; merge them back into the nearest
    # Agglomerative cluster to preserve the "one speaker per segment" contract.
    if np.any(refined_ids < 0):
        refined_ids = _stitch_noise(refined_ids, cluster_ids.astype(np.int32))

    refined_count = len({int(cid) for cid in refined_ids})
    original_count = len({int(cid) for cid in cluster_ids})
    # Only apply reclustering if it produced a *finer* partition with at least
    # two clusters; otherwise keep the Agglomerative result to avoid regressing
    # single-speaker audio.
    if refined_count < 2 or refined_count < original_count:
        return cluster_ids, {
            "recluster": "hdbscan-skipped",
            "recluster_clusters_original": original_count,
            "recluster_clusters_refined": refined_count,
        }
    return refined_ids, {
        "recluster": "hdbscan",
        "recluster_clusters_original": original_count,
        "recluster_clusters_refined": refined_count,
    }


def _stitch_noise(refined: np.ndarray, fallback: np.ndarray) -> np.ndarray:
    out = refined.copy()
    for index, value in enumerate(out):
        if value >= 0:
            continue
        # Inherit the label of the nearest non-noise neighbour; fall back to
        # the Agglomerative label if the entire set was flagged as noise.
        left = _nearest_labelled(out, index, step=-1)
        right = _nearest_labelled(out, index, step=1)
        if left is not None:
            out[index] = left
        elif right is not None:
            out[index] = right
        else:
            out[index] = int(fallback[index])
    return out


def _nearest_labelled(values: np.ndarray, start: int, step: int) -> int | None:
    idx = start + step
    while 0 <= idx < len(values):
        if values[idx] >= 0:
            return int(values[idx])
        idx += step
    return None
