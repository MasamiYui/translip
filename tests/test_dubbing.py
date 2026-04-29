import json
from pathlib import Path

import numpy as np
import soundfile as sf

from translip.dubbing.reference import prepare_reference_package, select_reference_candidates
from translip.dubbing.runner import synthesize_speaker
from translip.types import DubbingRequest


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


class RecordingBackend(FakeBackend):
    def __init__(self) -> None:
        self.segment_ids: list[str] = []
        self.target_texts: list[str] = []

    def synthesize(self, *, reference, segment, output_path):
        self.segment_ids.append(segment.segment_id)
        self.target_texts.append(segment.target_text)
        return super().synthesize(reference=reference, segment=segment, output_path=output_path)


def _write_audio(path: Path, duration_sec: float, *, sample_rate: int = 16_000, amplitude: float = 0.05) -> None:
    waveform = amplitude * np.ones(int(duration_sec * sample_rate), dtype=np.float32)
    sf.write(path, waveform, sample_rate)


def test_dubbing_request_defaults_to_moss_tts_nano_onnx() -> None:
    request = DubbingRequest(
        translation_path="translation.en.json",
        profiles_path="speaker_profiles.json",
    )
    assert request.backend == "moss-tts-nano-onnx"


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


def test_qwen_backend_uses_reusable_voice_clone_prompt(tmp_path: Path, monkeypatch) -> None:
    from translip.dubbing.backend import ReferencePackage, SynthSegmentInput
    from translip.dubbing.qwen_tts_backend import (
        QwenTTSBackend,
        _max_new_tokens_for,
    )

    class FakeModel:
        def __init__(self) -> None:
            self.prompt_calls = []
            self.generate_calls = []

        def create_voice_clone_prompt(self, **kwargs):
            self.prompt_calls.append(kwargs)
            return {"prompt": "cached"}

        def generate_voice_clone(self, **kwargs):
            self.generate_calls.append(kwargs)
            sample_rate = 24_000
            waveform = np.ones(int(0.9 * sample_rate), dtype=np.float32) * 0.05
            return [waveform], sample_rate

    fake_model = FakeModel()
    monkeypatch.setattr(
        "translip.dubbing.qwen_tts_backend._load_qwen_model",
        lambda *_args, **_kwargs: fake_model,
    )

    reference_path = tmp_path / "reference.wav"
    _write_audio(reference_path, 8.0)
    reference = ReferencePackage(
        speaker_id="spk_0000",
        profile_id="profile_0000",
        original_audio_path=reference_path,
        prepared_audio_path=reference_path,
        text="This is the reference transcript.",
        duration_sec=8.0,
        score=0.9,
        selection_reason="test",
    )
    segment = SynthSegmentInput(
        segment_id="seg-0001",
        speaker_id="spk_0000",
        target_lang="en",
        target_text="Hello from Dubai.",
        source_duration_sec=1.0,
        duration_budget_sec=1.1,
    )

    backend = QwenTTSBackend(requested_device="cpu")
    result = backend.synthesize(reference=reference, segment=segment, output_path=tmp_path / "out.wav")

    assert result.audio_path.exists()
    assert result.sample_rate == 24_000
    assert result.generated_duration_sec > 0
    assert fake_model.prompt_calls[0]["ref_audio"] == str(reference.prepared_audio_path)
    assert fake_model.prompt_calls[0]["ref_text"] == reference.text
    assert fake_model.generate_calls[0]["text"] == segment.target_text
    assert fake_model.generate_calls[0]["language"] == "English"
    assert fake_model.generate_calls[0]["voice_clone_prompt"] == {"prompt": "cached"}
    assert fake_model.generate_calls[0]["non_streaming_mode"] is True
    assert fake_model.generate_calls[0]["max_new_tokens"] == _max_new_tokens_for(segment)


