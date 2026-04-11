from __future__ import annotations

from pathlib import Path

from ..utils.ffmpeg import export_audio


def export_pair(
    voice_path: Path,
    background_path: Path,
    output_dir: Path,
    fmt: str,
    sample_rate: int | None,
    bitrate: str | None,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    voice_out = output_dir / f"voice.{fmt}"
    background_out = output_dir / f"background.{fmt}"
    export_audio(voice_path, voice_out, fmt, sample_rate=sample_rate, bitrate=bitrate)
    export_audio(
        background_path,
        background_out,
        fmt,
        sample_rate=sample_rate,
        bitrate=bitrate,
    )
    return voice_out, background_out

