"""Unit tests for voice-bank Sprint 2 additions: min-clips floor + cross-speaker fallback."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import soundfile as sf

from translip.config import (
    DEFAULT_VOICE_BANK_MIN_REFERENCE_CLIPS,
)
from translip.dubbing.voice_bank import (
    VoiceBankRequest,
    apply_cross_speaker_fallback,
    build_voice_bank,
)


def _write_audio(
    path: Path,
    duration_sec: float,
    *,
    sample_rate: int = 16_000,
    amplitude: float = 0.05,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    waveform = np.ones(int(duration_sec * sample_rate), dtype=np.float32) * amplitude
    sf.write(path, waveform, sample_rate)


def test_needs_more_references_when_fewer_than_three_usable_clips(tmp_path: Path) -> None:
    """Speaker with only 1 usable source clip should be flagged for fallback."""

    clip_a = tmp_path / "clip_a.wav"
    _write_audio(clip_a, 9.0, amplitude=0.05)

    profiles_path = tmp_path / "speaker_profiles.json"
    profiles_path.write_text(
        json.dumps(
            {
                "profiles": [
                    {
                        "profile_id": "profile_0001",
                        "speaker_id": "spk_0001",
                        "source_label": "SPEAKER_01",
                        "segment_count": 1,
                        "total_speech_sec": 9.0,
                        "reference_clips": [
                            {
                                "path": str(clip_a),
                                "duration": 9.0,
                                "text": "一个清晰的参考音频片段",
                                "rms": 0.05,
                            }
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = build_voice_bank(
        VoiceBankRequest(
            profiles_path=profiles_path,
            output_dir=tmp_path / "voice-bank",
            include_composites=False,
        )
    )
    speaker = result.voice_bank["speakers"][0]
    assert speaker["bank_status"] == "needs_more_references"
    assert speaker["usable_source_reference_count"] == 1
    assert (
        speaker["min_reference_clip_requirement"]
        == DEFAULT_VOICE_BANK_MIN_REFERENCE_CLIPS
    )


def test_cross_speaker_fallback_borrows_from_best_donor(tmp_path: Path) -> None:
    """A spk with thin pool should receive cross-speaker_fallback from 'available' peer."""

    healthy_clips = [tmp_path / f"hc_{i}.wav" for i in range(3)]
    for clip in healthy_clips:
        _write_audio(clip, 9.0, amplitude=0.05)
    thin_clip = tmp_path / "thin.wav"
    _write_audio(thin_clip, 9.0, amplitude=0.05)

    profiles_path = tmp_path / "speaker_profiles.json"
    profiles_path.write_text(
        json.dumps(
            {
                "profiles": [
                    {
                        "profile_id": "profile_healthy",
                        "speaker_id": "spk_healthy",
                        "source_label": "SPEAKER_HEALTHY",
                        "segment_count": 20,
                        "total_speech_sec": 60.0,
                        "reference_clips": [
                            {
                                "path": str(clip),
                                "duration": 9.0,
                                "text": "一段清晰的参考音频",
                                "rms": 0.05,
                            }
                            for clip in healthy_clips
                        ],
                    },
                    {
                        "profile_id": "profile_thin",
                        "speaker_id": "spk_thin",
                        "source_label": "SPEAKER_THIN",
                        "segment_count": 1,
                        "total_speech_sec": 9.0,
                        "reference_clips": [
                            {
                                "path": str(thin_clip),
                                "duration": 9.0,
                                "text": "单独一段",
                                "rms": 0.05,
                            }
                        ],
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = build_voice_bank(
        VoiceBankRequest(
            profiles_path=profiles_path,
            output_dir=tmp_path / "voice-bank",
            include_composites=False,
        )
    )

    by_id = {
        speaker.get("speaker_id"): speaker
        for speaker in result.voice_bank["speakers"]
    }
    healthy = by_id["spk_healthy"]
    thin = by_id["spk_thin"]

    # Healthy donor must not pick up a fallback and must be "available".
    assert healthy["bank_status"] == "available"
    assert healthy["cross_speaker_fallback"] is None

    # Thin speaker flagged + fallback populated with donor's recommended ref.
    assert thin["bank_status"] == "needs_more_references"
    fallback = thin["cross_speaker_fallback"]
    assert fallback is not None
    assert fallback["donor_speaker_id"] == "spk_healthy"
    assert fallback["reference_id"] == healthy["recommended_reference_id"]
    assert fallback["reference_path"] == healthy["recommended_reference_path"]
    assert "bank_status=needs_more_references" in fallback["reason"]


def test_apply_cross_speaker_fallback_idempotent_without_donor() -> None:
    """If no speaker is 'available', the fallback is a no-op."""

    voice_bank = {
        "speakers": [
            {
                "speaker_id": "spk_a",
                "profile_id": "profile_a",
                "bank_status": "needs_more_references",
                "usable_source_reference_count": 1,
                "references": [],
                "cross_speaker_fallback": None,
            },
            {
                "speaker_id": "spk_b",
                "profile_id": "profile_b",
                "bank_status": "needs_more_references",
                "usable_source_reference_count": 0,
                "references": [],
                "cross_speaker_fallback": None,
            },
        ]
    }
    before = json.dumps(voice_bank, sort_keys=True)
    apply_cross_speaker_fallback(voice_bank)
    after = json.dumps(voice_bank, sort_keys=True)
    assert before == after


def test_apply_cross_speaker_fallback_skips_self() -> None:
    """A donor cannot be fallback for itself."""

    voice_bank = {
        "speakers": [
            {
                "speaker_id": "spk_only_available",
                "profile_id": "profile_0",
                "bank_status": "available",
                "usable_source_reference_count": 3,
                "recommended_reference_id": "ref-0",
                "recommended_reference_path": "/tmp/ref-0.wav",
                "references": [
                    {"reference_id": "ref-0", "quality_score": 0.9},
                ],
                "cross_speaker_fallback": None,
            },
        ]
    }
    apply_cross_speaker_fallback(voice_bank)
    # Single available speaker remains untouched.
    assert voice_bank["speakers"][0]["cross_speaker_fallback"] is None


def test_apply_cross_speaker_fallback_handles_missing_reference_status() -> None:
    """A speaker with no refs at all still deserves a fallback if donor exists."""

    voice_bank = {
        "speakers": [
            {
                "speaker_id": "spk_missing",
                "profile_id": "profile_m",
                "bank_status": "missing_reference",
                "usable_source_reference_count": 0,
                "references": [],
                "cross_speaker_fallback": None,
            },
            {
                "speaker_id": "spk_donor",
                "profile_id": "profile_d",
                "bank_status": "available",
                "usable_source_reference_count": 5,
                "recommended_reference_id": "ref-d",
                "recommended_reference_path": "/tmp/ref-d.wav",
                "references": [
                    {"reference_id": "ref-d", "quality_score": 0.85},
                ],
                "total_speech_sec": 40.0,
                "cross_speaker_fallback": None,
            },
        ]
    }
    apply_cross_speaker_fallback(voice_bank)
    missing = voice_bank["speakers"][0]
    assert missing["cross_speaker_fallback"] is not None
    assert missing["cross_speaker_fallback"]["donor_speaker_id"] == "spk_donor"
