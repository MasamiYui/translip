from pathlib import Path

import numpy as np

from translip.speakers.profile import build_profiles_payload
from translip.speakers.reference import build_profile_drafts
from translip.speakers.registry import apply_registry_updates, load_registry, match_profiles
from translip.types import TranscriptionSegment


def _segments_for_label(label: str, starts: list[float]) -> list[TranscriptionSegment]:
    segments: list[TranscriptionSegment] = []
    for index, start in enumerate(starts, start=1):
        end = start + 2.0
        segments.append(
            TranscriptionSegment(
                segment_id=f"{label}-{index:04d}",
                start=start,
                end=end,
                text=f"text-{index}",
                speaker_label=label,
                language="zh",
                duration=2.0,
            )
        )
    return segments


def test_build_profile_drafts_merges_adjacent_segments() -> None:
    waveform = np.ones(16_000 * 20, dtype=np.float32)
    segments = _segments_for_label("SPEAKER_00", [0.0, 2.2, 5.5, 12.0])
    drafts = build_profile_drafts(segments, waveform=waveform, sample_rate=16_000)
    assert len(drafts) == 1
    assert drafts[0].profile_id == "profile_0000"
    assert len(drafts[0].reference_clips) >= 2
    assert drafts[0].reference_clips[0].duration >= 2.0


def test_match_profiles_prefers_highest_score() -> None:
    profiles_payload = {
        "profiles": [
            {
                "profile_id": "profile_0000",
                "prototype_embedding": [1.0, 0.0],
                "reference_clips": [],
            }
        ]
    }
    registry = {
        "version": 1,
        "backend": {"speaker_backend": "speechbrain-ecapa", "embedding_dim": 2},
        "speakers": [
            {
                "speaker_id": "spk_0000",
                "status": "confirmed",
                "prototype_embedding": [0.99, 0.01],
                "exemplar_embeddings": [],
            },
            {
                "speaker_id": "spk_0001",
                "status": "confirmed",
                "prototype_embedding": [0.0, 1.0],
                "exemplar_embeddings": [],
            },
        ],
    }
    matches = match_profiles(profiles_payload, registry, top_k=2)
    match = matches["matches"][0]
    assert match["top_k"][0]["speaker_id"] == "spk_0000"
    assert match["score"] > match["top_k"][1]["score"]


def test_apply_registry_updates_creates_new_speaker(tmp_path: Path) -> None:
    profiles_payload = {
        "profiles": [
            {
                "profile_id": "profile_0000",
                "source_label": "SPEAKER_00",
                "speaker_id": None,
                "status": "unmatched",
                "prototype_embedding": [1.0, 0.0],
                "reference_clips": [],
            }
        ]
    }
    matches_payload = {
        "matches": [
            {
                "profile_id": "profile_0000",
                "decision": "new_speaker",
                "matched_speaker_id": None,
                "score": 0.1,
                "top_k": [],
            }
        ]
    }
    registry = load_registry(None, backend_name="speechbrain-ecapa", embedding_dim=2)
    updated_profiles, updated_registry = apply_registry_updates(
        profiles_payload,
        matches_payload,
        registry,
        registry_root=tmp_path,
        update_registry=True,
    )
    assert updated_profiles["profiles"][0]["speaker_id"] == "spk_0000"
    assert updated_registry["speakers"][0]["speaker_id"] == "spk_0000"


def test_build_profiles_payload_contains_embeddings() -> None:
    waveform = np.ones(16_000 * 10, dtype=np.float32)
    segments = _segments_for_label("SPEAKER_00", [0.0, 2.5])
    drafts = build_profile_drafts(segments, waveform=waveform, sample_rate=16_000)
    drafts[0].reference_clips[0].embedding = np.asarray([1.0, 0.0], dtype=np.float32)
    payload = build_profiles_payload(
        drafts,
        backend={"speaker_backend": "speechbrain-ecapa", "speaker_device": "cpu", "embedding_dim": 2},
    )
    assert payload["profiles"][0]["prototype_embedding"] == [1.0, 0.0]


def test_match_profiles_uses_dynamic_thresholds() -> None:
    profiles_payload = {
        "profiles": [
            {"profile_id": "profile_0000", "prototype_embedding": [0.58, 0.0], "reference_clips": []},
            {"profile_id": "profile_0001", "prototype_embedding": [0.37, 0.0], "reference_clips": []},
        ]
    }
    registry = {
        "version": 1,
        "backend": {"speaker_backend": "speechbrain-ecapa", "embedding_dim": 2},
        "speakers": [
            {
                "speaker_id": "spk_0000",
                "status": "confirmed",
                "prototype_embedding": [1.0, 0.0],
                "exemplar_embeddings": [],
            },
            {
                "speaker_id": "spk_0001",
                "status": "confirmed",
                "prototype_embedding": [0.3, 0.0],
                "exemplar_embeddings": [],
            },
        ],
    }
    matches = match_profiles(profiles_payload, registry, top_k=2)["matches"]
    assert matches[0]["decision"] == "matched"
    assert matches[1]["decision"] == "review"
