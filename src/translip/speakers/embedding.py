from __future__ import annotations

from typing import Any

import numpy as np

from ..speaker_embedding import (
    extract_audio_clip,
    get_speaker_embedder,
    read_audio_mono,
    resolve_speaker_device,
)
from .reference import SpeakerProfileDraft


def load_audio_for_embeddings(audio_path):
    return read_audio_mono(audio_path)


def enrich_reference_embeddings(
    drafts: list[SpeakerProfileDraft],
    *,
    waveform: np.ndarray,
    sample_rate: int,
    requested_device: str,
) -> dict[str, Any]:
    device = resolve_speaker_device(requested_device)
    embedder = get_speaker_embedder(device)
    embedding_dim = 0

    for draft in drafts:
        for clip in draft.reference_clips:
            clip_waveform = extract_audio_clip(
                waveform,
                sample_rate,
                start=clip.start,
                end=clip.end,
            )
            embedding = embedder.encode(clip_waveform, sample_rate)
            clip.embedding = embedding
            if embedding is not None:
                embedding_dim = int(embedding.shape[0])

    return {
        "speaker_backend": embedder.name,
        "speaker_device": device,
        "embedding_dim": embedding_dim,
    }
