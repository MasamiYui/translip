"""Self-contained PaddleOCR hard-subtitle extraction for translip.

Vendored from media-sense's `modules/paddle_ocr` (offline core only). This makes
translip's OCR subtitle detection fully in-tree — no external sibling project is
called at runtime. PaddleOCR itself is an optional dependency installed via the
``ocr`` extra (``uv sync --extra ocr``) and is imported lazily, so importing this
package is cheap and only fails with a clear error when extraction actually runs
without paddle installed.

Public API:
    SubtitleService().extract_subtitles(video_path, language=..., ...)
    -> SubtitleExtractionResult

``SubtitleService`` is exposed lazily (it pulls in cv2/paddle), so plain
``import translip.ocr`` stays lightweight; the domain dataclasses are cheap and
imported eagerly.
"""

from .config import settings
from .models.domain import (
    DetectedText,
    Language,
    Subtitle,
    SubtitleAnchor,
    SubtitleExtractionResult,
    TextDetection,
)

__all__ = [
    "settings",
    "SubtitleService",
    "SubtitleExtractionResult",
    "Subtitle",
    "SubtitleAnchor",
    "DetectedText",
    "TextDetection",
    "Language",
]


def __getattr__(name: str):
    # Lazy re-export: importing SubtitleService eagerly would pull cv2/paddle.
    if name == "SubtitleService":
        from .services.subtitle_service import SubtitleService

        return SubtitleService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
