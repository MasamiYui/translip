from __future__ import annotations

import os
from pathlib import Path

DEFAULT_SAMPLE_RATE = 44_100
TRANSCRIPTION_SAMPLE_RATE = 16_000
DEFAULT_OUTPUT_FORMAT = "wav"
DEFAULT_MODE = "auto"
DEFAULT_DEVICE = "auto"
DEFAULT_TRANSCRIPTION_LANGUAGE = "zh"
DEFAULT_TRANSCRIPTION_ASR_MODEL = "small"
DEFAULT_MUSIC_BACKEND = "demucs"
DEFAULT_DIALOGUE_BACKEND = "cdx23"
DEFAULT_TRANSLATION_BACKEND = "local-m2m100"
DEFAULT_TRANSLATION_SOURCE_LANG = "zh"
DEFAULT_TRANSLATION_TARGET_LANG = "en"
DEFAULT_TRANSLATION_LOCAL_MODEL = "facebook/m2m100_418M"
DEFAULT_TRANSLATION_BATCH_SIZE = 4
DEFAULT_SILICONFLOW_BASE_URL = os.environ.get("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
DEFAULT_SILICONFLOW_MODEL = os.environ.get("SILICONFLOW_MODEL", "deepseek-ai/DeepSeek-V3")
SUPPORTED_OUTPUT_FORMATS = {"wav", "mp3", "flac", "aac", "opus"}
OUTPUT_ROOT = Path("output")
CACHE_ROOT = Path(
    os.environ.get(
        "VIDEO_VOICE_SEPARATE_CACHE_DIR",
        Path.home() / ".cache" / "video-voice-separate",
    )
)
