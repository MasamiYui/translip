import json
from pathlib import Path

import numpy as np
import soundfile as sf

from video_voice_separate.dubbing.reference import prepare_reference_package, select_reference_candidates
from video_voice_separate.dubbing.runner import synthesize_speaker
from video_voice_separate.types import DubbingRequest


class FakeBackend:
    backend_name = "fake-tts"
    resolved_model = "fake-model"
    resolved_device = "cpu"

    def synthesize(self, *, reference, segment, output_path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        duration_sec = max(0.6, min(segment.source_duration_sec, 1.2))
        sample_rate = 24_000
        waveform = 0.05 * np.sin(
            np.linspace(0, np.pi * 8, int(duration_sec * sample_rate), dtype=np.float32)
        )
        sf.write(output_path, waveform, sample_rate)
        return type(
            "SynthOutput",
            (),
            {
                "segment_id": segment.segment_id,
                "audio_path": output_path,
                "sample_rate": sample_rate,
                "generated_duration_sec": duration_sec,
                "backend_metadata": {},
            },
        )()


def _write_audio(path: Path, duration_sec: float, *, sample_rate: int = 16_000, amplitude: float = 0.05) -> None:
    waveform = amplitude * np.ones(int(duration_sec * sample_rate), dtype=np.float32)
    sf.write(path, waveform, sample_rate)


def test_select_reference_candidates_prefers_ideal_duration(tmp_path: Path) -> None:
    clip_short = tmp_path / "clip-short.wav"
    clip_ideal = tmp_path / "clip-ideal.wav"
    _write_audio(clip_short, 5.5)
    _write_audio(clip_ideal, 9.5)
    profiles_payload = {
        "profiles": [
            {
                "profile_id": "profile_0000",
                "speaker_id": "spk_0000",
                "reference_clips": [
                    {
                        "path": str(clip_short),
                        "text": "短一点的参考音频",
                        "duration": 5.5,
                        "rms": 0.05,
                    },
                    {
                        "path": str(clip_ideal),
                        "text": "这是更适合作为声音克隆参考的音频片段",
                        "duration": 9.5,
                        "rms": 0.05,
                    },
                ],
            }
        ]
    }
    candidates = select_reference_candidates(profiles_payload=profiles_payload, speaker_id="spk_0000")
    assert candidates[0].path == clip_ideal.resolve()
    assert candidates[0].score > candidates[1].score


def test_prepare_reference_package_adds_tail_silence(tmp_path: Path) -> None:
    clip = tmp_path / "clip.wav"
    _write_audio(clip, 6.0)
    profiles_payload = {
        "profiles": [
            {
                "profile_id": "profile_0000",
                "speaker_id": "spk_0000",
                "reference_clips": [
                    {
                        "path": str(clip),
                        "text": "这是参考文本",
                        "duration": 6.0,
                        "rms": 0.05,
                    }
                ],
            }
        ]
    }
    candidate = select_reference_candidates(profiles_payload=profiles_payload, speaker_id="spk_0000")[0]
    package = prepare_reference_package(candidate, output_path=tmp_path / "prepared.wav")
    assert package.prepared_audio_path.exists()
    assert package.duration_sec > candidate.duration_sec


def test_synthesize_speaker_writes_report_and_manifest(tmp_path: Path, monkeypatch) -> None:
    reference_clip = tmp_path / "reference.wav"
    _write_audio(reference_clip, 9.0)
    translation_path = tmp_path / "translation.en.json"
    profiles_path = tmp_path / "speaker_profiles.json"
    translation_path.write_text(
        json.dumps(
            {
                "backend": {"target_lang": "en", "output_tag": "en"},
                "segments": [
                    {
                        "segment_id": "seg-0001",
                        "speaker_id": "spk_0000",
                        "speaker_label": "SPEAKER_00",
                        "start": 0.0,
                        "duration": 1.0,
                        "target_text": "Hello Dubai",
                        "duration_budget": {"estimated_target_sec": 1.1},
                        "qa_flags": [],
                    },
                    {
                        "segment_id": "seg-0002",
                        "speaker_id": "spk_0000",
                        "speaker_label": "SPEAKER_00",
                        "start": 1.1,
                        "duration": 1.2,
                        "target_text": "Welcome back",
                        "duration_budget": {"estimated_target_sec": 1.0},
                        "qa_flags": ["duration_review"],
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    profiles_path.write_text(
        json.dumps(
            {
                "profiles": [
                    {
                        "profile_id": "profile_0000",
                        "speaker_id": "spk_0000",
                        "reference_clips": [
                            {
                                "path": str(reference_clip),
                                "text": "这是声音参考文本",
                                "duration": 9.0,
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

    monkeypatch.setattr(
        "video_voice_separate.dubbing.runner.evaluate_segment",
        lambda **_: type(
            "Eval",
            (),
            {
                "speaker_similarity": 0.61,
                "speaker_status": "passed",
                "backread_text": "hello dubai",
                "text_similarity": 0.96,
                "intelligibility_status": "passed",
                "duration_ratio": 1.02,
                "duration_status": "passed",
                "overall_status": "passed",
            },
        )(),
    )

    result = synthesize_speaker(
        DubbingRequest(
            translation_path=translation_path,
            profiles_path=profiles_path,
            output_dir=tmp_path / "output",
            speaker_id="spk_0000",
            keep_intermediate=True,
        ),
        backend_override=FakeBackend(),
    )

    report = json.loads(result.artifacts.report_path.read_text(encoding="utf-8"))
    manifest = json.loads(result.artifacts.manifest_path.read_text(encoding="utf-8"))
    assert result.artifacts.demo_audio_path is not None
    assert result.artifacts.demo_audio_path.exists()
    assert report["backend"]["tts_backend"] == "fake-tts"
    assert report["segments"][0]["segment_id"] == "seg-0001"
    assert report["segments"][1]["overall_status"] == "passed"
    assert manifest["status"] == "succeeded"
    assert manifest["resolved"]["selected_segment_count"] == 2
