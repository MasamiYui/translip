from __future__ import annotations

import contextlib
import json
import wave
from functools import lru_cache
from pathlib import Path

import numpy as np
import soundfile as sf

from ....dubbing.backend import ReferencePackage, SynthSegmentInput, resolve_tts_device
from ....dubbing.qwen_tts_backend import (
    _language_name,
    _load_qwen_model,
    _max_new_tokens_for,
    _normalize_waveform,
)
from ....dubbing.registry import TTS_BACKENDS
from ..registry import ToolSpec, register_tool
from ..schemas import TtsToolRequest
from . import ToolAdapter


class TtsAdapter(ToolAdapter):
    def validate_params(self, params: dict) -> dict:
        return TtsToolRequest(**params).model_dump()

    def run(self, params, input_dir, output_dir, on_progress):
        reference_audio_path = (
            self.first_input(input_dir, "reference_audio_file")
            if params.get("reference_audio_file_id")
            else None
        )
        output_path = output_dir / "speech.wav"
        on_progress(10.0, "synthesizing")
        metadata = generate_speech(
            text=params["text"],
            language=params.get("language", "auto"),
            backend=params.get("backend", "qwen3tts"),
            reference_audio_path=reference_audio_path,
            output_path=output_path,
        )
        report_path = output_dir / "speech.json"
        self.write_json(
            report_path,
            {
                "text": params["text"],
                "language": params.get("language", "auto"),
                **{key: value for key, value in metadata.items() if key != "output_path"},
            },
        )
        on_progress(95.0, "finalizing")
        return {
            "speech_file": output_path.name,
            "report_file": report_path.name,
            "duration_sec": metadata["duration_sec"],
            "sample_rate": metadata["sample_rate"],
            "mode": metadata["mode"],
            "backend": metadata["backend"],
            "reference_used": metadata["reference_used"],
        }


def generate_speech(
    *,
    text: str,
    language: str,
    backend: str,
    reference_audio_path: Path | None,
    output_path: Path,
) -> dict[str, object]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if backend == "qwen3tts":
        if reference_audio_path is not None:
            waveform, sample_rate = _generate_voice_clone(
                text=text,
                language=language,
                reference_audio_path=reference_audio_path,
            )
            mode = "voice_clone"
        else:
            waveform, sample_rate = _generate_voice_design(text=text, language=language)
            mode = "designed"
        sf.write(output_path, waveform, sample_rate)
        duration_sec = round(float(len(waveform) / sample_rate), 3)
    elif backend in {"moss-tts-nano-onnx", "voxcpm2"}:
        if reference_audio_path is None:
            raise ValueError(f"The {backend} backend requires a reference audio upload.")
        sample_rate, duration_sec = _generate_via_protocol_backend(
            backend=backend,
            text=text,
            language=language,
            reference_audio_path=reference_audio_path,
            output_path=output_path,
        )
        mode = "voice_clone"
    else:
        raise ValueError(f"Unsupported TTS backend: {backend}")
    return {
        "output_path": output_path,
        "duration_sec": duration_sec,
        "sample_rate": int(sample_rate),
        "mode": mode,
        "backend": backend,
        "reference_used": reference_audio_path is not None,
    }


def _generate_voice_clone(*, text: str, language: str, reference_audio_path: Path) -> tuple[np.ndarray, int]:
    device = resolve_tts_device("auto")
    model = _load_qwen_model("Qwen/Qwen3-TTS-12Hz-0.6B-Base", device)
    segment = _build_segment(text, language)
    wavs, sample_rate = model.generate_voice_clone(
        text=text,
        language=_language_name(language),
        ref_audio=str(reference_audio_path),
        x_vector_only_mode=True,
        non_streaming_mode=True,
        max_new_tokens=_max_new_tokens_for(segment),
    )
    if not wavs:
        raise RuntimeError("Qwen3-TTS returned no waveform for voice clone generation")
    return _normalize_waveform(wavs[0]), int(sample_rate)


def _generate_voice_design(*, text: str, language: str) -> tuple[np.ndarray, int]:
    device = resolve_tts_device("auto")
    model = _load_voice_design_model(device)
    segment = _build_segment(text, language)
    wavs, sample_rate = model.generate_voice_design(
        text=text,
        instruct=_voice_design_prompt(language),
        language=_language_name(language),
        non_streaming_mode=True,
        max_new_tokens=_max_new_tokens_for(segment),
    )
    if not wavs:
        raise RuntimeError("Qwen3-TTS returned no waveform for voice design generation")
    return _normalize_waveform(wavs[0]), int(sample_rate)


