"""Effective configuration introspection (ARCH-13).

Reports, for each operationally-relevant knob, the value the running process is
actually using and where it came from (an environment override vs the built-in
default). Resolvers across the codebase read ``os.environ`` directly (e.g.
``resolve_deepseek_base_url``), and settings-bridged values are applied to the
environment at startup, so reading ``os.environ`` here matches what the code
sees. Secret values (API keys / tokens) are never returned — only whether they
are set.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping

from ..config import CACHE_ROOT, DEFAULT_DEEPSEEK_BASE_URL


@dataclass(frozen=True)
class ConfigKnob:
    key: str
    env_var: str
    default: str | None
    description: str
    secret: bool = False


def _cache_path(*parts: str) -> str:
    return str(CACHE_ROOT.joinpath(*parts))


CONFIG_KNOBS: tuple[ConfigKnob, ...] = (
    # Paths / storage
    ConfigKnob("cache_dir", "TRANSLIP_CACHE_DIR", str(CACHE_ROOT), "Model cache + pipeline output root"),
    ConfigKnob("db_path", "TRANSLIP_DB_PATH", _cache_path("data.db"), "Server SQLite database path"),
    ConfigKnob("user_config", "TRANSLIP_USER_CONFIG", None, "Path to persisted user settings JSON"),
    ConfigKnob("ffmpeg_binary", "FFMPEG_BINARY", "ffmpeg", "ffmpeg executable (defaults to PATH lookup)"),
    ConfigKnob("default_glossary", "TRANSLIP_DEFAULT_GLOSSARY", None, "Default translation glossary JSON applied to every job"),
    # Translation LLM (deepseek)
    ConfigKnob("deepseek_api_key", "DEEPSEEK_API_KEY", None, "DeepSeek API key", secret=True),
    ConfigKnob("deepseek_base_url", "DEEPSEEK_BASE_URL", DEFAULT_DEEPSEEK_BASE_URL, "DeepSeek API base URL"),
    ConfigKnob("deepseek_model", "DEEPSEEK_MODEL", "deepseek-v4-pro", "DeepSeek model name"),
    # TTS backends
    ConfigKnob("moss_tts_cli", "MOSS_TTS_NANO_CLI", None, "moss-tts-nano CLI executable"),
    ConfigKnob("moss_tts_model_dir", "MOSS_TTS_NANO_MODEL_DIR", None, "moss-tts-nano model directory"),
    ConfigKnob("moss_tts_cpu_threads", "MOSS_TTS_NANO_CPU_THREADS", None, "moss-tts-nano CPU thread count"),
    ConfigKnob("moss_tts_python", "MOSS_TTS_NANO_PYTHON", None, "Python interpreter for the moss-tts-nano CLI"),
    ConfigKnob("qwen_tts_model", "QWEN_TTS_MODEL", None, "Qwen3-TTS model id override"),
    ConfigKnob("voxcpm_model", "VOXCPM_MODEL", None, "VoxCPM model id override"),
    # OCR / erase model dirs
    ConfigKnob("paddleocr_models_dir", "PADDLEOCR_MODELS_BASE_DIR", _cache_path("paddleocr_models"), "Local PP-OCRv5 model directory"),
    ConfigKnob("subtitle_erase_models_dir", "SUBTITLE_ERASE_MODELS_DIR", _cache_path("erase_models"), "Subtitle-erase inpainting weights cache"),
    # Tokens (secret)
    ConfigKnob("hf_token", "HF_TOKEN", None, "HuggingFace Hub token", secret=True),
    ConfigKnob("huggingface_hub_token", "HUGGINGFACE_HUB_TOKEN", None, "HuggingFace Hub token (alt env)", secret=True),
    ConfigKnob("pyannote_auth_token", "PYANNOTE_AUTH_TOKEN", None, "pyannote diarizer auth token", secret=True),
    ConfigKnob("tmdb_api_key", "TMDB_API_KEY", None, "TMDB API key", secret=True),
)


def _knob_state(knob: ConfigKnob, environ: Mapping[str, str]) -> dict[str, Any]:
    raw = environ.get(knob.env_var)
    overridden = raw is not None and raw != ""
    if overridden:
        value: str | None = raw
        source = "env"
    else:
        value = knob.default
        source = "default"
    return {
        "key": knob.key,
        "env_var": knob.env_var,
        "source": source,
        "is_overridden": overridden,
        "secret": knob.secret,
        # Never leak secret values — only whether one is set.
        "value": ("set" if value else None) if knob.secret else value,
        "default": None if knob.secret else knob.default,
        "description": knob.description,
    }


def introspect_config(*, environ: Mapping[str, str] | None = None) -> list[dict[str, Any]]:
    env = environ if environ is not None else os.environ
    return [_knob_state(knob, env) for knob in CONFIG_KNOBS]