def test_qwen_max_new_tokens_is_calibrated_to_12hz_audio_budget() -> None:
    from translip.dubbing.backend import SynthSegmentInput
    from translip.dubbing.qwen_tts_backend import _max_new_tokens_for

    short = SynthSegmentInput(
        segment_id="seg-short",
        speaker_id="spk_0000",
        target_lang="en",
        target_text="You are the Devil.",
        source_duration_sec=1.0,
        duration_budget_sec=1.48,
    )
    medium = SynthSegmentInput(
        segment_id="seg-medium",
        speaker_id="spk_0001",
        target_lang="en",
        target_text="Your father is a trouble officer.",
        source_duration_sec=4.41,
        duration_budget_sec=2.16,
    )
    long = SynthSegmentInput(
        segment_id="seg-long",
        speaker_id="spk_0001",
        target_lang="en",
        target_text="You are all in debt.",
        source_duration_sec=9.55,
        duration_budget_sec=1.82,
    )

    assert _max_new_tokens_for(short) == 22
    assert _max_new_tokens_for(medium) == 66
    assert _max_new_tokens_for(long) == 143


def test_moss_tts_nano_backend_invokes_onnx_cli_for_voice_clone(tmp_path: Path, monkeypatch) -> None:
    import subprocess

    from translip.dubbing.backend import ReferencePackage, SynthSegmentInput
    from translip.dubbing.moss_tts_nano_backend import MossTtsNanoOnnxBackend

    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        commands.append([str(part) for part in command])
        output_path = Path(command[command.index("--output") + 1])
        sample_rate = 48_000
        waveform = np.ones(int(0.75 * sample_rate), dtype=np.float32) * 0.04
        sf.write(output_path, waveform, sample_rate)
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr("translip.dubbing.moss_tts_nano_backend.subprocess.run", fake_run)
    monkeypatch.setenv("MOSS_TTS_NANO_CLI", "moss-tts-nano")
    monkeypatch.setenv("MOSS_TTS_NANO_MODEL_DIR", str(tmp_path / "moss-models"))

    reference_path = tmp_path / "reference.wav"
    _write_audio(reference_path, 8.0)
    reference = ReferencePackage(
        speaker_id="spk_0000",
        profile_id="profile_0000",
        original_audio_path=reference_path,
        prepared_audio_path=reference_path,
        text="This is the reference transcript.",
        duration_sec=8.0,
        score=0.9,
        selection_reason="test",
    )
    segment = SynthSegmentInput(
        segment_id="seg-0001",
        speaker_id="spk_0000",
        target_lang="en",
        target_text="Hello from Dubai.",
        source_duration_sec=1.0,
        duration_budget_sec=1.1,
    )

    backend = MossTtsNanoOnnxBackend(requested_device="mps")
    result = backend.synthesize(reference=reference, segment=segment, output_path=tmp_path / "out.wav")

    assert result.audio_path.exists()
    assert result.sample_rate == 48_000
    assert result.generated_duration_sec == 0.75
    assert backend.backend_name == "moss-tts-nano-onnx"
    assert backend.resolved_device == "cpu"
    assert backend.resolved_model == "OpenMOSS-Team/MOSS-TTS-Nano-100M-ONNX"
    assert result.backend_metadata["reference_score"] == 0.9
    assert commands == [
        [
            "moss-tts-nano",
            "generate",
            "--backend",
            "onnx",
            "--output",
            str(tmp_path / "out.wav"),
            "--text",
            "Hello from Dubai.",
            "--prompt-speech",
            str(reference.prepared_audio_path),
            "--onnx-model-dir",
            str(tmp_path / "moss-models"),
            "--cpu-threads",
            "4",
            "--max-new-frames",
            "375",
            "--voice-clone-max-text-tokens",
            "75",
            "--sample-mode",
            "fixed",
        ]
    ]


