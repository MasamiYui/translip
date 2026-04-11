from __future__ import annotations

import os
from pathlib import Path

DEFAULT_SAMPLE_RATE = 44_100
DEFAULT_OUTPUT_FORMAT = "wav"
DEFAULT_MODE = "auto"
DEFAULT_DEVICE = "auto"
DEFAULT_MUSIC_BACKEND = "demucs"
DEFAULT_DIALOGUE_BACKEND = "cdx23"
SUPPORTED_OUTPUT_FORMATS = {"wav", "mp3", "flac", "aac", "opus"}
OUTPUT_ROOT = Path("output")
CACHE_ROOT = Path(
    os.environ.get(
        "VIDEO_VOICE_SEPARATE_CACHE_DIR",
        Path.home() / ".cache" / "video-voice-separate",
    )
)
