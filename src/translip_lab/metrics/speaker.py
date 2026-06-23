"""Speaker-similarity (SIM) for voice-clone TTS eval: cosine over speaker embeddings.

The ``tts-clone`` scenario asks "does the synthesized speech preserve the target
*timbre*" — the dimension translip's intrinsic dub score under-reports. Following
seed-tts-eval, SIM is the cosine similarity between a speaker embedding of the
reference voice and of the generated audio.

The default embedder reuses translip's in-tree ECAPA (speechbrain) — the same
model the diarization backend uses — imported lazily so the lab stays importable
without it, and degrading to ``sim=None`` (never a crash) when it is absent. The
embedder is injectable so the metric is unit-testable offline with a pure-numpy
stand-in (no torch, no model download).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import numpy as np

EmbedFn = Callable[[Any], "np.ndarray | None"]


def cosine_similarity(a: Any, b: Any, *, eps: float = 1e-12) -> float:
    """Cosine similarity of two vectors, in [-1, 1]. Length-mismatch is truncated."""
    va = np.asarray(a, dtype=np.float64).reshape(-1)
    vb = np.asarray(b, dtype=np.float64).reshape(-1)
    n = min(len(va), len(vb))
    if n == 0:
        return 0.0
    va, vb = va[:n], vb[:n]
    denom = (float(np.linalg.norm(va)) * float(np.linalg.norm(vb))) + eps
    return float(np.dot(va, vb) / denom)


def _ecapa_embedder(device: str = "auto") -> EmbedFn:
    """Resolve translip's in-tree ECAPA embedder (lazy; may raise on missing deps).

    Loads the speechbrain classifier once and returns a ``path -> embedding``
    closure. Same model/weights the ``ecapa`` diarization backend uses, so SIM is
    measured with the speaker space translip itself reasons in.
    """
    from translip.speaker_embedding import (
        embedding_for_clip,
        load_speechbrain_classifier,
        read_audio_mono,
        resolve_speaker_device,
    )

    classifier = load_speechbrain_classifier(resolve_speaker_device(device))

    def embed(path: Any) -> "np.ndarray | None":
        waveform, sample_rate = read_audio_mono(Path(path))
        return embedding_for_clip(classifier, waveform, sample_rate)

    return embed


def speaker_similarity(
    reference_wav: Any,
    hypothesis_wav: Any,
    *,
    embed_fn: EmbedFn | None = None,
    device: str = "auto",
) -> dict[str, Any]:
    """Cosine SIM between reference-voice and generated-audio speaker embeddings.

    Returns ``{"sim": float|None, "embedding_dim": int|None, "note"?: str}``. On any
    embedder failure (speechbrain missing, model load error, empty/short clip) the
    metric degrades to ``sim=None`` with a note rather than raising — the scenario
    still reports intelligibility (CER). ``embed_fn`` overrides the default ECAPA
    embedder (used by tests to stay offline).
    """
    try:
        embed = embed_fn or _ecapa_embedder(device)
        ref_emb = embed(reference_wav)
        hyp_emb = embed(hypothesis_wav)
    except Exception as exc:  # noqa: BLE001 — degrade, never crash the run
        return {"sim": None, "embedding_dim": None,
                "note": f"embedder unavailable: {type(exc).__name__}: {exc}"}
    if ref_emb is None or hyp_emb is None:
        return {"sim": None, "embedding_dim": None,
                "note": "embedder returned no embedding (clip too short or silent?)"}
    dim = int(np.asarray(ref_emb).reshape(-1).shape[0])
    return {"sim": cosine_similarity(ref_emb, hyp_emb), "embedding_dim": dim}