def test_moss_tts_nano_backend_uses_repo_local_cli_when_env_and_path_are_absent(tmp_path: Path, monkeypatch) -> None:
    from translip.dubbing import moss_tts_nano_backend
    from translip.dubbing.moss_tts_nano_backend import MossTtsNanoOnnxBackend

    local_cli = tmp_path / ".dev-runtime" / "moss-tts-nano-venv" / "bin" / "moss-tts-nano"
    local_cli.parent.mkdir(parents=True)
    local_cli.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.delenv("MOSS_TTS_NANO_CLI", raising=False)
    monkeypatch.setattr("translip.dubbing.moss_tts_nano_backend.shutil.which", lambda _name: None)
    monkeypatch.setattr(moss_tts_nano_backend, "_repo_root", lambda: tmp_path)

    backend = MossTtsNanoOnnxBackend(requested_device="auto")

    assert backend.cli_path == str(local_cli)


def test_build_backend_defaults_to_moss_tts_nano_onnx() -> None:
    from translip.dubbing.runner import _build_backend

    backend = _build_backend(
        DubbingRequest(
            translation_path="translation.en.json",
            profiles_path="speaker_profiles.json",
            device="auto",
        )
    )
    assert backend.backend_name == "moss-tts-nano-onnx"


def test_build_backend_returns_qwen_backend() -> None:
    from translip.dubbing.runner import _build_backend

    backend = _build_backend(
        DubbingRequest(
            translation_path="translation.en.json",
            profiles_path="speaker_profiles.json",
            backend="qwen3tts",
            device="cpu",
        )
    )
    assert backend.backend_name == "qwen3tts"


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
        "translip.dubbing.runner.evaluate_segment",
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


def test_synthesize_speaker_retries_second_reference_for_pathological_duration(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bad_reference = tmp_path / "reference_bad.wav"
    good_reference = tmp_path / "reference_good.wav"
    _write_audio(bad_reference, 9.0)
    _write_audio(good_reference, 8.5)
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
                        "duration": 0.9,
                        "target_text": "My bag.",
                        "duration_budget": {"estimated_target_sec": 0.8},
                        "qa_flags": ["condensed"],
                    }
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
                                "path": str(bad_reference),
                                "text": "这是第一段声音参考文本",
                                "duration": 9.0,
                                "rms": 0.05,
                            },
                            {
                                "path": str(good_reference),
                                "text": "这是第二段声音参考文本",
                                "duration": 8.5,
                                "rms": 0.05,
                            },
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    def fake_evaluate(**kwargs):
        is_second_reference = "ref-02" in str(kwargs["generated_audio_path"])
        return type(
            "Eval",
            (),
            {
                "speaker_similarity": 0.5 if is_second_reference else 0.3,
                "speaker_status": "passed" if is_second_reference else "review",
                "backread_text": "my bag",
                "text_similarity": 1.0,
                "intelligibility_status": "passed",
                "duration_ratio": 1.0 if is_second_reference else 7.0,
                "duration_status": "passed" if is_second_reference else "failed",
                "overall_status": "passed" if is_second_reference else "failed",
            },
        )()

    monkeypatch.setattr("translip.dubbing.runner.evaluate_segment", fake_evaluate)

    result = synthesize_speaker(
        DubbingRequest(
            translation_path=translation_path,
            profiles_path=profiles_path,
            output_dir=tmp_path / "output",
            speaker_id="spk_0000",
        ),
        backend_override=FakeBackend(),
    )

    report = json.loads(result.artifacts.report_path.read_text(encoding="utf-8"))
    segment = report["segments"][0]
    assert segment["overall_status"] == "passed"
    assert segment["duration_status"] == "passed"
    assert segment["attempt_count"] == 2
    assert segment["selected_attempt_index"] == 2
    assert segment["quality_retry_reasons"] == ["pathological_duration"]
    assert segment["reference_path"] == str(good_reference.resolve())
    assert segment["attempts"][0]["selected"] is False
    assert segment["attempts"][1]["selected"] is True


