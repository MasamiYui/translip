import json
from pathlib import Path

import numpy as np
import pytest
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


def test_dubbing_request_normalizes_quality_check_mode() -> None:
    request = DubbingRequest(
        translation_path="translation.en.json",
        profiles_path="speaker_profiles.json",
        quality_check_mode=" Duration-Only ",  # type: ignore[arg-type]
    )

    assert request.normalized().quality_check_mode == "duration-only"


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


def test_qwen_backend_supports_xvec_clone_mode(tmp_path: Path, monkeypatch) -> None:
    from translip.dubbing.backend import ReferencePackage, SynthSegmentInput
    from translip.dubbing.qwen_tts_backend import QwenTTSBackend

    class FakeModel:
        def __init__(self) -> None:
            self.prompt_calls = []

        def create_voice_clone_prompt(self, **kwargs):
            self.prompt_calls.append(kwargs)
            return {"prompt": "xvec"}

        def generate_voice_clone(self, **_kwargs):
            sample_rate = 24_000
            waveform = np.ones(int(0.8 * sample_rate), dtype=np.float32) * 0.05
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
        text="这是参考文本",
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

    backend = QwenTTSBackend(requested_device="cpu", clone_mode="xvec")
    result = backend.synthesize(reference=reference, segment=segment, output_path=tmp_path / "out.wav")

    assert result.audio_path.exists()
    assert backend.clone_mode == "xvec"
    assert result.backend_metadata["clone_mode"] == "xvec"
    assert fake_model.prompt_calls[0]["ref_text"] is None
    assert fake_model.prompt_calls[0]["x_vector_only_mode"] is True


