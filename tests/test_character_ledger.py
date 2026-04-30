import json
from pathlib import Path

import numpy as np
import soundfile as sf

from translip.characters.ledger import CharacterLedgerRequest, build_character_ledger
from translip.quality.audio_signature import classify_pitch, voice_signature


def _write_tone(path: Path, *, frequency: float, duration_sec: float = 1.4, sample_rate: int = 16_000) -> None:
    sample_count = max(1, int(duration_sec * sample_rate))
    time_axis = np.arange(sample_count, dtype=np.float32) / float(sample_rate)
    waveform = (0.08 * np.sin(2 * np.pi * frequency * time_axis)).astype(np.float32)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, waveform, sample_rate)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_voice_signature_classifies_low_mid_high_pitch(tmp_path: Path) -> None:
    low = tmp_path / "low.wav"
    high = tmp_path / "high.wav"
    _write_tone(low, frequency=110.0)
    _write_tone(high, frequency=260.0)

    low_signature = voice_signature(low)
    high_signature = voice_signature(high)

    assert classify_pitch(low_signature.pitch_hz) == "low"
    assert classify_pitch(high_signature.pitch_hz) == "high"
    assert 95.0 <= float(low_signature.pitch_hz or 0.0) <= 125.0
    assert 240.0 <= float(high_signature.pitch_hz or 0.0) <= 280.0


def test_character_ledger_flags_generated_voice_pitch_drift(tmp_path: Path) -> None:
    reference = tmp_path / "reference_low.wav"
    generated_ok = tmp_path / "seg-0001.wav"
    generated_bad = tmp_path / "seg-0002.wav"
    _write_tone(reference, frequency=110.0, duration_sec=2.0)
    _write_tone(generated_ok, frequency=120.0, duration_sec=1.0)
    _write_tone(generated_bad, frequency=260.0, duration_sec=1.0)

    profiles_path = tmp_path / "speaker_profiles.json"
    report_path = tmp_path / "speaker_segments.en.json"
    _write_json(
        profiles_path,
        {
            "profiles": [
                {
                    "profile_id": "profile_0001",
                    "speaker_id": "spk_0001",
                    "source_label": "SPEAKER_01",
                    "reference_clips": [
                        {
                            "path": str(reference),
                            "text": "这是一段清晰的参考音频",
                            "duration": 2.0,
                            "rms": 0.08,
                        }
                    ],
                }
            ]
        },
    )
    _write_json(
        report_path,
        {
            "speaker_id": "spk_0001",
            "reference": {"path": str(reference)},
            "segments": [
                {
                    "segment_id": "seg-0001",
                    "speaker_id": "spk_0001",
                    "audio_path": str(generated_ok),
                    "speaker_status": "passed",
                    "overall_status": "passed",
                },
                {
                    "segment_id": "seg-0002",
                    "speaker_id": "spk_0001",
                    "audio_path": str(generated_bad),
                    "speaker_status": "failed",
                    "overall_status": "failed",
                },
            ],
        },
    )

    result = build_character_ledger(
        CharacterLedgerRequest(
            profiles_path=profiles_path,
            task_d_report_paths=[report_path],
            output_dir=tmp_path / "character-ledger",
            target_lang="en",
        )
    )

    payload = json.loads(result.artifacts.ledger_path.read_text(encoding="utf-8"))
    character = payload["characters"][0]
    assert character["character_id"] == "char_0001"
    assert character["voice_signature"]["pitch_class"] == "low"
    assert character["stats"]["voice_mismatch_count"] == 1
    assert "pitch_class_drift" in character["risk_flags"]
    assert character["review_status"] == "review"
    assert result.artifacts.report_path.exists()
    assert result.artifacts.manifest_path.exists()
