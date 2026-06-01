"""Environment-overridable settings for the in-tree subtitle eraser.

Mirrors :mod:`translip.ocr.config`: a pydantic-settings ``BaseSettings`` with
``case_sensitive`` fields overridable by their exact uppercase name (no dotenv;
translip configures via process env vars). Model weights default under
``TRANSLIP_CACHE_DIR``. These are *defaults*; per-run values come from the CLI /
``PipelineRequest``.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

from translip.config import CACHE_ROOT


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=True, extra="ignore")

    # Where downloaded inpainting weights are cached (sttn.pth / big-lama.pt).
    SUBTITLE_ERASE_MODELS_DIR: str = str(CACHE_ROOT / "erase_models")
    # When set, never download — the weight file must already be present locally.
    SUBTITLE_ERASE_LOCAL_MODELS_ONLY: bool = False

    # Default inpainting backend and device.
    ERASE_BACKEND: str = "sttn"  # sttn | lama | opencv
    ERASE_DEVICE: str = "auto"  # auto | mps | cuda | cpu

    # Mask construction.
    ERASE_MASK_DILATE_X: int = 12
    ERASE_MASK_DILATE_Y: int = 8
    ERASE_YX_DIFF_PX: int = 10  # drop tall-thin (vertical) boxes above this skew

    # STTN temporal sampling.
    ERASE_NEIGHBOR_STRIDE: int = 5
    ERASE_REFERENCE_LENGTH: int = 10
    ERASE_MAX_LOAD: int = 50  # max frames inpainted per batch

    # libx264 output encoding.
    ERASE_X264_CRF: int = 18
    ERASE_X264_PRESET: str = "fast"


settings = Settings()


__all__ = ["Settings", "settings"]