def test_voxcpm_backend_uses_prompt_and_reference_clone_inputs(tmp_path: Path, monkeypatch) -> None:
    from translip.dubbing.backend import ReferencePackage, SynthSegmentInput
    from translip.dubbing.voxcpm_tts_backend import VoxCPMTTSBackend

    class FakeTtsModel:
        sample_rate = 48_000

    class FakeModel:
        def __init__(self) -> None:
            self.tts_model = FakeTtsModel()
            self.generate_calls = []

        def generate(self, **kwargs):
            self.generate_calls.append(kwargs)
            return np.ones(int(0.7 * self.tts_model.sample_rate), dtype=np.float32) * 0.05

    fake_model = FakeModel()
    monkeypatch.setattr(
        "translip.dubbing.voxcpm_tts_backend._load_voxcpm_model",
        lambda *_args, **_kwargs: fake_model,
    )

    reference_path = tmp_path / "reference.wav"
    _write_audio(reference_path, 8.0)
    reference = ReferencePackage(
        speaker_id="spk_0000",
        profile_id="profile_0000",
        original_audio_path=reference_path,
        prepared_audio_path=reference_path,
        text="This is the exact reference transcript.",
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

    backend = VoxCPMTTSBackend(requested_device="cpu")
    result = backend.synthesize(reference=reference, segment=segment, output_path=tmp_path / "out.wav")

    assert result.audio_path.exists()
    assert result.sample_rate == 48_000
    assert result.generated_duration_sec == 0.7
    assert backend.backend_name == "voxcpm2"
    assert backend.resolved_model == "openbmb/VoxCPM2"
    assert backend.resolved_device == "cpu"
    assert backend.optimize is False
    assert fake_model.generate_calls == [
        {
            "text": "Hello from Dubai.",
            "prompt_wav_path": str(reference.prepared_audio_path),
            "prompt_text": reference.text,
            "reference_wav_path": str(reference.prepared_audio_path),
            "cfg_value": 2.0,
            "inference_timesteps": 10,
            "normalize": True,
            "denoise": False,
            "retry_badcase": True,
            "retry_badcase_max_times": 3,
        }
    ]
    assert result.backend_metadata["reference_score"] == 0.9
    assert result.backend_metadata["clone_mode"] == "ultimate"


def test_voxcpm_backend_forces_cpu_when_mps_is_not_explicitly_allowed(monkeypatch) -> None:
    from translip.dubbing.voxcpm_tts_backend import VoxCPMTTSBackend

    monkeypatch.setattr(
        "translip.dubbing.voxcpm_tts_backend.resolve_tts_device",
        lambda _requested: "mps",
    )
    monkeypatch.delenv("VOXCPM_ALLOW_MPS", raising=False)

    backend = VoxCPMTTSBackend(requested_device="mps")

    assert backend.requested_device == "mps"
    assert backend.resolved_device == "cpu"
    assert backend.backend_metadata_device_reason == "mps_disabled_for_voxcpm2"


def test_voxcpm_backend_can_disable_internal_badcase_retry(tmp_path: Path, monkeypatch) -> None:
    from translip.dubbing.backend import ReferencePackage, SynthSegmentInput
    from translip.dubbing.voxcpm_tts_backend import VoxCPMTTSBackend

    monkeypatch.setenv("VOXCPM_RETRY_BADCASE", "0")
    reference_path = tmp_path / "reference.wav"
    _write_audio(reference_path, 8.0)
    reference = ReferencePackage(
        speaker_id="spk_0000",
        profile_id="profile_0000",
        original_audio_path=reference_path,
        prepared_audio_path=reference_path,
        text="Reference transcript.",
        duration_sec=8.0,
        score=0.9,
        selection_reason="test",
    )
    segment = SynthSegmentInput(
        segment_id="seg-0001",
        speaker_id="spk_0000",
        target_lang="en",
        target_text="Hello.",
        source_duration_sec=1.0,
        duration_budget_sec=1.0,
    )

    backend = VoxCPMTTSBackend(requested_device="cpu")
    kwargs, _clone_mode = backend._generate_kwargs(reference=reference, segment=segment)

    assert kwargs["retry_badcase"] is False


def test_voxcpm_model_loader_prefers_local_cache(monkeypatch) -> None:
    from translip.dubbing import voxcpm_tts_backend

    calls = []
    model = object()

    class FakeVoxCPM:
        @classmethod
        def from_pretrained(cls, model_name, **kwargs):
            calls.append((model_name, kwargs))
            return model

    monkeypatch.setattr(voxcpm_tts_backend, "_load_voxcpm_package", lambda: FakeVoxCPM)
    monkeypatch.delenv("VOXCPM_PREFER_LOCAL_FILES", raising=False)
    monkeypatch.delenv("VOXCPM_ALLOW_DOWNLOAD", raising=False)
    voxcpm_tts_backend._load_voxcpm_model.cache_clear()

    try:
        result = voxcpm_tts_backend._load_voxcpm_model("openbmb/VoxCPM2", "cpu", False, False)
    finally:
        voxcpm_tts_backend._load_voxcpm_model.cache_clear()

    assert result is model
    assert calls == [
        (
            "openbmb/VoxCPM2",
            {
                "device": "cpu",
                "optimize": False,
                "load_denoiser": False,
                "local_files_only": True,
            },
        )
    ]


def test_voxcpm_model_loader_falls_back_to_download_when_cache_missing(monkeypatch) -> None:
    from translip.dubbing import voxcpm_tts_backend

    calls = []
    model = object()

    class FakeVoxCPM:
        @classmethod
        def from_pretrained(cls, model_name, **kwargs):
            calls.append((model_name, kwargs))
            if kwargs["local_files_only"]:
                raise RuntimeError("cache miss")
            return model

    monkeypatch.setattr(voxcpm_tts_backend, "_load_voxcpm_package", lambda: FakeVoxCPM)
    monkeypatch.delenv("VOXCPM_PREFER_LOCAL_FILES", raising=False)
    monkeypatch.delenv("VOXCPM_ALLOW_DOWNLOAD", raising=False)
    voxcpm_tts_backend._load_voxcpm_model.cache_clear()

    try:
        result = voxcpm_tts_backend._load_voxcpm_model("openbmb/VoxCPM2", "cpu", False, False)
    finally:
        voxcpm_tts_backend._load_voxcpm_model.cache_clear()

    assert result is model
    assert [call[1]["local_files_only"] for call in calls] == [True, False]


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
    monkeypatch.setenv("MOSS_TTS_NANO_PERSISTENT", "0")  # exercise the legacy one-shot path

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


def test_build_backend_returns_voxcpm_backend() -> None:
    from translip.dubbing.runner import _build_backend

    backend = _build_backend(
        DubbingRequest(
            translation_path="translation.en.json",
            profiles_path="speaker_profiles.json",
            backend="voxcpm2",
            device="cpu",
        )
    )
    assert backend.backend_name == "voxcpm2"


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


def test_synthesize_speaker_duration_only_quality_check_skips_backread(
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
                        "duration": 1.0,
                        "target_text": "Hello.",
                        "duration_budget": {"estimated_target_sec": 1.0},
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

    def fail_evaluate(**_):
        raise AssertionError("standard quality checks should be skipped")

    monkeypatch.setattr("translip.dubbing.runner.evaluate_segment", fail_evaluate)

    result = synthesize_speaker(
        DubbingRequest(
            translation_path=translation_path,
            profiles_path=profiles_path,
            output_dir=tmp_path / "output",
            speaker_id="spk_0000",
            quality_check_mode="duration-only",
        ),
        backend_override=FakeBackend(),
    )

    report = json.loads(result.artifacts.report_path.read_text(encoding="utf-8"))
    manifest = json.loads(result.artifacts.manifest_path.read_text(encoding="utf-8"))
    row = report["segments"][0]
    assert row["quality_check_mode"] == "duration-only"
    assert row["speaker_status"] == "review"
    assert row["intelligibility_status"] == "review"
    assert manifest["request"]["quality_check_mode"] == "duration-only"
    assert manifest["resolved"]["quality_check_mode"] == "duration-only"


def test_synthesize_speaker_duration_only_fails_near_silent_audio(tmp_path: Path) -> None:
    class QuietBackend(FakeBackend):
        def synthesize(self, *, reference, segment, output_path):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            sample_rate = 24_000
            waveform = np.zeros(int(segment.source_duration_sec * sample_rate), dtype=np.float32)
            sf.write(output_path, waveform, sample_rate)
            return type(
                "SynthOutput",
                (),
                {
                    "segment_id": segment.segment_id,
                    "audio_path": output_path,
                    "sample_rate": sample_rate,
                    "generated_duration_sec": segment.source_duration_sec,
                    "backend_metadata": {},
                },
            )()

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
                        "target_text": "Hello.",
                        "duration_budget": {"estimated_target_sec": 1.0},
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

    result = synthesize_speaker(
        DubbingRequest(
            translation_path=translation_path,
            profiles_path=profiles_path,
            output_dir=tmp_path / "output",
            speaker_id="spk_0000",
            quality_check_mode="duration-only",
        ),
        backend_override=QuietBackend(),
    )

    report = json.loads(result.artifacts.report_path.read_text(encoding="utf-8"))
    row = report["segments"][0]
    assert row["duration_status"] == "passed"
    assert row["intelligibility_status"] == "failed"
    assert row["overall_status"] == "failed"
    assert row["quality_retry_reasons"] == ["silent_audio"]


def test_synthesize_speaker_retries_silent_audio_with_same_reference(tmp_path: Path) -> None:
    class FirstSilentBackend(FakeBackend):
        def __init__(self) -> None:
            self.calls = 0

        def synthesize(self, *, reference, segment, output_path):
            self.calls += 1
            output_path.parent.mkdir(parents=True, exist_ok=True)
            sample_rate = 24_000
            if self.calls == 1:
                waveform = np.zeros(int(segment.source_duration_sec * sample_rate), dtype=np.float32)
            else:
                waveform = 0.05 * np.sin(
                    np.linspace(0, np.pi * 8, int(segment.source_duration_sec * sample_rate), dtype=np.float32)
                )
            sf.write(output_path, waveform, sample_rate)
            return type(
                "SynthOutput",
                (),
                {
                    "segment_id": segment.segment_id,
                    "audio_path": output_path,
                    "sample_rate": sample_rate,
                    "generated_duration_sec": segment.source_duration_sec,
                    "backend_metadata": {},
                },
            )()

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
                        "target_text": "Hello.",
                        "duration_budget": {"estimated_target_sec": 1.0},
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
    backend = FirstSilentBackend()

    result = synthesize_speaker(
        DubbingRequest(
            translation_path=translation_path,
            profiles_path=profiles_path,
            output_dir=tmp_path / "output",
            speaker_id="spk_0000",
            quality_check_mode="duration-only",
        ),
        backend_override=backend,
    )

    report = json.loads(result.artifacts.report_path.read_text(encoding="utf-8"))
    row = report["segments"][0]
    assert backend.calls == 2
    assert row["attempt_count"] == 2
    assert row["selected_attempt_index"] == 2
    assert row["overall_status"] == "review"
    assert row["quality_retry_reasons"] == ["silent_audio"]


def test_synthesize_speaker_prefers_audible_retry_over_silent_duration_match(tmp_path: Path) -> None:
    class SilentThenLongBackend(FakeBackend):
        def __init__(self) -> None:
            self.calls = 0

        def synthesize(self, *, reference, segment, output_path):
            self.calls += 1
            output_path.parent.mkdir(parents=True, exist_ok=True)
            sample_rate = 24_000
            if self.calls == 1:
                duration_sec = 0.8
                waveform = np.zeros(int(duration_sec * sample_rate), dtype=np.float32)
            else:
                duration_sec = 2.7
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
                        "duration": 1.4,
                        "target_text": "The thief is the detective.",
                        "duration_budget": {"estimated_target_sec": 1.4},
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
    backend = SilentThenLongBackend()

    result = synthesize_speaker(
        DubbingRequest(
            translation_path=translation_path,
            profiles_path=profiles_path,
            output_dir=tmp_path / "output",
            speaker_id="spk_0000",
            quality_check_mode="duration-only",
        ),
        backend_override=backend,
    )

    report = json.loads(result.artifacts.report_path.read_text(encoding="utf-8"))
    row = report["segments"][0]
    assert backend.calls == 2
    assert row["attempt_count"] == 2
    assert row["selected_attempt_index"] == 2
    assert row["duration_status"] == "failed"
    assert row["intelligibility_status"] == "review"
    assert row["quality_retry_reasons"] == ["silent_audio"]
    assert row["attempts"][0]["quality_flags"] == ["silent_audio"]
    assert row["attempts"][1]["quality_flags"] == []


def test_synthesize_speaker_marks_silent_dubbing_unit_piece_failed(tmp_path: Path) -> None:
    class UnitWithSilentMiddleBackend(FakeBackend):
        def synthesize(self, *, reference, segment, output_path):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            sample_rate = 24_000
            audible = 0.05 * np.sin(np.linspace(0, np.pi * 12, sample_rate, dtype=np.float32))
            silence = np.zeros(sample_rate, dtype=np.float32)
            waveform = np.concatenate([audible, silence, audible])
            sf.write(output_path, waveform, sample_rate)
            return type(
                "SynthOutput",
                (),
                {
                    "segment_id": segment.segment_id,
                    "audio_path": output_path,
                    "sample_rate": sample_rate,
                    "generated_duration_sec": 3.0,
                    "backend_metadata": {},
                },
            )()

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
                        "end": 1.0,
                        "duration": 1.0,
                        "target_text": "First.",
                        "context_unit_id": "unit-a",
                        "duration_budget": {"estimated_target_sec": 1.0},
                        "qa_flags": ["too_short_source"],
                    },
                    {
                        "segment_id": "seg-0002",
                        "speaker_id": "spk_0000",
                        "speaker_label": "SPEAKER_00",
                        "start": 1.0,
                        "end": 2.0,
                        "duration": 1.0,
                        "target_text": "Second.",
                        "context_unit_id": "unit-a",
                        "duration_budget": {"estimated_target_sec": 1.0},
                        "qa_flags": [],
                    },
                    {
                        "segment_id": "seg-0003",
                        "speaker_id": "spk_0000",
                        "speaker_label": "SPEAKER_00",
                        "start": 2.0,
                        "end": 3.0,
                        "duration": 1.0,
                        "target_text": "Third.",
                        "context_unit_id": "unit-a",
                        "duration_budget": {"estimated_target_sec": 1.0},
                        "qa_flags": [],
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

    result = synthesize_speaker(
        DubbingRequest(
            translation_path=translation_path,
            profiles_path=profiles_path,
            output_dir=tmp_path / "output",
            speaker_id="spk_0000",
            quality_check_mode="duration-only",
        ),
        backend_override=UnitWithSilentMiddleBackend(),
    )

    report = json.loads(result.artifacts.report_path.read_text(encoding="utf-8"))
    rows = {row["segment_id"]: row for row in report["segments"]}
    assert rows["seg-0001"]["overall_status"] == "review"
    assert rows["seg-0002"]["overall_status"] == "failed"
    assert rows["seg-0002"]["intelligibility_status"] == "failed"
    assert rows["seg-0002"]["quality_flags"] == ["silent_audio"]
    assert rows["seg-0002"]["quality_retry_reasons"] == ["silent_audio"]
    assert rows["seg-0003"]["overall_status"] == "review"


def test_synthesize_speaker_retries_voxcpm_silent_audio_with_next_reference(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class VoxSilentThenGoodBackend(FakeBackend):
        backend_name = "voxcpm2"
        resolved_model = "openbmb/VoxCPM2"

        def synthesize(self, *, reference, segment, output_path):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            sample_rate = 24_000
            if reference.original_audio_path.name == "reference_bad.wav":
                waveform = np.zeros(int(segment.source_duration_sec * sample_rate), dtype=np.float32)
            else:
                waveform = 0.05 * np.sin(
                    np.linspace(0, np.pi * 8, int(segment.source_duration_sec * sample_rate), dtype=np.float32)
                )
            sf.write(output_path, waveform, sample_rate)
            return type(
                "SynthOutput",
                (),
                {
                    "segment_id": segment.segment_id,
                    "audio_path": output_path,
                    "sample_rate": sample_rate,
                    "generated_duration_sec": segment.source_duration_sec,
                    "backend_metadata": {},
                },
            )()

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
                        "duration": 1.0,
                        "target_text": "Hello.",
                        "duration_budget": {"estimated_target_sec": 1.0},
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
    monkeypatch.delenv("VOXCPM_REFERENCE_RETRY", raising=False)

    result = synthesize_speaker(
        DubbingRequest(
            translation_path=translation_path,
            profiles_path=profiles_path,
            output_dir=tmp_path / "output",
            speaker_id="spk_0000",
            quality_check_mode="duration-only",
        ),
        backend_override=VoxSilentThenGoodBackend(),
    )

    report = json.loads(result.artifacts.report_path.read_text(encoding="utf-8"))
    row = report["segments"][0]
    assert row["attempt_count"] == 4
    assert row["selected_attempt_index"] == 4
    assert row["reference_path"] == str(good_reference.resolve())
    assert row["overall_status"] == "review"
    assert row["quality_retry_reasons"] == ["silent_audio"]


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


def test_synthesize_speaker_limits_voxcpm_reference_retry_by_default(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class VoxFakeBackend(FakeBackend):
        backend_name = "voxcpm2"
        resolved_model = "openbmb/VoxCPM2"

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

    def fake_evaluate(**_kwargs):
        return type(
            "Eval",
            (),
            {
                "speaker_similarity": 0.3,
                "speaker_status": "review",
                "backread_text": "my bag",
                "text_similarity": 1.0,
                "intelligibility_status": "passed",
                "duration_ratio": 7.0,
                "duration_status": "failed",
                "overall_status": "failed",
            },
        )()

    monkeypatch.setattr("translip.dubbing.runner.evaluate_segment", fake_evaluate)
    monkeypatch.delenv("VOXCPM_REFERENCE_RETRY", raising=False)

    result = synthesize_speaker(
        DubbingRequest(
            translation_path=translation_path,
            profiles_path=profiles_path,
            output_dir=tmp_path / "output",
            speaker_id="spk_0000",
        ),
        backend_override=VoxFakeBackend(),
    )

    report = json.loads(result.artifacts.report_path.read_text(encoding="utf-8"))
    segment = report["segments"][0]
    assert segment["attempt_count"] == 1
    assert segment["selected_attempt_index"] == 1
    assert segment["quality_retry_reasons"] == ["pathological_duration"]
    assert segment["reference_path"] == str(bad_reference.resolve())


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


class _FakeWorker:
    """Stand-in for a persistent MOSS worker subprocess used in unit tests."""

    def __init__(self, *, on_request=None) -> None:
        self.requests: list[dict] = []
        self.closed = False
        self.ready = False
        self._on_request = on_request

    def wait_ready(self) -> None:
        self.ready = True

    def request(self, payload: dict) -> dict:
        self.requests.append(payload)
        if self._on_request is not None:
            return self._on_request(self, payload)
        sample_rate = 48_000
        waveform = np.ones(int(0.6 * sample_rate), dtype=np.float32) * 0.04
        sf.write(payload["output"], waveform, sample_rate)
        return {"id": payload["id"], "ok": True, "audio_path": payload["output"], "sample_rate": sample_rate}

    def close(self) -> None:
        self.closed = True


def _moss_reference_and_segment(tmp_path: Path):
    from translip.dubbing.backend import ReferencePackage, SynthSegmentInput

    reference_path = tmp_path / "reference.wav"
    _write_audio(reference_path, 8.0)
    reference = ReferencePackage(
        speaker_id="spk_0000",
        profile_id="profile_0000",
        original_audio_path=reference_path,
        prepared_audio_path=reference_path,
        text="Reference transcript.",
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
    return reference, segment


def test_moss_persistent_reuses_single_worker_across_segments(tmp_path: Path, monkeypatch) -> None:
    from translip.dubbing.moss_tts_nano_backend import MossTtsNanoOnnxBackend

    monkeypatch.delenv("MOSS_TTS_NANO_PERSISTENT", raising=False)
    reference, segment = _moss_reference_and_segment(tmp_path)

    spawned: list[_FakeWorker] = []

    def fake_spawn(self):
        worker = _FakeWorker()
        spawned.append(worker)
        return worker

    monkeypatch.setattr(MossTtsNanoOnnxBackend, "_spawn_worker", fake_spawn)

    backend = MossTtsNanoOnnxBackend(requested_device="cpu", worker_count_hint=1)
    assert backend.persistent is True

    first = backend.synthesize(reference=reference, segment=segment, output_path=tmp_path / "a.wav")
    second = backend.synthesize(reference=reference, segment=segment, output_path=tmp_path / "b.wav")

    assert first.audio_path.exists() and second.audio_path.exists()
    assert first.sample_rate == 48_000
    assert first.backend_metadata["persistent"] is True
    # The model is loaded once: a single worker serves both segments.
    assert len(spawned) == 1
    assert spawned[0].requests[0]["text"] == "Hello from Dubai."
    assert spawned[0].requests[0]["prompt_speech"] == str(reference.prepared_audio_path)

    backend.close()
    assert spawned[0].closed is True


def test_moss_persistent_raises_on_error_ack(tmp_path: Path, monkeypatch) -> None:
    from translip.dubbing.moss_tts_nano_backend import MossTtsNanoOnnxBackend

    monkeypatch.delenv("MOSS_TTS_NANO_PERSISTENT", raising=False)
    reference, segment = _moss_reference_and_segment(tmp_path)

    def erroring(worker, payload):
        return {"id": payload["id"], "ok": False, "error": "boom"}

    monkeypatch.setattr(
        MossTtsNanoOnnxBackend,
        "_spawn_worker",
        lambda self: _FakeWorker(on_request=erroring),
    )

    backend = MossTtsNanoOnnxBackend(requested_device="cpu", worker_count_hint=1)
    with pytest.raises(RuntimeError, match="boom"):
        backend.synthesize(reference=reference, segment=segment, output_path=tmp_path / "a.wav")
    backend.close()


def test_moss_persistent_respawns_after_worker_death(tmp_path: Path, monkeypatch) -> None:
    from translip.dubbing.moss_tts_nano_backend import MossTtsNanoOnnxBackend, _WorkerDied

    monkeypatch.delenv("MOSS_TTS_NANO_PERSISTENT", raising=False)
    reference, segment = _moss_reference_and_segment(tmp_path)

    spawned: list[_FakeWorker] = []

    def dying(worker, payload):
        raise _WorkerDied("pipe broke")

    def fake_spawn(self):
        # First worker dies on use; replacement behaves normally.
        worker = _FakeWorker(on_request=dying if not spawned else None)
        spawned.append(worker)
        return worker

    monkeypatch.setattr(MossTtsNanoOnnxBackend, "_spawn_worker", fake_spawn)

    backend = MossTtsNanoOnnxBackend(requested_device="cpu", worker_count_hint=1)
    with pytest.raises(RuntimeError, match="died"):
        backend.synthesize(reference=reference, segment=segment, output_path=tmp_path / "a.wav")

    # The dead worker was closed and replaced, so the pool keeps serving.
    assert len(spawned) == 2
    assert spawned[0].closed is True
    result = backend.synthesize(reference=reference, segment=segment, output_path=tmp_path / "b.wav")
    assert result.audio_path.exists()
    backend.close()
