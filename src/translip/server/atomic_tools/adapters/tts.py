from __future__ import annotations

import contextlib
import json
import wave
from functools import lru_cache
from pathlib import Path

import numpy as np
import soundfile as sf

from ....dubbing.backend import SynthSegmentInput, resolve_tts_device
from ....dubbing.qwen_tts_backend import (
    _language_name,
    _load_qwen_model,
    _max_new_tokens_for,
    _normalize_waveform,
)
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
            "reference_used": metadata["reference_used"],
        }


def generate_speech(*, text: str, language: str, reference_audio_path: Path | None, output_path: Path) -> dict[str, object]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
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
    return {
        "output_path": output_path,
        "duration_sec": round(float(len(waveform) / sample_rate), 3),
        "sample_rate": int(sample_rate),
        "mode": mode,
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
        max_file_size_mb=100,
        max_files=1,
    ),
    TtsAdapter,
)
