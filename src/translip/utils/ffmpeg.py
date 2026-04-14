from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from imageio_ffmpeg import get_ffmpeg_exe

from ..exceptions import DependencyError, FFmpegError
from ..types import MediaInfo


def _resolve_binary(name: str) -> str:
    env_name = name.upper() + "_BINARY"
    env_value = os.environ.get(env_name)
    if env_value:
        return env_value

    found = shutil.which(name)
    if found:
        return found

    if name == "ffmpeg":
        return get_ffmpeg_exe()

    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path and name != "ffmpeg":
        try:
            ffmpeg_path = get_ffmpeg_exe()
        except Exception:
            ffmpeg_path = None
    if ffmpeg_path:
        sibling = str(Path(ffmpeg_path).with_name(name))
        if Path(sibling).exists():
            return sibling

    raise DependencyError(
        f"Required binary '{name}' not found. Install ffmpeg or set {env_name}."
    )


def ffmpeg_binary() -> str:
    return _resolve_binary("ffmpeg")


def ffprobe_binary() -> str:
    return _resolve_binary("ffprobe")


def run_ffmpeg(args: list[str]) -> subprocess.CompletedProcess[str]:
    command = [ffmpeg_binary(), *args]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise FFmpegError(result.stderr.strip() or "ffmpeg failed")
    return result


def run_ffprobe_json(path: Path) -> dict[str, Any]:
    command = [
        ffprobe_binary(),
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
        str(path),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise FFmpegError(result.stderr.strip() or "ffprobe failed")
    return json.loads(result.stdout)


def probe_media(path: Path) -> MediaInfo:
    payload = run_ffprobe_json(path)
    streams = payload.get("streams", [])
    format_info = payload.get("format", {})
    audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
    video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
    selected_audio = audio_streams[0] if audio_streams else None
    duration = 0.0
    duration_text = format_info.get("duration") or (
        selected_audio and selected_audio.get("duration")
    )
    if duration_text:
        duration = float(duration_text)

    return MediaInfo(
        path=path,
        media_type="video" if video_streams else "audio",
        format_name=format_info.get("format_name"),
        duration_sec=duration,
        audio_stream_index=(selected_audio or {}).get("index"),
        audio_stream_count=len(audio_streams),
        sample_rate=int(selected_audio["sample_rate"]) if selected_audio else None,
        channels=int(selected_audio["channels"]) if selected_audio else None,
    )


def extract_audio(
    input_path: Path,
    output_path: Path,
    audio_stream_index: int = 0,
    sample_rate: int = 44_100,
    channels: int = 2,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        [
            "-y",
            "-i",
            str(input_path),
            "-map",
            f"0:a:{audio_stream_index}",
            "-vn",
            "-ac",
            str(channels),
            "-ar",
            str(sample_rate),
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]
    )
    return output_path


def render_wav(input_path: Path, output_path: Path, sample_rate: int | None = None) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    args = ["-y", "-i", str(input_path)]
    if sample_rate:
        args.extend(["-ar", str(sample_rate)])
    args.extend(["-c:a", "pcm_s16le", str(output_path)])
    run_ffmpeg(args)
    return output_path


def mix_audio(inputs: list[Path], output_path: Path) -> Path:
    if not inputs:
        raise FFmpegError("mix_audio requires at least one input stem")

    if len(inputs) == 1:
        return render_wav(inputs[0], output_path)

    args: list[str] = ["-y"]
    for stem in inputs:
        args.extend(["-i", str(stem)])
    args.extend(
        [
            "-filter_complex",
            f"amix=inputs={len(inputs)}:normalize=0,alimiter=limit=0.95",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]
    )
    run_ffmpeg(args)
    return output_path


def export_audio(
    input_path: Path,
    output_path: Path,
    fmt: str,
    sample_rate: int | None = None,
    bitrate: str | None = None,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    args = ["-y", "-i", str(input_path)]
    if sample_rate:
        args.extend(["-ar", str(sample_rate)])

    if fmt == "wav":
        args.extend(["-c:a", "pcm_s16le"])
    elif fmt == "mp3":
        args.extend(["-c:a", "libmp3lame", "-b:a", bitrate or "320k"])
    elif fmt == "flac":
        args.extend(["-c:a", "flac"])
    elif fmt == "aac":
        args.extend(["-c:a", "aac", "-b:a", bitrate or "256k"])
    elif fmt == "opus":
        args.extend(["-c:a", "libopus", "-b:a", bitrate or "192k"])
    else:
        raise FFmpegError(f"Unsupported output format: {fmt}")

    args.append(str(output_path))
    run_ffmpeg(args)
    return output_path


def mux_video_with_audio(
    *,
    input_video_path: Path,
    input_audio_path: Path,
    output_path: Path,
    video_codec: str = "copy",
    audio_codec: str = "aac",
    audio_bitrate: str | None = None,
    end_policy: str = "trim_audio_to_video",
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    args = [
        "-y",
        "-i",
        str(input_video_path),
        "-i",
        str(input_audio_path),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        video_codec,
        "-c:a",
        audio_codec,
    ]
    if audio_bitrate:
        args.extend(["-b:a", audio_bitrate])
    if end_policy == "trim_audio_to_video":
        args.extend(["-af", "apad", "-shortest"])
    elif end_policy == "keep_longest":
        args.extend(["-af", "apad"])
    else:
        raise FFmpegError(f"Unsupported end policy: {end_policy}")
    args.extend(["-movflags", "+faststart", str(output_path)])
    run_ffmpeg(args)
    return output_path
