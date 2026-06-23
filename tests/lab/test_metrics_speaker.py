"""Speaker-similarity metric: cosine math + injectable embedder + graceful degrade."""
from __future__ import annotations

import numpy as np

from translip_lab.metrics.speaker import cosine_similarity, speaker_similarity


def test_cosine_identical_orthogonal_opposite():
    a = np.array([1.0, 2.0, 3.0])
    assert abs(cosine_similarity(a, a) - 1.0) < 1e-9
    assert abs(cosine_similarity([1.0, 0.0], [0.0, 1.0])) < 1e-9
    assert abs(cosine_similarity([1.0, 0.0], [-1.0, 0.0]) + 1.0) < 1e-9


def test_cosine_length_mismatch_truncates():
    assert abs(cosine_similarity([1.0, 1.0, 9.0], [1.0, 1.0]) - 1.0) < 1e-9


def test_cosine_empty_is_zero():
    assert cosine_similarity([], []) == 0.0


def test_speaker_similarity_with_injected_embedder():
    table = {
        "a.wav": np.array([1.0, 0.0, 0.0]),
        "b.wav": np.array([2.0, 0.0, 0.0]),  # same direction as a → sim 1
        "c.wav": np.array([0.0, 1.0, 0.0]),  # orthogonal → sim 0
    }
    embed = lambda p: table[str(p)]  # noqa: E731
    same = speaker_similarity("a.wav", "b.wav", embed_fn=embed)
    diff = speaker_similarity("a.wav", "c.wav", embed_fn=embed)
    assert same["sim"] > 0.99 and same["embedding_dim"] == 3
    assert abs(diff["sim"]) < 1e-9
    assert same["sim"] > diff["sim"]


def test_speaker_similarity_degrades_to_none_on_embedder_error():
    def boom(_path):
        raise RuntimeError("no speechbrain")

    out = speaker_similarity("a.wav", "b.wav", embed_fn=boom)
    assert out["sim"] is None and "note" in out


def test_speaker_similarity_none_when_embedding_missing():
    out = speaker_similarity("a.wav", "b.wav", embed_fn=lambda _p: None)
    assert out["sim"] is None and "note" in out
