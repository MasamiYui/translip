from __future__ import annotations

import subprocess
from functools import lru_cache
from pathlib import Path

import numpy as np
import soundfile as sf

from ..exceptions import DependencyError
from ..utils.ffmpeg import ffmpeg_binary, run_ffmpeg


def db_to_gain(db: float) -> float:
    return float(10 ** (db / 20.0))


def read_audio_mono(audio_path: Path) -> tuple[np.ndarray, int]:
    waveform, sample_rate = sf.read(audio_path, dtype="float32", always_2d=False)
    if waveform.ndim == 2:
        waveform = waveform.mean(axis=1)
    return waveform.astype(np.float32), sample_rate


def resample_linear(waveform: np.ndarray, original_rate: int, target_rate: int) -> np.ndarray:
    if waveform.size == 0 or original_rate == target_rate:
        return waveform.astype(np.float32)
    duration_sec = waveform.size / float(original_rate)
    target_size = max(1, int(round(duration_sec * target_rate)))
    source_index = np.linspace(0.0, waveform.size - 1, num=waveform.size, dtype=np.float32)
    target_index = np.linspace(0.0, waveform.size - 1, num=target_size, dtype=np.float32)
    return np.interp(target_index, source_index, waveform).astype(np.float32)


def prepare_audio_for_mix(audio_path: Path, *, target_sample_rate: int) -> np.ndarray:
    waveform, sample_rate = read_audio_mono(audio_path)
    if sample_rate != target_sample_rate:
        waveform = resample_linear(waveform, sample_rate, target_sample_rate)
    return waveform.astype(np.float32)


def apply_fade(waveform: np.ndarray, *, sample_rate: int, fade_sec: float = 0.01) -> np.ndarray:
    if waveform.size == 0:
        return waveform.astype(np.float32)
    fade_samples = min(int(round(fade_sec * sample_rate)), waveform.size // 2)
    if fade_samples <= 0:
        return waveform.astype(np.float32)
    faded = waveform.astype(np.float32).copy()
    ramp = np.linspace(0.0, 1.0, fade_samples, dtype=np.float32)
    faded[:fade_samples] *= ramp
    faded[-fade_samples:] *= ramp[::-1]
    return faded


def peak_limit(waveform: np.ndarray, *, peak: float = 0.95) -> np.ndarray:
    if waveform.size == 0:
        return waveform.astype(np.float32)
    current_peak = float(np.max(np.abs(waveform)))
    if current_peak <= peak or current_peak <= 1e-8:
        return waveform.astype(np.float32)
    return (waveform * (peak / current_peak)).astype(np.float32)


def write_wav(audio_path: Path, waveform: np.ndarray, *, sample_rate: int) -> Path:
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(audio_path, waveform.astype(np.float32), sample_rate)
    return audio_path


def compress_audio(
    *,
    input_path: Path,
    output_path: Path,
    tempo: float,
    backend: str,
    output_sample_rate: int,
) -> Path:
    if tempo <= 1.0:
        waveform = prepare_audio_for_mix(input_path, target_sample_rate=output_sample_rate)
        return write_wav(output_path, waveform, sample_rate=output_sample_rate)

    filter_spec = _tempo_filter(tempo=tempo, backend=backend)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        [
            "-y",
            "-i",
            str(input_path),
            "-af",
            filter_spec,
            "-ar",
            str(output_sample_rate),
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]
    )
    return output_path


def build_sidechain_preview_mix(
    *,
    dub_voice_path: Path,
    background_path: Path,
    output_path: Path,
    output_sample_rate: int,
    background_gain_db: float,
    use_loudnorm: bool,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    chain = (
        f"[1:a]volume={background_gain_db}dB[bg];"
        "[bg][0:a]sidechaincompress=threshold=0.08:ratio=6:attack=20:release=250[ducked];"
        "[ducked][0:a]amix=inputs=2:normalize=0"
    )
    if use_loudnorm:
        chain += ",loudnorm=I=-16:LRA=11:TP=-1.5"
    chain += ",alimiter=limit=0.95"
    run_ffmpeg(
        [
            "-y",
            "-i",
            str(dub_voice_path),
            "-i",
            str(background_path),
            "-filter_complex",
            chain,
            "-ar",
            str(output_sample_rate),
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]
    )
    return output_path


def audio_duration_sec(audio_path: Path) -> float:
    info = sf.info(audio_path)
    return float(info.duration)


def _tempo_filter(*, tempo: float, backend: str) -> str:
    if backend == "atempo":
        return f"atempo={tempo:.6f}"
    if backend == "rubberband":
        if not ffmpeg_supports_filter("rubberband"):
            raise DependencyError(
                "ffmpeg rubberband filter is not available in the current build. "
                "Use --fit-backend atempo or install ffmpeg with librubberband."
            )
        return f"rubberband=tempo={tempo:.6f}"
    raise DependencyError(f"Unsupported fit backend: {backend}")


@lru_cache(maxsize=1)
def ffmpeg_supports_filter(filter_name: str) -> bool:
    result = subprocess.run(
        [ffmpeg_binary(), "-hide_banner", "-filters"],
        capture_output=True,
        text=True,
        check=False,
    )
    return filter_name in result.stdout
