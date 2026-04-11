from __future__ import annotations

from pathlib import Path

from ..config import DEFAULT_SAMPLE_RATE
from ..exceptions import VideoVoiceSeparateError
from ..types import MediaInfo, SeparationRequest
from ..utils.ffmpeg import extract_audio, probe_media


def probe_input(path: Path) -> MediaInfo:
    if not path.exists():
        raise VideoVoiceSeparateError(f"Input file does not exist: {path}")
    return probe_media(path)


def prepare_working_audio(
    request: SeparationRequest,
    work_dir: Path,
) -> tuple[MediaInfo, Path]:
    media_info = probe_input(Path(request.input_path))
    if media_info.audio_stream_count == 0:
        raise VideoVoiceSeparateError("Input file does not contain an audio stream")

    temp_dir = work_dir / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    working_audio = temp_dir / "input.wav"
    extract_audio(
        input_path=Path(request.input_path),
        output_path=working_audio,
        audio_stream_index=request.audio_stream_index,
        sample_rate=DEFAULT_SAMPLE_RATE,
    )
    return media_info, working_audio

