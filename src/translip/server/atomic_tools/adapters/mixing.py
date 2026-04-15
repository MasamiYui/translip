from __future__ import annotations

from pathlib import Path

import soundfile as sf

from ....rendering.audio import (
    build_sidechain_preview_mix,
    db_to_gain,
    peak_limit,
    prepare_audio_for_mix,
    write_wav,
)
from ....utils.ffmpeg import export_audio
from ..registry import ToolSpec, register_tool
from ..schemas import MixingToolRequest
from . import ToolAdapter


class MixingAdapter(ToolAdapter):
    def validate_params(self, params: dict) -> dict:
        return MixingToolRequest(**params).model_dump()

    def run(self, params, input_dir, output_dir, on_progress):
        voice_path = self.first_input(input_dir, "voice_file")
        background_path = self.first_input(input_dir, "background_file")
        output_format = params.get("output_format", "wav")
        output_path = output_dir / f"mixed.{output_format}"
        on_progress(10.0, "preparing")

        voice_info = sf.info(voice_path)
        background_info = sf.info(background_path)
        sample_rate = max(int(voice_info.samplerate), int(background_info.samplerate))
        temp_wav = output_dir / "mixed.wav"

        if params.get("ducking_mode", "static") == "sidechain":
            build_sidechain_preview_mix(
                dub_voice_path=voice_path,
                background_path=background_path,
                output_path=temp_wav,
                output_sample_rate=sample_rate,
                background_gain_db=float(params.get("background_gain_db", -8.0)),
                use_loudnorm=False,
            )
        else:
            voice = prepare_audio_for_mix(voice_path, target_sample_rate=sample_rate)
            background = prepare_audio_for_mix(background_path, target_sample_rate=sample_rate)
            background = background * db_to_gain(float(params.get("background_gain_db", -8.0)))
            target_length = max(len(voice), len(background))
            padded_voice = _pad_to_length(voice, target_length)
            padded_background = _pad_to_length(background, target_length)
            mixed = peak_limit((padded_voice + padded_background).astype("float32"))
            write_wav(temp_wav, mixed, sample_rate=sample_rate)

        if output_format == "wav":
            if temp_wav != output_path:
                self.copy_output(temp_wav, output_dir, output_path.name)
        else:
            export_audio(temp_wav, output_path, output_format)

        on_progress(95.0, "finalizing")
        return {
            "mixed_file": output_path.name,
            "output_format": output_format,
            "sample_rate": sample_rate,
        }


def _pad_to_length(waveform, target_length: int):
    if len(waveform) >= target_length:
        return waveform
    import numpy as np

    return np.pad(waveform, (0, target_length - len(waveform)))


register_tool(
    ToolSpec(
        tool_id="mixing",
        name_zh="音频混合",
        name_en="Audio Mixing",
        description_zh="将人声轨和背景轨混合为单一音频文件",
        description_en="Mix a vocal track and a background track into one output",
        category="audio",
        icon="Music",
        accept_formats=[".wav", ".mp3", ".flac", ".m4a", ".ogg"],
        max_file_size_mb=500,
        max_files=2,
    ),
    MixingAdapter,
)