def test_synthesize_speaker_groups_short_context_as_dubbing_unit(
    tmp_path: Path,
    monkeypatch,
) -> None:
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
                        "end": 0.8,
                        "duration": 0.8,
                        "target_text": "Ne Zha.",
                        "dubbing_text": "Ne Zha.",
                        "duration_budget": {"estimated_target_sec": 0.7},
                        "qa_flags": ["too_short_source"],
                        "script_risk_flags": ["needs_dubbing_unit"],
                        "context_unit_id": "unit-0001",
                    },
                    {
                        "segment_id": "seg-0002",
                        "speaker_id": "spk_0000",
                        "speaker_label": "SPEAKER_00",
                        "start": 0.9,
                        "end": 2.0,
                        "duration": 1.1,
                        "target_text": "Come back.",
                        "dubbing_text": "Come back.",
                        "duration_budget": {"estimated_target_sec": 0.9},
                        "qa_flags": [],
                        "script_risk_flags": [],
                        "context_unit_id": "unit-0001",
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
        "translip.dubbing.runner.evaluate_segment",
        lambda **_: type(
            "Eval",
            (),
            {
                "speaker_similarity": 0.61,
                "speaker_status": "passed",
                "backread_text": "ne zha come back",
                "text_similarity": 0.96,
                "intelligibility_status": "passed",
                "duration_ratio": 1.0,
                "duration_status": "passed",
                "overall_status": "passed",
            },
        )(),
    )

    backend = RecordingBackend()
    result = synthesize_speaker(
        DubbingRequest(
            translation_path=translation_path,
            profiles_path=profiles_path,
            output_dir=tmp_path / "output",
            speaker_id="spk_0000",
        ),
        backend_override=backend,
    )

    report = json.loads(result.artifacts.report_path.read_text(encoding="utf-8"))
    assert backend.segment_ids == ["unit-0001"]
    assert backend.target_texts == ["Ne Zha. Come back."]
    assert [row["synthesis_mode"] for row in report["segments"]] == ["dubbing_unit", "dubbing_unit"]
    assert report["segments"][0]["dubbing_unit_segment_ids"] == ["seg-0001", "seg-0002"]
    assert Path(report["segments"][0]["audio_path"]).exists()
    assert Path(report["segments"][1]["audio_path"]).exists()


def test_synthesize_speaker_prefers_voice_bank_references(
    tmp_path: Path,
    monkeypatch,
) -> None:
    profile_reference = tmp_path / "profile_reference.wav"
    bank_reference = tmp_path / "bank_reference.wav"
    _write_audio(profile_reference, 9.0)
    _write_audio(bank_reference, 8.5)
    translation_path = tmp_path / "translation.en.json"
    profiles_path = tmp_path / "speaker_profiles.json"
    voice_bank_path = tmp_path / "voice_bank.en.json"
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
                        "target_text": "Hello.",
                        "dubbing_text": "Hello.",
                        "duration_budget": {"estimated_target_sec": 0.8},
                        "qa_flags": [],
                    }
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
                                "path": str(profile_reference),
                                "text": "这是普通参考文本",
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
    voice_bank_path.write_text(
        json.dumps(
            {
                "speakers": [
                    {
                        "speaker_id": "spk_0000",
                        "profile_id": "profile_0000",
                        "references": [
                            {
                                "reference_id": "bank-ref",
                                "type": "source_clip",
                                "audio_path": str(bank_reference),
                                "text": "这是更好的参考文本",
                                "duration_sec": 8.5,
                                "rms": 0.05,
                                "quality_score": 0.95,
                                "risk_flags": [],
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
        "translip.dubbing.runner.evaluate_segment",
        lambda **_: type(
            "Eval",
            (),
            {
                "speaker_similarity": 0.70,
                "speaker_status": "passed",
                "backread_text": "hello",
                "text_similarity": 1.0,
                "intelligibility_status": "passed",
                "duration_ratio": 1.0,
                "duration_status": "passed",
                "overall_status": "passed",
            },
        )(),
    )

    result = synthesize_speaker(
        DubbingRequest(
            translation_path=translation_path,
            profiles_path=profiles_path,
            voice_bank_path=voice_bank_path,
            output_dir=tmp_path / "output",
            speaker_id="spk_0000",
        ),
        backend_override=FakeBackend(),
    )

    report = json.loads(result.artifacts.report_path.read_text(encoding="utf-8"))
    assert report["segments"][0]["reference_path"] == str(bank_reference.resolve())
