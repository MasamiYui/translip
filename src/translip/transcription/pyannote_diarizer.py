from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path

import torch

from .asr import AsrSegment

logger = logging.getLogger(__name__)


_DEFAULT_PIPELINE = "pyannote/speaker-diarization-3.1"


def _resolve_pyannote_device(requested_device: str) -> str:
    if requested_device == "cuda" and torch.cuda.is_available():
        return "cuda"
    if requested_device == "mps":
        if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
            return "mps"
        return "cpu"
    if requested_device == "auto":
        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
            return "mps"
        return "cpu"
    return "cpu"


@lru_cache(maxsize=2)
def _load_pipeline(model_id: str, device: str):
    try:
        from pyannote.audio import Pipeline
    except ImportError as exc:  # pragma: no cover - import guard
        raise RuntimeError(
            "pyannote.audio is not installed. Run `pip install pyannote.audio` to enable the pyannote diarizer."
        ) from exc

    auth_token = (
        os.environ.get("PYANNOTE_AUTH_TOKEN")
        or os.environ.get("HUGGINGFACE_HUB_TOKEN")
        or os.environ.get("HF_TOKEN")
    )
    pipeline = Pipeline.from_pretrained(model_id, use_auth_token=auth_token)
    if pipeline is None:
        raise RuntimeError(
            f"Failed to load pyannote pipeline `{model_id}`. "
            "Ensure you have accepted the model license and provided a HF token via "
            "PYANNOTE_AUTH_TOKEN / HUGGINGFACE_HUB_TOKEN / HF_TOKEN."
        )
    try:
        pipeline.to(torch.device(device))
    except Exception:  # pragma: no cover - best effort device move
        logger.warning("Failed to move pyannote pipeline to %s; staying on default device.", device)
    return pipeline


def _stable_relabel(raw_labels: list[str]) -> list[str]:
    mapping: dict[str, str] = {}
    next_id = 0
    relabeled: list[str] = []
    for label in raw_labels:
        if label not in mapping:
            mapping[label] = f"SPEAKER_{next_id:02d}"
            next_id += 1
        relabeled.append(mapping[label])
    return relabeled


def _assign_label_for_segment(
    segment: AsrSegment,
    diarization_turns: list[tuple[float, float, str]],
    fallback_label: str,
) -> str:
    if not diarization_turns:
        return fallback_label

    seg_start, seg_end = float(segment.start), float(segment.end)
    if seg_end <= seg_start:
        seg_end = seg_start + 1e-3

    best_label = fallback_label
    best_overlap = 0.0
    for turn_start, turn_end, label in diarization_turns:
        overlap = max(0.0, min(seg_end, turn_end) - max(seg_start, turn_start))
        if overlap > best_overlap:
            best_overlap = overlap
            best_label = label

    if best_overlap > 0.0:
        return best_label

    midpoint = 0.5 * (seg_start + seg_end)
    nearest_label = fallback_label
    nearest_distance = float("inf")
    for turn_start, turn_end, label in diarization_turns:
        if turn_end < seg_start:
            distance = seg_start - turn_end
        elif turn_start > seg_end:
            distance = turn_start - seg_end
        else:
            distance = abs(0.5 * (turn_start + turn_end) - midpoint)
        if distance < nearest_distance:
            nearest_distance = distance
            nearest_label = label
    return nearest_label


def assign_speaker_labels(
    audio_path: Path,
    segments: list[AsrSegment],
    *,
    requested_device: str,
    pipeline_id: str = _DEFAULT_PIPELINE,
) -> tuple[list[str], dict[str, int | float | str]]:
    if not segments:
        return [], {"speaker_backend": "pyannote-3.1", "speaker_count": 0}

    device = _resolve_pyannote_device(requested_device)
    pipeline = _load_pipeline(pipeline_id, device)

    diarization = pipeline(str(audio_path))

    raw_turns: list[tuple[float, float, str]] = []
    for turn, _, raw_label in diarization.itertracks(yield_label=True):
        raw_turns.append((float(turn.start), float(turn.end), str(raw_label)))

    if not raw_turns:
        labels = ["SPEAKER_00"] * len(segments)
        return labels, {
            "speaker_backend": "pyannote-3.1",
            "speaker_device": device,
            "speaker_count": 1,
            "diarization_turns": 0,
        }

    raw_turns.sort(key=lambda item: item[0])
    canonical = _stable_relabel([label for _, _, label in raw_turns])
    canonical_turns = [
        (start, end, canonical_label)
        for (start, end, _), canonical_label in zip(raw_turns, canonical, strict=True)
    ]

    fallback_label = canonical_turns[0][2]
    labels = [
        _assign_label_for_segment(segment, canonical_turns, fallback_label)
        for segment in segments
    ]

    return labels, {
        "speaker_backend": "pyannote-3.1",
        "speaker_device": device,
        "speaker_count": len(set(labels)),
        "diarization_turns": len(canonical_turns),
        "pipeline_id": pipeline_id,
    }


__all__ = ["assign_speaker_labels"]
