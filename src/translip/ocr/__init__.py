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
from .services.subtitle_service import SubtitleService

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
