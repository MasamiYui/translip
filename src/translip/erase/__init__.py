"""Self-contained hard-subtitle erasure (inpainting) for translip.

In-tree port of video-subtitle-remover's inpainting core (Apache-2.0): two
backends — STTN video inpainting (default) and big-LaMa single-frame
inpainting — driven by translip's own OCR ``detection.json``. This makes
subtitle erasure fully in-tree with no external sibling project.

The heavy stack (cv2/torch + downloaded weights) is imported lazily, so plain
``import translip.erase`` stays cheap; ``EraseService`` and ``EraseBackend`` only
pull their dependencies when an erase actually runs (and surface a clear error if
torch/weights are unavailable). Weights download on first use via the optional
``erase`` extra path; see :mod:`translip.erase.config` for env overrides.

Public API:
    EraseService().erase(video_path=..., detection_path=..., output_path=...,
                         backend="sttn"|"lama", ...) -> EraseResult
"""

from .config import settings
from .models.domain import EraseBackend, EraseResult, VideoInfo

__all__ = [
    "settings",
    "EraseService",
    "EraseBackend",
    "EraseResult",
    "VideoInfo",
]


def __getattr__(name: str):
    # Lazy re-export: importing EraseService eagerly would pull cv2/torch.
    if name == "EraseService":
        from .services.erase_service import EraseService

        return EraseService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