@lru_cache(maxsize=3)
def _load_voice_design_model(device: str):
    return _load_qwen_model("Qwen/Qwen3-TTS-12Hz-0.6B-VoiceDesign", device)


# Match the reference shape the pipeline feeds these clone-only backends:
# mono, capped to ~11s of speech with a short silence tail (see dubbing/reference.py).
_REFERENCE_MAX_SPEECH_SEC = 11.0
_REFERENCE_TAIL_SILENCE_SEC = 1.0


def _generate_via_protocol_backend(
    *,
    backend: str,
    text: str,
    language: str,
    reference_audio_path: Path,
    output_path: Path,
) -> tuple[int, float]:
    prepared_path, prepared_duration = _prepare_reference_audio(reference_audio_path, output_path.parent)
    reference = ReferencePackage(
        speaker_id="atomic",
        profile_id="atomic",
        original_audio_path=reference_audio_path,
        prepared_audio_path=prepared_path,
        text="",  # empty: MOSS ignores ref text; VoxCPM uses audio-only "reference" mode
        duration_sec=prepared_duration,
        score=0.0,
        selection_reason="atomic-tool-upload",
    )
    segment = _build_segment(text, language)
    if backend == "moss-tts-nano-onnx":
        tts_backend = MossTtsNanoOnnxBackend(requested_device="auto", worker_count_hint=1)
        try:
            output = tts_backend.synthesize(reference=reference, segment=segment, output_path=output_path)
        finally:
            # Tear down the persistent worker subprocess after the one-shot job.
            tts_backend.close()
    else:  # voxcpm2
        tts_backend = VoxCPMTTSBackend(requested_device="auto")
        output = tts_backend.synthesize(reference=reference, segment=segment, output_path=output_path)
    return int(output.sample_rate), float(output.generated_duration_sec)


def _prepare_reference_audio(reference_audio_path: Path, work_dir: Path) -> tuple[Path, float]:
    try:
        waveform, sample_rate = sf.read(str(reference_audio_path), dtype="float32", always_2d=False)
    except Exception:
        # soundfile cannot decode every accepted upload format (e.g. mp3/m4a);
        # fall back to the raw upload so the backend's own loader can try.
        return reference_audio_path, 0.0
    array = np.asarray(waveform, dtype=np.float32)
    if array.ndim == 2:
        array = array.mean(axis=1)
    array = np.squeeze(array).astype(np.float32)
    max_samples = int(_REFERENCE_MAX_SPEECH_SEC * sample_rate)
    if array.shape[0] > max_samples:
        array = array[:max_samples]
    tail = np.zeros(int(_REFERENCE_TAIL_SILENCE_SEC * sample_rate), dtype=np.float32)
    array = np.concatenate([array, tail])
    prepared_path = work_dir / "reference_prepared.wav"
    sf.write(prepared_path, array, sample_rate)
    return prepared_path, round(float(len(array) / sample_rate), 3)


def _build_segment(text: str, language: str) -> SynthSegmentInput:
    return SynthSegmentInput(
        segment_id="atomic-tts",
        speaker_id="atomic",
        target_lang=language if language != "auto" else "en",
        target_text=text,
        source_duration_sec=max(0.8, len(text) / 12.0),
        duration_budget_sec=max(0.8, len(text) / 10.0),
    )


def _voice_design_prompt(language: str) -> str:
    if language.startswith("zh"):
        return "A clear, neutral Chinese voice with natural pacing."
    if language.startswith("ja"):
        return "A clear, neutral Japanese voice with natural pacing."
    return "A clear, neutral English voice with natural pacing."


register_tool(
    ToolSpec(
        tool_id="tts",
        name_zh="语音合成",
        name_en="Text to Speech",
        description_zh="将文本转为语音，并可选参考音色克隆",
        description_en="Synthesize speech from text with optional reference voice cloning",
        category="speech",
        icon="Mic",
        accept_formats=[".wav", ".mp3", ".flac", ".m4a", ".ogg", ".txt"],
        max_file_size_mb=1024,
        max_files=1,
    ),
    TtsAdapter,
)
