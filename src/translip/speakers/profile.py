from __future__ import annotations

from typing import Any

import numpy as np

from ..speaker_embedding import normalize_embedding
from .reference import SpeakerProfileDraft


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))


def _prototype_from_embeddings(embeddings: list[np.ndarray]) -> np.ndarray:
    if len(embeddings) == 1:
        return embeddings[0]

    matrix = np.stack(embeddings).astype(np.float32)
    sims = matrix @ matrix.T
    mean_sims = sims.mean(axis=1)
    center_index = int(np.argmax(mean_sims))
    center = matrix[center_index]
    keep_indices = [index for index, emb in enumerate(matrix) if _cosine(center, emb) >= 0.6]
    if not keep_indices:
        keep_indices = list(range(len(matrix)))
    kept = matrix[keep_indices]
    return normalize_embedding(kept.mean(axis=0))


def build_profiles_payload(
    drafts: list[SpeakerProfileDraft],
    *,
    backend: dict[str, Any],
) -> dict[str, Any]:
    profiles: list[dict[str, Any]] = []
    for draft in drafts:
        valid_embeddings = [clip.embedding for clip in draft.reference_clips if clip.embedding is not None]
        prototype_embedding = _prototype_from_embeddings(valid_embeddings) if valid_embeddings else None
        profiles.append(
            {
                "profile_id": draft.profile_id,
                "source_label": draft.source_label,
                "speaker_id": None,
                "display_name": None,
                "status": "unmatched",
                "total_speech_sec": draft.total_speech_sec,
                "segment_count": len(draft.segments),
                "reference_clip_count": len(draft.reference_clips),
                "prototype_embedding": (
                    [round(float(value), 6) for value in prototype_embedding.tolist()]
                    if prototype_embedding is not None
                    else None
                ),
                "reference_clips": [
                    {
                        "path": str(clip.path) if clip.path is not None else None,
                        "start": clip.start,
                        "end": clip.end,
                        "duration": clip.duration,
                        "segment_ids": clip.segment_ids,
                        "text": clip.text,
                        "rms": round(clip.rms, 6),
                    }
                    for clip in draft.reference_clips
                ],
            }
        )

    return {
        "backend": {
            "speaker_backend": backend.get("speaker_backend"),
            "speaker_device": backend.get("speaker_device"),
            "embedding_dim": backend.get("embedding_dim"),
        },
        "profiles": profiles,
    }
