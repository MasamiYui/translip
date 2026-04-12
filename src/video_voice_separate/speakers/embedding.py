from __future__ import annotations

from typing import Any

import numpy as np

from ..speaker_embedding import (
    embedding_for_clip,
    extract_audio_clip,
    load_speechbrain_classifier,
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
    classifier = load_speechbrain_classifier(device)
    embedding_dim = 0

    for draft in drafts:
        for clip in draft.reference_clips:
            clip_waveform = extract_audio_clip(
                waveform,
                sample_rate,
                start=clip.start,
                end=clip.end,
            )
            embedding = embedding_for_clip(classifier, clip_waveform, sample_rate)
            clip.embedding = embedding
            if embedding is not None:
                embedding_dim = int(embedding.shape[0])

    return {
        "speaker_backend": "speechbrain-ecapa",
        "speaker_device": device,
        "embedding_dim": embedding_dim,
    }
