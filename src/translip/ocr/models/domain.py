"""Domain models for subtitle extraction"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from enum import Enum


class Language(Enum):
    """Supported languages"""
    CHINESE = "ch"
    ENGLISH = "en"
    KOREAN = "korean"
    JAPANESE = "japan"
    AUTO = "auto"


@dataclass
class SubtitleAnchor:
    """
    Subtitle anchor - defines subtitle region

    Coordinates are relative ratios (0-1) of frame dimensions
    """
    center_x: float          # Center X coordinate (relative ratio 0-1)
    center_y: float          # Center Y coordinate (relative ratio 0-1)
    height: float            # Subtitle height (relative ratio 0-1)
    width: float             # Subtitle width (relative ratio 0-1)
    language: Language       # Detected language
    confidence: float        # Confidence score
    source: str = "unknown"
    position_mode: str = "auto"
    debug_info: Optional[dict] = None

    # Absolute pixel coordinates (calculated at runtime)
    abs_box: Optional[Tuple[int, int, int, int]] = None  # (x1, y1, x2, y2)


@dataclass
class DetectedText:
    """Detected text from OCR"""
    text: str
    confidence: float
    box: Tuple[int, int, int, int]  # (x1, y1, x2, y2)
    timestamp: float  # Timestamp in seconds
    frame_index: int
    polygon: Optional[List[Tuple[float, float]]] = None
    rotated_box: Optional[dict] = None
    recognition_region: Optional[Tuple[int, int, int, int]] = None
    recognition_executed: bool = True
    sample_debug: Optional[dict] = None


@dataclass
class Subtitle:
    """Subtitle entry"""
    index: int
    start_time: float    # Seconds
    end_time: float      # Seconds
    text: str
    confidence: float = 1.0
    box: Optional[Tuple[int, int, int, int]] = None
    polygon: Optional[List[Tuple[float, float]]] = None
    rotated_box: Optional[dict] = None
    debug_info: Optional[dict] = None

    def to_srt_format(self) -> str:
        """Convert to SRT format"""
        start_srt = self._seconds_to_srt_time(self.start_time)
        end_srt = self._seconds_to_srt_time(self.end_time)
        return f"{self.index}\n{start_srt} --> {end_srt}\n{self.text}\n"

    @staticmethod
    def _seconds_to_srt_time(seconds: float) -> str:
        """Convert seconds to SRT time format HH:MM:SS,mmm"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


@dataclass
class SubtitleExtractionResult:
    """Subtitle extraction result"""
    subtitles: List[Subtitle]
    anchors: List[SubtitleAnchor]
    total_frames: int
    processed_frames: int
    duration: float
    language: Language
    anchor_debug: Optional[dict] = None


@dataclass
class TextDetection:
    """Text detection result from OCR"""
    box: Tuple[int, int, int, int]  # (x1, y1, x2, y2)
    text: str
    confidence: float
    polygon: Optional[List[Tuple[float, float]]] = None
    rotated_box: Optional[dict] = None
    center_y: float = 0.0  # Computed during processing
    center_x: float = 0.0
    height: int = 0
    width: int = 0
