"""Cheap, dependency-free value types for the in-tree subtitle eraser.

Kept import-light (no cv2 / torch) so ``import translip.erase`` and the bridge
that wires the ``subtitle-erase`` node can read these without pulling the heavy
inpainting stack.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class EraseBackend(str, Enum):
    """Inpainting backend used to fill the masked subtitle region.

    - ``sttn``   : Spatial-Temporal Transformer Network video inpainting
                   (temporal context, best general quality). Needs torch + weights.
    - ``lama``   : big-LaMa single-frame inpainting (sharpest stills / animation).
                   Needs torch + the TorchScript weight.
    """

    STTN = "sttn"
    LAMA = "lama"


@dataclass(frozen=True, slots=True)
class VideoInfo:
    fps: float
    width: int
    height: int
    total_frames: int
    duration: float = 0.0


@dataclass(slots=True)
class EraseResult:
    """Outcome of an erase run, surfaced to the CLI/manifest layer."""

    clean_video: str
    backend: EraseBackend
    device: str
    video: VideoInfo
    erased_ranges: list[tuple[int, int]] = field(default_factory=list)
    processed_frames: int = 0
    audio_muxed: bool = True


__all__ = ["EraseBackend", "VideoInfo", "EraseResult"]
