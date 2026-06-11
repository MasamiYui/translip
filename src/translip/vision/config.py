"""Environment-overridable settings for the in-tree vision module.

Unlike :mod:`translip.ocr.config` / :mod:`translip.erase.config` this module is
**stdlib-only** (no pydantic-settings): the ollama backend is promised to work
without installing any extra, and pydantic-settings only ships with the
ocr/erase/vision extras. Settings are re-read from the environment on every
``load_settings()`` call so tests can monkeypatch ``os.environ`` without
reimporting the module.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from translip.config import CACHE_ROOT

VALID_BACKENDS = ("auto", "mlx", "ollama")
VALID_TASKS = ("scene-context", "erase-qc", "ocr-classify", "speaker-visual", "freeform")
VALID_LANGS = ("zh", "en")


def _env_str(name: str, default: str) -> str:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, ""))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, ""))
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True, slots=True)
class VisionSettings:
    backend: str = "auto"  # auto | mlx | ollama
    model: str = "mlx-community/Qwen3-VL-4B-Instruct-4bit"
    ollama_model: str = "qwen3-vl:4b-instruct"
    ollama_host: str = "http://127.0.0.1:11434"
    # Injected as HF_HUB_CACHE (not HF_HOME — that would move tokens too).
    hf_cache: str = str(CACHE_ROOT / "vision_models" / "hf")
    hf_cache_explicit: bool = False
    local_models_only: bool = False
    frames_per_unit: int = 4  # 1-8
    frame_max_edge: int = 768
    max_new_tokens: int = 256
    temperature: float = 0.2
    # Per-request timeout for the ollama HTTP backend only; mlx runs in-process
    # and cannot be interrupted mid-inference (the parent kills the subprocess).
    timeout_sec: int = 120
    # Scene-skip: when the mid frames of two consecutive units differ by less
    # than this mean-luma distance (0-255), reuse the previous unit's result
    # instead of running inference again. 0 disables the optimization.
    scene_skip_threshold: float = 4.0


def load_settings() -> VisionSettings:
    return VisionSettings(
        backend=_env_str("VISION_BACKEND", "auto"),
        model=_env_str("VISION_MODEL", "mlx-community/Qwen3-VL-4B-Instruct-4bit"),
        ollama_model=_env_str("VISION_OLLAMA_MODEL", "qwen3-vl:4b-instruct"),
        ollama_host=_env_str("VISION_OLLAMA_HOST", "http://127.0.0.1:11434"),
        hf_cache=_env_str("VISION_HF_CACHE", str(CACHE_ROOT / "vision_models" / "hf")),
        hf_cache_explicit="VISION_HF_CACHE" in os.environ,
        local_models_only=_env_bool("VISION_LOCAL_MODELS_ONLY", False),
        frames_per_unit=max(1, min(8, _env_int("VISION_FRAMES_PER_UNIT", 4))),
        frame_max_edge=_env_int("VISION_FRAME_MAX_EDGE", 768),
        max_new_tokens=_env_int("VISION_MAX_NEW_TOKENS", 256),
        temperature=_env_float("VISION_TEMPERATURE", 0.2),
        timeout_sec=_env_int("VISION_TIMEOUT_SEC", 120),
        scene_skip_threshold=max(0.0, _env_float("VISION_SCENE_SKIP_THRESHOLD", 4.0)),
    )


__all__ = ["VALID_BACKENDS", "VALID_LANGS", "VALID_TASKS", "VisionSettings", "load_settings"]
