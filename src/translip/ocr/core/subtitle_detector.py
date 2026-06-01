"""Subtitle region detector - automatically discovers subtitle positions."""

from __future__ import annotations

import logging
import re
from typing import Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np

from translip.ocr.config import settings
from translip.ocr.core.ocr_engine import OCREngine
from translip.ocr.models.domain import Language, SubtitleAnchor
from translip.ocr.utils.geometry import shift_polygon, shift_rotated_box
from translip.ocr.utils.textness import should_run_ocr

logger = logging.getLogger(__name__)


class SubtitleDetector:
    """
    Subtitle region detector - automatically discovers subtitle positions.

    Uses anchor discovery mechanism:
    1. Sample frames uniformly
    2. Detect text in ROI candidates
    3. Cluster by Y position
    4. Find stable regions (subtitles appear at consistent positions)
    """

    def __init__(self, ocr_engine: OCREngine, prefilter_enabled: Optional[bool] = None):
        self.ocr_engine = ocr_engine
        self.prefilter_enabled = prefilter_enabled
        self.min_confidence = settings.SUBTITLE_MIN_CONFIDENCE
        self.roi_bottom_ratio = settings.SUBTITLE_ROI_BOTTOM_RATIO
        self.min_appearance_ratio = settings.SUBTITLE_ANCHOR_MIN_APPEARANCE_RATIO
        self.max_anchor_count = settings.SUBTITLE_ANCHOR_MAX_COUNT
        self.last_debug_info: dict = {}

    def detect_subtitle_region(
        self,
        frames: List[np.ndarray],
        timestamps: List[float],
        position_mode: str = "auto",
        roi_ratio: Optional[float] = None,
        progress_callback: Optional[Callable[[str, Optional[dict]], None]] = None,
    ) -> List[SubtitleAnchor]:
        logger.info(
            "Detecting subtitle regions from %s frames position_mode=%s",
            len(frames),
            position_mode,
        )

        if not frames:
            self.last_debug_info = {
                "requested_position_mode": position_mode,
                "stages": [],
                "selected_anchor_count": 0,
            }
            return []

        roi_ratio = roi_ratio or self.roi_bottom_ratio
        search_modes = self._resolve_search_modes(position_mode)
        debug_info = {
            "requested_position_mode": position_mode,
            "roi_ratio": roi_ratio,
            "search_modes": search_modes,
            "stages": [],
        }

        anchors: List[SubtitleAnchor] = []
        for mode_index, mode in enumerate(search_modes, start=1):
            detections, collect_debug = self._collect_roi_detections(
                frames,
                timestamps,
                mode,
                roi_ratio,
                progress_callback=progress_callback,
                mode_index=mode_index,
                mode_count=len(search_modes),
            )
            stage_anchors, score_debug = self._find_stable_regions(
                detections,
                frames[0].shape,
                total_frames=len(frames),
                position_mode=mode,
                source=f"{mode}_roi",
            )
            debug_info["stages"].append({
                **collect_debug,
                **score_debug,
                "stage": f"{mode}_roi",
                "position_mode": mode,
            })
            anchors.extend(stage_anchors)

        if not anchors:
            for mode_index, mode in enumerate(search_modes, start=1):
                detections, collect_debug = self._collect_full_frame_detections(
                    frames,
                    timestamps,
                    mode,
                    progress_callback=progress_callback,
                    mode_index=mode_index,
                    mode_count=len(search_modes),
                )
                stage_anchors, score_debug = self._find_stable_regions(
                    detections,
                    frames[0].shape,
                    total_frames=len(frames),
                    position_mode=mode,
                    source=f"{mode}_full_frame",
                )
                debug_info["stages"].append({
                    **collect_debug,
                    **score_debug,
                    "stage": f"{mode}_full_frame",
                    "position_mode": mode,
                })
                anchors.extend(stage_anchors)

        if not anchors:
            for mode_index, mode in enumerate(search_modes, start=1):
                self._emit_progress(
                    progress_callback,
                    "region_scanning_visual_band",
                    {
                        "position_mode": mode,
                        "mode_index": mode_index,
                        "mode_count": len(search_modes),
                        "current": mode_index,
                        "total": len(search_modes),
                    },
                )
                visual_bands = self._detect_temporal_subtitle_bands(frames, mode, roi_ratio)
                band_debug = {
                    "stage": f"{mode}_visual_band",
                    "position_mode": mode,
                    "band_count": len(visual_bands),
                    "bands": [{"y1": y1, "y2": y2} for y1, y2 in visual_bands],
                }
                debug_info["stages"].append(band_debug)
                anchors.extend(self._bands_to_anchors(visual_bands, frames[0].shape, mode))

        anchors = sorted(anchors, key=lambda a: a.confidence, reverse=True)[:self.max_anchor_count]
        debug_info["selected_anchor_count"] = len(anchors)
        debug_info["selected_anchors"] = [
            {
                "center_x": round(anchor.center_x, 4),
                "center_y": round(anchor.center_y, 4),
                "width": round(anchor.width, 4),
                "height": round(anchor.height, 4),
                "confidence": round(anchor.confidence, 4),
                "source": anchor.source,
                "position_mode": anchor.position_mode,
            }
            for anchor in anchors
        ]
        self.last_debug_info = debug_info

        logger.info("Found %s subtitle anchors", len(anchors))
        return anchors

    def _resolve_search_modes(self, position_mode: str) -> List[str]:
        normalized = (position_mode or "auto").lower()
        if normalized in {"top", "middle", "bottom"}:
            return [normalized]
        return ["bottom", "middle", "top"]

    def _get_position_band(self, position_mode: str, roi_ratio: Optional[float] = None) -> Tuple[float, float]:
        window = min(max(roi_ratio or self.roi_bottom_ratio, 0.12), 0.6)
        mode = (position_mode or "bottom").lower()
        if mode == "top":
            return (0.02, min(0.98, 0.02 + window))
        if mode == "middle":
            half = window / 2.0
            return (max(0.02, 0.5 - half), min(0.98, 0.5 + half))
        end = 0.98
        return (max(0.02, end - window), end)

    def _extract_focus_roi(
        self,
        frame: np.ndarray,
        position_mode: str,
        roi_ratio: Optional[float] = None,
    ) -> Tuple[np.ndarray, int]:
        height = frame.shape[0]
        start_ratio, end_ratio = self._get_position_band(position_mode, roi_ratio)
        y1 = int(round(height * start_ratio))
        y2 = int(round(height * end_ratio))
        y2 = max(y1 + 1, min(height, y2))
        return frame[y1:y2, :], y1

    def _collect_roi_detections(
        self,
        frames: List[np.ndarray],
        timestamps: List[float],
        position_mode: str,
        roi_ratio: Optional[float] = None,
        progress_callback: Optional[Callable[[str, Optional[dict]], None]] = None,
        mode_index: int = 1,
        mode_count: int = 1,
    ) -> Tuple[List[dict], dict]:
        all_detections: List[dict] = []
        skipped_prefilter = 0
        sample_prefilter = []

        for idx, (frame, timestamp) in enumerate(zip(frames, timestamps)):
            self._emit_progress(
                progress_callback,
                "region_scanning_roi",
                {
                    "position_mode": position_mode,
                    "mode_index": mode_index,
                    "mode_count": mode_count,
                    "current": idx + 1,
                    "total": len(frames),
                    "timestamp": round(float(timestamp), 3),
                },
            )
            roi_frame, roi_start = self._extract_focus_roi(frame, position_mode, roi_ratio)
            should_ocr, metrics = should_run_ocr(roi_frame, enabled=self.prefilter_enabled)
            if len(sample_prefilter) < 5:
                sample_prefilter.append({
                    "frame_idx": idx,
                    "timestamp": round(timestamp, 3),
                    **metrics,
                })
            if not should_ocr:
                skipped_prefilter += 1
                continue

            detections = self.ocr_engine.detect_text(roi_frame)
            for det in detections:
                det = dict(det)
                det["abs_box"] = self._roi_to_absolute(det["box"], frame.shape, roi_start)
                if det.get("polygon"):
                    det["abs_polygon"] = shift_polygon(det["polygon"], 0, roi_start)
                if det.get("rotated_box"):
                    det["abs_rotated_box"] = shift_rotated_box(det["rotated_box"], 0, roi_start)
                det["frame_idx"] = idx
                det["timestamp"] = timestamp
                all_detections.append(det)

        return all_detections, {
            "roi_ratio": roi_ratio or self.roi_bottom_ratio,
            "frames_considered": len(frames),
            "detections_collected": len(all_detections),
            "prefilter_skipped_frames": skipped_prefilter,
            "prefilter_samples": sample_prefilter,
        }

    def _collect_full_frame_detections(
        self,
        frames: List[np.ndarray],
        timestamps: List[float],
        position_mode: str,
        progress_callback: Optional[Callable[[str, Optional[dict]], None]] = None,
        mode_index: int = 1,
        mode_count: int = 1,
    ) -> Tuple[List[dict], dict]:
        all_detections: List[dict] = []
        if not frames:
            return all_detections, {
                "frames_considered": 0,
                "detections_collected": 0,
                "prefilter_skipped_frames": 0,
                "prefilter_samples": [],
            }

        band_start, band_end = self._get_position_band(position_mode)
        stride = max(1, len(frames) // 8)
        skipped_prefilter = 0
        sample_prefilter = []

        for idx in range(0, len(frames), stride):
            frame = frames[idx]
            timestamp = timestamps[idx]
            current = len(range(0, idx + 1, stride))
            total = len(range(0, len(frames), stride))
            self._emit_progress(
                progress_callback,
                "region_scanning_full_frame",
                {
                    "position_mode": position_mode,
                    "mode_index": mode_index,
                    "mode_count": mode_count,
                    "current": current,
                    "total": total,
                    "timestamp": round(float(timestamp), 3),
                },
            )
            should_ocr, metrics = should_run_ocr(frame, enabled=self.prefilter_enabled)
            if len(sample_prefilter) < 5:
                sample_prefilter.append({
                    "frame_idx": idx,
                    "timestamp": round(timestamp, 3),
                    **metrics,
                })
            if not should_ocr:
                skipped_prefilter += 1
                continue

            detections = self.ocr_engine.detect_text(frame)
            for det in detections:
                box = det["box"]
                center_y_ratio = ((box[1] + box[3]) / 2) / max(frame.shape[0], 1)
                if center_y_ratio < band_start or center_y_ratio > band_end:
                    continue
                det = dict(det)
                det["abs_box"] = (
                    int(det["box"][0]),
                    int(det["box"][1]),
                    int(det["box"][2]),
                    int(det["box"][3]),
                )
                det["frame_idx"] = idx
                det["timestamp"] = timestamp
                all_detections.append(det)

        return all_detections, {
            "frames_considered": len(range(0, len(frames), stride)),
            "detections_collected": len(all_detections),
            "prefilter_skipped_frames": skipped_prefilter,
            "prefilter_samples": sample_prefilter,
        }

    def _emit_progress(
        self,
        progress_callback: Optional[Callable[[str, Optional[dict]], None]],
        stage: str,
        details: Optional[dict] = None,
    ) -> None:
        if progress_callback is None:
            return
        try:
            progress_callback(stage, details)
        except Exception:
            logger.exception("Subtitle detector progress callback failed stage=%s", stage)

    def _detect_temporal_subtitle_bands(
        self,
        frames: List[np.ndarray],
        position_mode: str,
        roi_ratio: Optional[float] = None,
    ) -> List[Tuple[int, int]]:
        if not frames:
            return []

        frame_height, frame_width = frames[0].shape[:2]
        density = np.zeros(frame_height, dtype=np.float32)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 5))

        for frame in frames:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            top_hat = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, kernel)
            black_hat = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, kernel)
            enhanced = cv2.addWeighted(top_hat, 0.6, black_hat, 0.4, 0.0)
            _, binary = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            binary = cv2.morphologyEx(
                binary,
                cv2.MORPH_CLOSE,
                cv2.getStructuringElement(cv2.MORPH_RECT, (15, 3)),
            )
            row_score = np.sum(binary > 0, axis=1).astype(np.float32) / max(frame_width, 1)
            density += row_score

        density /= max(len(frames), 1)
        start_ratio, end_ratio = self._get_position_band(position_mode, roi_ratio)
        focus_start = int(frame_height * start_ratio)
        focus_end = int(frame_height * end_ratio)
        focus = density[focus_start:focus_end]
        if focus.size == 0:
            return []

        smooth = cv2.GaussianBlur(focus.reshape(-1, 1), (1, 21), 0).reshape(-1)
        threshold = max(float(np.percentile(smooth, 85)), float(np.mean(smooth) * 1.15))
        active_rows = np.where(smooth >= threshold)[0]
        if active_rows.size == 0:
            return []

        bands = []
        group = [int(active_rows[0])]
        for row in active_rows[1:]:
            row = int(row)
            if row - group[-1] <= 4:
                group.append(row)
                continue
            bands.append(self._rows_to_band(group, frame_height, focus_start, focus_end))
            group = [row]
        if group:
            bands.append(self._rows_to_band(group, frame_height, focus_start, focus_end))

        merged = []
        for y1, y2 in sorted([band for band in bands if band], key=lambda b: b[0]):
            if not merged:
                merged.append([y1, y2])
                continue
            prev = merged[-1]
            if y1 <= prev[1] + 8:
                prev[1] = max(prev[1], y2)
            else:
                merged.append([y1, y2])

        return [(int(y1), int(y2)) for y1, y2 in merged]

    def _rows_to_band(
        self,
        rows: List[int],
        frame_height: int,
        focus_start: int,
        focus_end: int,
    ) -> Optional[Tuple[int, int]]:
        center = int(np.mean(rows))
        half = max(int(frame_height * 0.035), 12)
        y1 = max(focus_start, focus_start + center - half)
        y2 = min(focus_end, focus_start + center + half)
        if y2 <= y1:
            return None
        return (y1, y2)

    def _bands_to_anchors(
        self,
        bands: List[Tuple[int, int]],
        frame_shape: Tuple[int, int, int],
        position_mode: str,
    ) -> List[SubtitleAnchor]:
        frame_height, _ = frame_shape[:2]
        anchors = []
        for y1, y2 in bands:
            band_h = max(y2 - y1, 1)
            anchors.append(
                SubtitleAnchor(
                    center_x=0.5,
                    center_y=((y1 + y2) / 2) / frame_height,
                    height=min(settings.SUBTITLE_ANCHOR_MAX_HEIGHT_RATIO, band_h / frame_height),
                    width=0.85,
                    language=Language.AUTO,
                    confidence=0.55,
                    source=f"{position_mode}_visual_band",
                    position_mode=position_mode,
                    debug_info={"visual_band": {"y1": y1, "y2": y2}},
                )
            )
        return anchors

    def _roi_to_absolute(
        self,
        roi_box: Tuple[int, int, int, int],
        frame_shape: Tuple[int, int, int],
        roi_start: int,
    ) -> Tuple[int, int, int, int]:
        x1, y1, x2, y2 = roi_box
        return (int(x1), int(y1 + roi_start), int(x2), int(y2 + roi_start))

    def _find_stable_regions(
        self,
        detections: List[dict],
        frame_shape: Tuple[int, int, int],
        total_frames: Optional[int] = None,
        position_mode: str = "bottom",
        source: str = "bottom_roi",
    ) -> Tuple[List[SubtitleAnchor], dict]:
        if not detections:
            return [], {"clusters": 0, "candidates": [], "accepted_anchor_count": 0}

        frame_height, frame_width = frame_shape[:2]
        band_start, band_end = self._get_position_band(position_mode)

        for det in detections:
            box = det["abs_box"]
            det["center_y"] = (box[1] + box[3]) / 2
            det["center_x"] = (box[0] + box[2]) / 2
            det["height"] = box[3] - box[1]
            det["width"] = box[2] - box[0]

        y_clusters = self._cluster_by_y_position(detections)
        anchors = []
        observed_frames = max(total_frames or 0, 1)
        candidates = []

        for cluster_index, cluster in enumerate(y_clusters):
            avg_y = float(np.mean([det["center_y"] for det in cluster]))
            avg_height = float(np.mean([det["height"] for det in cluster]))
            avg_width = float(np.mean([det["width"] for det in cluster]))
            avg_x = float(np.mean([det["center_x"] for det in cluster]))
            avg_confidence = float(np.mean([det["confidence"] for det in cluster]))
            frame_ids = {det["frame_idx"] for det in cluster if "frame_idx" in det}
            appearance_ratio = len(frame_ids) / observed_frames

            texts = [det.get("text", "") for det in cluster]
            normalized = [self._normalize_text(t) for t in texts if self._normalize_text(t)]
            unique_ratio = len(set(normalized)) / max(len(normalized), 1)
            center_prior = 1.0 - min(1.0, abs((avg_x / frame_width) - 0.5) * 2)
            width_ratio = avg_width / frame_width
            height_ratio = avg_height / frame_height
            center_y_ratio = avg_y / frame_height

            score_breakdown = {
                "confidence": settings.SUBTITLE_ANCHOR_SCORE_WEIGHT_CONFIDENCE * avg_confidence,
                "appearance": settings.SUBTITLE_ANCHOR_SCORE_WEIGHT_APPEARANCE * appearance_ratio,
                "text_variety": settings.SUBTITLE_ANCHOR_SCORE_WEIGHT_TEXT_VARIETY * unique_ratio,
                "center_prior": settings.SUBTITLE_ANCHOR_SCORE_WEIGHT_CENTER_PRIOR * center_prior,
            }
            score = float(sum(score_breakdown.values()))
            score_floor = max(self.min_confidence * 0.75, settings.SUBTITLE_ANCHOR_MIN_SCORE)

            reject_reasons = []
            if center_y_ratio < band_start or center_y_ratio > band_end:
                reject_reasons.append("outside_position_band")
            if appearance_ratio < self.min_appearance_ratio:
                reject_reasons.append("appearance_ratio_too_low")
            if width_ratio < settings.SUBTITLE_ANCHOR_MIN_WIDTH_RATIO or width_ratio > settings.SUBTITLE_ANCHOR_MAX_WIDTH_RATIO:
                reject_reasons.append("width_ratio_out_of_range")
            if height_ratio < settings.SUBTITLE_ANCHOR_MIN_HEIGHT_RATIO or height_ratio > settings.SUBTITLE_ANCHOR_MAX_HEIGHT_RATIO:
                reject_reasons.append("height_ratio_out_of_range")
            if score < score_floor:
                reject_reasons.append("score_below_threshold")

            candidate_info = {
                "cluster_index": cluster_index,
                "source": source,
                "sample_count": len(cluster),
                "frame_appearance_count": len(frame_ids),
                "appearance_ratio": round(appearance_ratio, 4),
                "avg_confidence": round(avg_confidence, 4),
                "unique_ratio": round(unique_ratio, 4),
                "center_prior": round(center_prior, 4),
                "avg_center_x_ratio": round(avg_x / frame_width, 4),
                "avg_center_y_ratio": round(center_y_ratio, 4),
                "avg_width_ratio": round(width_ratio, 4),
                "avg_height_ratio": round(height_ratio, 4),
                "score": round(score, 4),
                "score_floor": round(score_floor, 4),
                "score_breakdown": {k: round(v, 4) for k, v in score_breakdown.items()},
                "sample_texts": texts[:5],
                "accepted": not reject_reasons,
                "reject_reasons": reject_reasons,
            }
            candidates.append(candidate_info)

            if reject_reasons:
                continue

            language = self._detect_language(texts)
            anchors.append(
                SubtitleAnchor(
                    center_x=avg_x / frame_width,
                    center_y=center_y_ratio,
                    height=height_ratio,
                    width=width_ratio,
                    language=language,
                    confidence=min(0.99, score),
                    source=source,
                    position_mode=position_mode,
                    debug_info=candidate_info,
                )
            )

        return anchors, {
            "clusters": len(y_clusters),
            "candidates": candidates,
            "accepted_anchor_count": len(anchors),
        }

    def _cluster_by_y_position(self, detections: List[dict]) -> List[List[dict]]:
        if not detections:
            return []

        sorted_dets = sorted(detections, key=lambda d: d["center_y"])
        clusters = []
        current_cluster = [sorted_dets[0]]

        for det in sorted_dets[1:]:
            avg_y = np.mean([d["center_y"] for d in current_cluster])
            avg_height = np.mean([d["height"] for d in current_cluster])
            tolerance = settings.SUBTITLE_ANCHOR_Y_TOLERANCE_RATIO * avg_height * 2

            if abs(det["center_y"] - avg_y) < tolerance:
                current_cluster.append(det)
                continue

            if len(current_cluster) >= settings.SUBTITLE_ANCHOR_MIN_CLUSTER_SIZE:
                clusters.append(current_cluster)
            current_cluster = [det]

        if len(current_cluster) >= settings.SUBTITLE_ANCHOR_MIN_CLUSTER_SIZE:
            clusters.append(current_cluster)

        return clusters

    def _detect_language(self, texts: List[str]) -> Language:
        chinese_chars = 0
        english_chars = 0
        japanese_chars = 0
        korean_chars = 0

        for text in texts:
            for char in text:
                if "\u4e00" <= char <= "\u9fff":
                    chinese_chars += 1
                elif "\u3040" <= char <= "\u30ff":
                    japanese_chars += 1
                elif "\uac00" <= char <= "\ud7a3":
                    korean_chars += 1
                elif char.isalpha():
                    english_chars += 1

        total = chinese_chars + english_chars + japanese_chars + korean_chars
        if total == 0:
            return Language.AUTO

        max_count = max(chinese_chars, english_chars, japanese_chars, korean_chars)
        if max_count == chinese_chars and chinese_chars > 0:
            return Language.CHINESE
        if max_count == english_chars and english_chars > 0:
            return Language.ENGLISH
        if max_count == japanese_chars and japanese_chars > 0:
            return Language.JAPANESE
        if max_count == korean_chars and korean_chars > 0:
            return Language.KOREAN
        return Language.AUTO

    def _normalize_text(self, text: str) -> str:
        text = text.strip().lower()
        text = re.sub(r"\s+", "", text)
        text = re.sub(r"[^\w\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7a3]", "", text)
        return text

    def refine_anchor(self, anchor: SubtitleAnchor, frame: np.ndarray) -> Tuple[int, int, int, int]:
        h, w = frame.shape[:2]
        center_x = int(anchor.center_x * w)
        center_y = int(anchor.center_y * h)
        box_height = int(anchor.height * h)
        box_width = int(anchor.width * w)

        margin = 10
        x1 = max(0, center_x - box_width // 2 - margin)
        y1 = max(0, center_y - box_height // 2 - margin)
        x2 = min(w, center_x + box_width // 2 + margin)
        y2 = min(h, center_y + box_height // 2 + margin)
        return (x1, y1, x2, y2)

    def get_default_anchor(
        self,
        frame_height: int,
        frame_width: int,
        roi_bottom_ratio: float | None = None,
        position_mode: str = "bottom",
    ) -> SubtitleAnchor:
        start_ratio, end_ratio = self._get_position_band(position_mode, roi_bottom_ratio)
        center_y = (start_ratio + end_ratio) / 2.0
        height = max(0.08, min(0.35, (end_ratio - start_ratio) * 0.45))
        width = 0.8 if position_mode != "middle" else 0.75
        return SubtitleAnchor(
            center_x=0.5,
            center_y=center_y,
            height=height,
            width=width,
            language=Language.AUTO,
            confidence=0.5,
            source=f"default_{position_mode}",
            position_mode=position_mode,
            debug_info={
                "fallback": True,
                "position_band": {
                    "start_ratio": round(start_ratio, 4),
                    "end_ratio": round(end_ratio, 4),
                },
            },
        )
