"""Video processor module - handles video decoding and frame extraction"""

import cv2
import numpy as np
from typing import Generator, Tuple, Optional
from pathlib import Path
import logging

from translip.ocr.config import settings

logger = logging.getLogger(__name__)


class VideoProcessor:
    """
    Video processor - handles video decoding and frame extraction

    Provides methods to extract frames by interval, by indices, or uniformly.
    """

    def __init__(self, video_path: str):
        """
        Initialize video processor

        Args:
            video_path: Path to video file
        """
        self.video_path = video_path
        self.cap = None
        self.fps = 0.0
        self.total_frames = 0
        self.duration = 0.0
        self.width = 0
        self.height = 0

        self._initialize()

    def _initialize(self):
        """Initialize video information"""
        if not Path(self.video_path).exists():
            raise FileNotFoundError(f"Video not found: {self.video_path}")

        # Use OpenCV to get basic information
        self.cap = cv2.VideoCapture(self.video_path)
        if not self.cap.isOpened():
            raise ValueError(f"Cannot open video: {self.video_path}")

        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.duration = self.total_frames / self.fps if self.fps > 0 else 0

        logger.info(
            f"Video loaded: {self.video_path}, "
            f"FPS: {self.fps:.2f}, Frames: {self.total_frames}, "
            f"Duration: {self.duration:.2f}s, Resolution: {self.width}x{self.height}"
        )

    def extract_frames_by_interval(
        self,
        interval: float = 1.0,
        start_time: float = 0.0,
        end_time: Optional[float] = None,
    ) -> Generator[Tuple[np.ndarray, float, int], None, None]:
        """
        Extract frames by time interval

        Args:
            interval: Sampling interval in seconds
            start_time: First timestamp to sample, in seconds
            end_time: Exclusive end timestamp to sample, in seconds

        Yields:
            Tuple of (frame, timestamp, frame_index)
        """
        frame_interval = int(self.fps * interval)
        frame_interval = max(1, frame_interval)  # At least 1 frame

        fps = self.fps if self.fps > 0 else 1.0
        start_frame = int(max(0, start_time or 0.0) * fps)
        start_frame = max(0, min(self.total_frames, start_frame))
        end_frame = self.total_frames
        if end_time is not None:
            end_frame = int(max(0.0, end_time) * fps)
            end_frame = max(0, min(self.total_frames, end_frame))
        if end_frame <= start_frame:
            return

        self.cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        current_frame = start_frame

        while current_frame < end_frame:
            ret, frame = self.cap.read()
            if not ret:
                break

            timestamp = current_frame / fps
            yield frame, timestamp, current_frame
            current_frame += 1

            skipped = 0
            while skipped < frame_interval - 1 and current_frame < end_frame:
                if not self.cap.grab():
                    return
                skipped += 1
                current_frame += 1

    def extract_frames_by_indices(
        self,
        indices: list
    ) -> Generator[Tuple[np.ndarray, float, int], None, None]:
        """
        Extract frames by specific indices

        Args:
            indices: List of frame indices

        Yields:
            Tuple of (frame, timestamp, frame_index)
        """
        for idx in indices:
            if idx >= self.total_frames:
                continue
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = self.cap.read()

            if ret:
                timestamp = idx / self.fps
                yield frame, timestamp, idx

    def extract_specific_frames(
        self,
        num_frames: int
    ) -> Generator[Tuple[np.ndarray, float, int], None, None]:
        """
        Extract specific number of frames uniformly (for pre-detection)

        Args:
            num_frames: Number of frames to extract

        Yields:
            Tuple of (frame, timestamp, frame_index)
        """
        if num_frames >= self.total_frames:
            # If requested frames >= total, extract all
            step = 1
        else:
            step = self.total_frames // num_frames

        indices = list(range(0, self.total_frames, step))[:num_frames]
        yield from self.extract_frames_by_indices(indices)

    def get_frame_at_time(self, timestamp: float) -> Optional[np.ndarray]:
        """
        Get frame at specific timestamp

        Args:
            timestamp: Time in seconds

        Returns:
            Frame array or None if not found
        """
        frame_index = int(timestamp * self.fps)
        if frame_index >= self.total_frames:
            return None

        self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ret, frame = self.cap.read()
        return frame if ret else None

    def get_frame_at_index(self, frame_index: int) -> Optional[np.ndarray]:
        """
        Get frame at specific index

        Args:
            frame_index: Frame index

        Returns:
            Frame array or None if not found
        """
        if frame_index >= self.total_frames:
            return None

        self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ret, frame = self.cap.read()
        return frame if ret else None

    def extract_bottom_roi(
        self,
        frame: np.ndarray,
        roi_ratio: float = None
    ) -> Tuple[np.ndarray, int]:
        """
        Extract bottom ROI region from frame

        Args:
            frame: Input frame
            roi_ratio: ROI ratio (default from settings)

        Returns:
            Tuple of (roi_frame, roi_start_y)
        """
        if roi_ratio is None:
            roi_ratio = settings.SUBTITLE_ROI_BOTTOM_RATIO

        height = frame.shape[0]
        roi_start = int(height * (1 - roi_ratio))
        return frame[roi_start:, :], roi_start

    def close(self):
        """Release resources"""
        if self.cap:
            self.cap.release()
            self.cap = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __del__(self):
        self.close()
