"""Subtitle extraction service - coordinates the complete pipeline"""

import os
import logging
import time
import math
from difflib import SequenceMatcher
from typing import Optional, List, Dict, Any, Tuple, Callable
from pathlib import Path
import re
import cv2
import numpy as np

from translip.ocr.config import settings
from translip.ocr.core.video_processor import VideoProcessor
from translip.ocr.core.subtitle_detector import SubtitleDetector
from translip.ocr.core.ocr_engine import OCREngine, OCREngineRuntimeError
from translip.ocr.core.subtitle_merger import SubtitleMerger
from translip.ocr.core.srt_generator import SRTGenerator
from translip.ocr.models.domain import (
    SubtitleAnchor, Subtitle, SubtitleExtractionResult,
    Language, DetectedText
)
from translip.ocr.utils.geometry import box_to_polygon, crop_by_geometry, merge_polygons, polygon_to_rotated_box
from translip.ocr.utils.runtime_diagnostics import log_runtime_snapshot
from translip.ocr.utils.textness import analyze_textness, should_run_ocr

logger = logging.getLogger(__name__)


def _clamp_unit_interval(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _safe_text_similarity(left: str, right: str) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return float(SequenceMatcher(a=left, b=right).ratio())


def _has_cjk_text(text: str) -> bool:
    return any('\u4e00' <= ch <= '\u9fff' for ch in text or "")


class SubtitleService:
    """
    Subtitle extraction service - coordinates the complete pipeline

    Pipeline:
    1. Video preprocessing
    2. Subtitle region detection (anchor discovery)
    3. Main detection (sampling + OCR)
    4. Subtitle merging
    5. SRT generation
    """

    def __init__(self):
        self.ocr_engine = None
        self.detector = None
        self.merger = None
        self.prefilter_enabled = settings.SUBTITLE_PREFILTER_ENABLED
        self.localizer_profile = self._build_localizer_profile()
        self.subtitle_extraction_mode = "conservative"
        self.variety_recall_enabled = False
        self.manual_region_active = False

    def _build_localizer_profile(self, **overrides: Optional[float]) -> Dict[str, float]:
        profile = {
            "min_width_ratio": float(settings.SUBTITLE_LOCALIZER_MIN_WIDTH_RATIO),
            "direct_accept_margin": float(settings.SUBTITLE_LOCALIZER_DIRECT_ACCEPT_MARGIN),
            "overlay_track_threshold": float(settings.SUBTITLE_LOCALIZER_OVERLAY_TRACK_THRESHOLD),
            "credit_column_score_threshold": float(settings.SUBTITLE_LOCALIZER_CREDIT_COLUMN_SCORE_THRESHOLD),
            "signage_score_threshold": float(settings.SUBTITLE_LOCALIZER_SIGNAGE_SCORE_THRESHOLD),
            "signage_strict_width_ratio": float(settings.SUBTITLE_LOCALIZER_SIGNAGE_STRICT_WIDTH_RATIO),
            "dense_text_scene_score_threshold": float(settings.SUBTITLE_LOCALIZER_DENSE_TEXT_SCENE_SCORE_THRESHOLD),
        }
        for key, value in overrides.items():
            if value is None:
                continue
            profile[key] = float(value)
        return profile

    def _normalize_extraction_mode(self, mode: Optional[str]) -> str:
        raw_mode = getattr(mode, "value", mode)
        normalized = (str(raw_mode or "conservative").strip().lower() or "conservative")
        if normalized not in {"conservative", "balanced", "variety_recall"}:
            logger.warning("unknown subtitle_extraction_mode=%s, fallback to conservative", mode)
            return "conservative"
        return normalized

    def _normalize_skip_seconds(self, value: Optional[float]) -> float:
        try:
            seconds = float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0
        if not math.isfinite(seconds):
            return 0.0
        return max(0.0, seconds)

    def _normalize_manual_subtitle_region(self, region: Optional[Any]) -> Optional[Dict[str, float]]:
        if region is None:
            return None
        if hasattr(region, "model_dump"):
            region = region.model_dump(mode="python")
        elif hasattr(region, "dict"):
            region = region.dict()
        if not isinstance(region, dict):
            return None

        try:
            center_x = float(region.get("center_x"))
            center_y = float(region.get("center_y"))
            width = float(region.get("width"))
            height = float(region.get("height"))
        except (TypeError, ValueError):
            return None
        if not all(math.isfinite(value) for value in (center_x, center_y, width, height)):
            return None

        width = min(1.0, max(0.01, width))
        height = min(1.0, max(0.01, height))
        center_x = 0.5 if width >= 1.0 else max(width / 2.0, min(1.0 - width / 2.0, center_x))
        center_y = 0.5 if height >= 1.0 else max(height / 2.0, min(1.0 - height / 2.0, center_y))

        return {
            "center_x": round(center_x, 6),
            "center_y": round(center_y, 6),
            "width": round(width, 6),
            "height": round(height, 6),
        }

    def _build_manual_anchor(self, region: Dict[str, float]) -> SubtitleAnchor:
        center_y = float(region["center_y"])
        if center_y <= 0.34:
            position_mode = "top"
        elif center_y < 0.66:
            position_mode = "middle"
        else:
            position_mode = "bottom"
        return SubtitleAnchor(
            center_x=region["center_x"],
            center_y=region["center_y"],
            width=region["width"],
            height=region["height"],
            language=Language.AUTO,
            confidence=1.0,
            source="manual_region",
            position_mode=position_mode,
            debug_info={
                "manual": True,
                "region": region,
                "inferred_position_mode": position_mode,
            },
        )

    def _resolve_extraction_time_window(
        self,
        duration: float,
        skip_start_seconds: Optional[float],
        skip_end_seconds: Optional[float],
    ) -> Tuple[float, float]:
        video_duration = max(0.0, float(duration or 0.0))
        start_time = min(video_duration, self._normalize_skip_seconds(skip_start_seconds))
        end_time = max(0.0, video_duration - self._normalize_skip_seconds(skip_end_seconds))
        if end_time < start_time:
            end_time = start_time
        return start_time, end_time

    def _initialize(
        self,
        language: str = 'ch',
        use_angle_cls: Optional[bool] = None,
        det_db_thresh: Optional[float] = None,
        det_db_box_thresh: Optional[float] = None,
        prefilter_enabled: Optional[bool] = None,
    ):
        """Initialize per-task OCR and detector components without mutating global settings."""
        resolved_use_angle_cls = settings.PADDLEOCR_USE_ANGLE_CLS if use_angle_cls is None else bool(use_angle_cls)
        resolved_det_db_thresh = _clamp_unit_interval(
            settings.PADDLEOCR_DET_DB_THRESH if det_db_thresh is None else det_db_thresh
        )
        resolved_det_db_box_thresh = _clamp_unit_interval(
            settings.PADDLEOCR_DET_DB_BOX_THRESH if det_db_box_thresh is None else det_db_box_thresh
        )
        resolved_prefilter_enabled = settings.SUBTITLE_PREFILTER_ENABLED if prefilter_enabled is None else bool(prefilter_enabled)

        needs_new_engine = (
            self.ocr_engine is None
            or self.ocr_engine.lang != language
            or self.ocr_engine.use_angle_cls != resolved_use_angle_cls
            or self.ocr_engine.det_db_thresh != resolved_det_db_thresh
            or self.ocr_engine.det_db_box_thresh != resolved_det_db_box_thresh
        )

        if needs_new_engine:
            self.ocr_engine = OCREngine(
                lang=language,
                use_angle_cls=resolved_use_angle_cls,
                det_db_thresh=resolved_det_db_thresh,
                det_db_box_thresh=resolved_det_db_box_thresh,
            )
            self.detector = None

        if self.detector is None:
            self.detector = SubtitleDetector(
                self.ocr_engine,
                prefilter_enabled=resolved_prefilter_enabled,
            )
        else:
            self.detector.prefilter_enabled = resolved_prefilter_enabled

        if self.merger is None:
            self.merger = SubtitleMerger(
                similarity_threshold=settings.SUBTITLE_MERGE_THRESHOLD,
                time_tolerance=settings.SUBTITLE_TIME_TOLERANCE,
                attach_short_prefixes=settings.SUBTITLE_ATTACH_SHORT_PREFIX,
            )

        self.prefilter_enabled = resolved_prefilter_enabled

    def extract_subtitles(
        self,
        video_path: str,
        language: str = 'auto',
        sample_interval: float = 0.2,
        detect_region: bool = True,
        roi_bottom_ratio: float = 0.35,
        merge_threshold: float = 0.8,
        time_tolerance: float = settings.SUBTITLE_TIME_TOLERANCE,
        attach_short_prefixes: bool = settings.SUBTITLE_ATTACH_SHORT_PREFIX,
        skip_start_seconds: float = settings.SUBTITLE_SKIP_START_SECONDS_DEFAULT,
        skip_end_seconds: float = settings.SUBTITLE_SKIP_END_SECONDS_DEFAULT,
        subtitle_position_mode: str = "auto",
        subtitle_geometry_mode: str = "axis_aligned",
        subtitle_extraction_mode: str = "conservative",
        use_angle_cls: Optional[bool] = None,
        det_db_thresh: Optional[float] = None,
        det_db_box_thresh: Optional[float] = None,
        prefilter_enabled: Optional[bool] = None,
        localizer_min_width_ratio: Optional[float] = None,
        localizer_direct_accept_margin: Optional[float] = None,
        localizer_overlay_track_threshold: Optional[float] = None,
        localizer_credit_column_score_threshold: Optional[float] = None,
        localizer_signage_score_threshold: Optional[float] = None,
        subtitle_region: Optional[Any] = None,
        task_id: Optional[str] = None,
        progress_callback: Optional[Callable[[int, str, Optional[dict]], None]] = None,
        cancel_checker: Optional[Callable[[], bool]] = None,
    ) -> SubtitleExtractionResult:
        """
        Extract subtitles from video

        Args:
            video_path: Path to video file
            language: Language code ('auto', 'ch', 'en', 'korean', 'japan')
            sample_interval: Sampling interval in seconds
            detect_region: Whether to auto-detect subtitle region
            roi_bottom_ratio: Bottom ROI ratio (when detect_region=False)
            merge_threshold: Merge similarity threshold
            skip_start_seconds: Seconds to skip from the beginning before OCR
            skip_end_seconds: Seconds to skip from the end before OCR

        Returns:
            SubtitleExtractionResult
        """
        started_at = time.monotonic()
        task_label = task_id or "-"
        manual_region = self._normalize_manual_subtitle_region(subtitle_region)
        self.subtitle_extraction_mode = self._normalize_extraction_mode(subtitle_extraction_mode)
        self.manual_region_active = manual_region is not None
        self.variety_recall_enabled = (
            self.subtitle_extraction_mode == "variety_recall"
            and manual_region is None
        )
        if manual_region is not None:
            detect_region = False
        elif self.subtitle_extraction_mode == "conservative" and (subtitle_position_mode or "auto").lower() == "auto":
            subtitle_position_mode = "bottom"
        if self.variety_recall_enabled:
            detect_region = False
            subtitle_position_mode = "bottom"
            roi_bottom_ratio = min(0.35, max(0.25, float(roi_bottom_ratio or 0.30)))
            time_tolerance = min(float(time_tolerance), 0.65)
            attach_short_prefixes = False
        skip_start_seconds = self._normalize_skip_seconds(skip_start_seconds)
        skip_end_seconds = self._normalize_skip_seconds(skip_end_seconds)
        log_runtime_snapshot(logger, logging.INFO, "subtitle pipeline open task_id=%s video_path=%s", task_label, video_path)
        self._raise_if_cancelled(cancel_checker)

        # Initialize
        lang = language if language != 'auto' else 'ch'
        self._initialize(
            lang,
            use_angle_cls=use_angle_cls,
            det_db_thresh=det_db_thresh,
            det_db_box_thresh=det_db_box_thresh,
            prefilter_enabled=prefilter_enabled,
        )
        self.localizer_profile = self._build_localizer_profile(
            min_width_ratio=localizer_min_width_ratio,
            direct_accept_margin=localizer_direct_accept_margin,
            overlay_track_threshold=localizer_overlay_track_threshold,
            credit_column_score_threshold=localizer_credit_column_score_threshold,
            signage_score_threshold=localizer_signage_score_threshold,
        )
        self._emit_progress(
            progress_callback,
            25,
            "ocr_initialized",
            {"task_id": task_label, "language": lang},
        )
        self._emit_progress(
            progress_callback,
            26,
            "ocr_model_loading",
            {"language": lang},
        )
        warm_results = self.ocr_engine.warm_up([lang])
        warm_result = warm_results[0] if warm_results else {"lang": lang, "ok": False, "runtime_ms": 0, "error": "no warm-up result"}
        if not warm_result.get("ok"):
            raise OCREngineRuntimeError(
                warm_result.get("error") or f"Failed to warm up OCR model for lang={lang}"
            )
        self._raise_if_cancelled(cancel_checker)
        self._emit_progress(
            progress_callback,
            29,
            "ocr_model_ready",
            {
                "language": warm_result.get("lang", lang),
                "runtime_ms": int(warm_result.get("runtime_ms") or 0),
            },
        )

        # Update merger parameters
        self.merger.similarity_threshold = merge_threshold
        self.merger.time_tolerance = max(0.1, float(time_tolerance))
        self.merger.attach_short_prefixes = bool(attach_short_prefixes)

        localization_failure_debug: List[Dict[str, Any]] = []

        # Phase 1: Video preprocessing
        with VideoProcessor(video_path) as processor:
            total_frames = processor.total_frames
            duration = processor.duration
            extraction_start, extraction_end = self._resolve_extraction_time_window(
                duration,
                skip_start_seconds,
                skip_end_seconds,
            )
            effective_duration = max(0.0, extraction_end - extraction_start)
            frame_interval = max(1, int(processor.fps * sample_interval))
            effective_total_frames = max(0, int(math.ceil(effective_duration * max(float(processor.fps), 1.0))))
            estimated_frames = (
                max(1, int(math.ceil(effective_total_frames / frame_interval)))
                if effective_total_frames > 0 else 0
            )
            detector_progress_callback = self._build_region_progress_callback(progress_callback)
            logger.info(
                "subtitle video opened task_id=%s total_frames=%s duration=%s extraction_start=%s extraction_end=%s skip_start_seconds=%s skip_end_seconds=%s width=%s height=%s fps=%s",
                task_label,
                total_frames,
                duration,
                extraction_start,
                extraction_end,
                skip_start_seconds,
                skip_end_seconds,
                processor.width,
                processor.height,
                processor.fps,
            )
            log_runtime_snapshot(logger, logging.INFO, "subtitle video metadata captured task_id=%s", task_label)
            self._emit_progress(
                progress_callback,
                30,
                "video_opened",
                {
                    "total_frames": total_frames,
                    "duration": round(float(duration), 3),
                    "extraction_start": round(float(extraction_start), 3),
                    "extraction_end": round(float(extraction_end), 3),
                    "skip_start_seconds": round(float(skip_start_seconds), 3),
                    "skip_end_seconds": round(float(skip_end_seconds), 3),
                    "estimated_sample_frames": estimated_frames,
                },
            )

            # Phase 2: Subtitle region detection (pre-detection)
            anchors = []
            if manual_region is not None:
                anchors = [self._build_manual_anchor(manual_region)]
                self.detector.last_debug_info = {
                    "requested_position_mode": subtitle_position_mode,
                    "manual_region": manual_region,
                    "search_modes": ["manual"],
                    "stages": [
                        {
                            "stage": "manual_region",
                            "position_mode": "manual",
                            "selected": True,
                        }
                    ],
                    "selected_anchor_count": 1,
                    "selected_anchors": [
                        {
                            "center_x": round(anchors[0].center_x, 4),
                            "center_y": round(anchors[0].center_y, 4),
                            "width": round(anchors[0].width, 4),
                            "height": round(anchors[0].height, 4),
                            "confidence": round(anchors[0].confidence, 4),
                            "source": anchors[0].source,
                            "position_mode": anchors[0].position_mode,
                        }
                    ],
                }
                logger.info(
                    "subtitle manual region selected task_id=%s region=%s",
                    task_label,
                    manual_region,
                )
            elif detect_region:
                self._raise_if_cancelled(cancel_checker)
                logger.info("subtitle region detection start task_id=%s", task_label)
                # Extract pre-detection frames
                pre_detection_target = self._resolve_detection_sample_count(effective_duration)
                pre_frames, pre_timestamps, pre_detection_debug = self._collect_pre_detection_frames(
                    processor,
                    subtitle_position_mode,
                    roi_bottom_ratio,
                    start_time=extraction_start,
                    end_time=extraction_end,
                )
                logger.info(
                    "subtitle pre-detection samples selected task_id=%s target=%s actual=%s samples=%s",
                    task_label,
                    pre_detection_target,
                    len(pre_frames),
                    pre_detection_debug,
                )
                for current, ts in enumerate(pre_timestamps, start=1):
                    self._raise_if_cancelled(cancel_checker)
                    self._emit_progress(
                        progress_callback,
                        self._compute_sampling_detection_progress(current, pre_detection_target),
                        "sampling_detection_frames",
                        {
                            "current": current,
                            "total": pre_detection_target,
                            "timestamp": round(float(ts), 3),
                        },
                    )

                # Detect subtitle regions
                if pre_frames:
                    self._raise_if_cancelled(cancel_checker)
                    anchors = self.detector.detect_subtitle_region(
                        pre_frames,
                        pre_timestamps,
                        position_mode=subtitle_position_mode,
                        roi_ratio=roi_bottom_ratio,
                        progress_callback=detector_progress_callback,
                    )
                    if (
                        subtitle_position_mode != "auto"
                        and self._anchors_need_auto_fallback(anchors)
                    ):
                        logger.info(
                            "subtitle region detection weak anchors fallback task_id=%s requested_mode=%s anchors=%s retry_mode=auto",
                            task_label,
                            subtitle_position_mode,
                            [anchor.source for anchor in anchors],
                        )
                        anchors = self.detector.detect_subtitle_region(
                            pre_frames,
                            pre_timestamps,
                            position_mode="auto",
                            roi_ratio=roi_bottom_ratio,
                            progress_callback=detector_progress_callback,
                        )
                logger.info(
                    "subtitle region detection done task_id=%s pre_frames=%s anchors=%s",
                    task_label,
                    len(pre_frames),
                    len(anchors),
                )
                log_runtime_snapshot(logger, logging.INFO, "subtitle region detection snapshot task_id=%s", task_label)

                if not anchors:
                    logger.warning("No subtitle anchors detected, using default bottom ROI task_id=%s", task_label)
                    # Use default bottom region
                    anchors = [self.detector.get_default_anchor(
                        processor.height,
                        processor.width,
                        roi_bottom_ratio,
                        position_mode=subtitle_position_mode if subtitle_position_mode != "auto" else "bottom",
                    )]
            else:
                # Use specified bottom ROI
                anchors = [self.detector.get_default_anchor(
                    processor.height,
                    processor.width,
                    roi_bottom_ratio,
                    position_mode=subtitle_position_mode if subtitle_position_mode != "auto" else "bottom",
                )]
            self._emit_progress(
                progress_callback,
                50,
                "region_ready",
                {"anchors": len(anchors), "detect_region": bool(detect_region)},
            )

            # Phase 3: Main detection - sample and recognize
            logger.info(
                "subtitle main detection start task_id=%s sample_interval=%s extraction_start=%s extraction_end=%s anchors=%s subtitle_geometry_mode=%s",
                task_label,
                sample_interval,
                extraction_start,
                extraction_end,
                len(anchors),
                subtitle_geometry_mode,
            )

            all_detections = []
            processed_frames = 0
            prefilter_skipped_regions = 0
            reused_regions = 0
            empty_skipped_regions = 0
            secondary_skipped_regions = 0
            last_reported_progress = 50

            tracker_states = [self._create_tracker_state() for _ in anchors]
            for frame, timestamp, frame_idx in processor.extract_frames_by_interval(
                sample_interval,
                start_time=extraction_start,
                end_time=extraction_end,
            ):
                self._raise_if_cancelled(cancel_checker)
                processed_frames += 1
                loop_progress = min(92, 51 + int(round((processed_frames / max(1, estimated_frames)) * 41)))
                if processed_frames == 1 or loop_progress > last_reported_progress:
                    self._emit_progress(
                        progress_callback,
                        loop_progress,
                        "ocr_processing",
                        {
                            "processed_frames": processed_frames,
                            "estimated_frames": estimated_frames,
                            "detections": len(all_detections),
                            "timestamp": round(float(timestamp), 3),
                        },
                    )
                    last_reported_progress = loop_progress

                # Recognize in each anchor region
                for anchor_idx, anchor in enumerate(anchors):
                    self._raise_if_cancelled(cancel_checker)
                    tracker_state = tracker_states[anchor_idx]
                    # Refine anchor region
                    search_region = self._resolve_detection_region(anchor, frame, tracker_state)
                    rx1, ry1, rx2, ry2 = search_region
                    region_view = frame[ry1:ry2, rx1:rx2]
                    should_ocr, textness_debug = should_run_ocr(
                        region_view,
                        enabled=self.prefilter_enabled,
                    )
                    if not should_ocr:
                        prefilter_skipped_regions += 1
                        self._register_tracker_miss(tracker_state, timestamp=timestamp)
                        continue

                    region_signature = self._compute_region_signature(region_view)
                    reused_detection = self._build_reused_detection(
                        tracker_state=tracker_state,
                        signature=region_signature,
                        timestamp=timestamp,
                        frame_index=frame_idx,
                    )
                    if reused_detection is not None:
                        self._register_tracker_success(tracker_state, timestamp)
                        reused_regions += 1
                        all_detections.append(reused_detection)
                        continue

                    if self._maybe_skip_confirmed_empty_region(tracker_state, region_signature):
                        empty_skipped_regions += 1
                        self._register_tracker_miss(
                            tracker_state,
                            timestamp=timestamp,
                            signature=region_signature,
                            clear_pending=tracker_state.get("pending_candidate") is None,
                        )
                        continue

                    # OCR recognition
                    ocr_lang = None
                    if anchor.language != Language.AUTO:
                        ocr_lang = anchor.language.value

                    coarse_detections = self.ocr_engine.recognize_in_region(
                        frame, search_region, ocr_lang
                    )
                    localized = self._localize_subtitle_region(
                        coarse_detections,
                        search_region=search_region,
                        frame_shape=frame.shape,
                        anchor=anchor,
                        tracker_state=tracker_state,
                        timestamp=timestamp,
                    )
                    if not localized:
                        confirmed_empty = not self._clean_text_detections(coarse_detections)
                        self._register_tracker_miss(
                            tracker_state,
                            timestamp=timestamp,
                            signature=region_signature,
                            clear_pending=tracker_state.get("pending_candidate") is None,
                        )
                        if confirmed_empty and tracker_state.get("pending_candidate") is None:
                            self._arm_empty_region_skip(tracker_state, region_signature)
                        continue

                    recognition_region = localized["recognition_region"]
                    secondary_pass_skipped = self._should_skip_secondary_recognition(
                        localized,
                        search_region,
                    )
                    if secondary_pass_skipped:
                        secondary_skipped_regions += 1
                        final_detections = localized["selected_detections"]
                    else:
                        final_detections = self.ocr_engine.recognize_in_region(
                            frame,
                            recognition_region,
                            ocr_lang,
                        )
                        final_detections = self._filter_detections_to_focus_box(
                            final_detections,
                            tuple(int(v) for v in localized["debug"]["tight_box"]),
                        )
                    final_detections = self._filter_variety_recall_frame_detections(
                        final_detections,
                        frame.shape,
                    )
                    if not final_detections:
                        final_detections = localized["selected_detections"]
                        final_detections = self._filter_variety_recall_frame_detections(
                            final_detections,
                            frame.shape,
                        )

                    merged_detection = self._merge_detections_in_frame(final_detections)
                    if self._is_implausible_merged_subtitle(merged_detection):
                        self._register_tracker_miss(
                            tracker_state,
                            timestamp=timestamp,
                            signature=region_signature,
                        )
                        continue
                    secondary_recognition = self._apply_selected_geometry_recognition(
                        frame=frame,
                        detection=merged_detection,
                        geometry_mode=subtitle_geometry_mode,
                        ocr_lang=ocr_lang,
                    )
                    merged_detection["debug_info"] = {
                        "textness_prefilter": textness_debug,
                        "anchor_source": anchor.source,
                        "anchor_position_mode": anchor.position_mode,
                        "processing_geometry_mode": subtitle_geometry_mode,
                        "search_region": [int(v) for v in search_region],
                        "localization": localized["debug"],
                        "coarse_detection_count": len(coarse_detections),
                        "final_detection_count": len(final_detections),
                        "secondary_pass_skipped": secondary_pass_skipped,
                        "ocr_options": {
                            "use_angle_cls": self.ocr_engine.use_angle_cls,
                            "det_db_thresh": round(float(self.ocr_engine.det_db_thresh), 4),
                            "det_db_box_thresh": round(float(self.ocr_engine.det_db_box_thresh), 4),
                            "prefilter_enabled": self.prefilter_enabled,
                        },
                        "secondary_recognition": secondary_recognition,
                    }
                    merged_detection["recognition_region"] = tuple(int(v) for v in recognition_region)
                    optimized_box = self._self_optimize_box(
                        merged_detection["box"],
                        merged_detection["confidence"],
                        tracker_state,
                        frame.shape
                    )
                    merged_detection["box"] = optimized_box
                    self._update_tracker_reuse_candidate(
                        tracker_state=tracker_state,
                        detection=merged_detection,
                        signature=region_signature,
                        timestamp=timestamp,
                    )

                    detected_text = DetectedText(
                        text=merged_detection['text'],
                        confidence=merged_detection['confidence'],
                        box=merged_detection['box'],
                        polygon=merged_detection.get('polygon'),
                        rotated_box=merged_detection.get('rotated_box'),
                        recognition_region=merged_detection.get('recognition_region'),
                        recognition_executed=True,
                        sample_debug=merged_detection.get("debug_info"),
                        timestamp=timestamp,
                        frame_index=frame_idx
                    )
                    all_detections.append(detected_text)

                if processed_frames == 1 or processed_frames % settings.SUBTITLE_PROGRESS_LOG_EVERY_FRAMES == 0:
                    log_runtime_snapshot(
                        logger,
                        logging.INFO,
                        "subtitle progress task_id=%s processed_frames=%s detections=%s timestamp=%.3f",
                        task_label,
                        processed_frames,
                        len(all_detections),
                        timestamp,
                    )
            logger.info(
                "subtitle main detection done task_id=%s processed_frames=%s detections=%s prefilter_skipped_regions=%s reused_regions=%s empty_skipped_regions=%s secondary_skipped_regions=%s",
                task_label,
                processed_frames,
                len(all_detections),
                prefilter_skipped_regions,
                reused_regions,
                empty_skipped_regions,
                secondary_skipped_regions,
            )
            localization_failure_debug = self._collect_localization_failure_debug(tracker_states, anchors)
            self._emit_progress(
                progress_callback,
                94,
                "ocr_done",
                {
                    "processed_frames": processed_frames,
                    "detections": len(all_detections),
                    "reused_regions": reused_regions,
                    "prefilter_skipped_regions": prefilter_skipped_regions,
                    "empty_skipped_regions": empty_skipped_regions,
                    "secondary_skipped_regions": secondary_skipped_regions,
                },
            )

        # Phase 4: Merge and generate subtitles
        logger.info("subtitle merge start task_id=%s detections=%s", task_label, len(all_detections))
        self._emit_progress(
            progress_callback,
            97,
            "merging",
            {"detections": len(all_detections)},
        )

        all_detections = self._filter_repetitive_anchor_overlays(all_detections, anchors)
        self._raise_if_cancelled(cancel_checker)
        subtitles = self.merger.merge_detected_texts(all_detections)
        subtitles = self.merger.filter_low_confidence(subtitles, settings.SUBTITLE_MIN_CONFIDENCE)
        subtitles = self.merger.deduplicate_similar(subtitles)
        subtitles = self._filter_competing_nonbottom_subtitles(subtitles, anchors)
        subtitles = self._filter_dense_scene_overlay_subtitles(subtitles)
        subtitles = self._filter_structural_non_dialogue_subtitles(subtitles)
        subtitles = self._filter_visual_track_non_dialogue_subtitles(subtitles)
        subtitles = self._filter_tail_non_dialogue_sequences(subtitles)
        subtitles = self._filter_credit_roll_sequences(subtitles)
        subtitles = self._filter_variety_recall_overlay_subtitles(subtitles)
        subtitles = self._filter_main_temporal_window(subtitles, video_duration=duration)
        subtitles = self._filter_subtitles_to_time_window(
            subtitles,
            start_time=extraction_start,
            end_time=extraction_end,
        )

        # Detect final language
        detected_lang = Language.AUTO
        if anchors:
            detected_lang = anchors[0].language
        anchor_debug = dict(self.detector.last_debug_info or {})
        if localization_failure_debug:
            anchor_debug["localization_failures"] = localization_failure_debug

        result = SubtitleExtractionResult(
            subtitles=subtitles,
            anchors=anchors,
            total_frames=total_frames,
            processed_frames=processed_frames,
            duration=duration,
            language=detected_lang,
            anchor_debug=anchor_debug,
        )

        logger.info(
            "subtitle pipeline done task_id=%s subtitles=%s processed_frames=%s runtime_ms=%s",
            task_label,
            len(subtitles),
            processed_frames,
            int((time.monotonic() - started_at) * 1000),
        )
        log_runtime_snapshot(logger, logging.INFO, "subtitle pipeline final snapshot task_id=%s", task_label)
        self._emit_progress(
            progress_callback,
            99,
            "finalizing",
            {"subtitles": len(subtitles), "processed_frames": processed_frames},
        )
        return result

    def _emit_progress(
        self,
        progress_callback: Optional[Callable[[int, str, Optional[dict]], None]],
        progress: int,
        stage: str,
        details: Optional[dict] = None,
    ) -> None:
        if progress_callback is None:
            return
        try:
            progress_callback(progress, stage, details)
        except Exception:
            logger.exception("Progress callback failed stage=%s progress=%s", stage, progress)

    def _raise_if_cancelled(self, cancel_checker: Optional[Callable[[], bool]]) -> None:
        if cancel_checker is None:
            return
        if cancel_checker():
            raise RuntimeError("Task cancelled")

    def _compute_sampling_detection_progress(self, current: int, total: int) -> int:
        fraction = current / max(1, total)
        return min(35, 31 + int(round(fraction * 4)))

    def _anchors_need_auto_fallback(self, anchors: List[SubtitleAnchor]) -> bool:
        if not anchors:
            return True

        for anchor in anchors:
            source = (anchor.source or "").lower()
            debug_info = anchor.debug_info or {}
            is_weak_anchor = (
                source.endswith("visual_band")
                or source.startswith("default_")
                or "visual_band" in debug_info
            )
            if not is_weak_anchor:
                return False
        return True

    def _resolve_detection_sample_count(self, duration: float) -> int:
        base_count = max(1, int(settings.SUBTITLE_DETECTION_SAMPLE_RATE))
        max_count = max(base_count, int(settings.SUBTITLE_DETECTION_SAMPLE_RATE_MAX))
        target_segment_seconds = max(10.0, float(settings.SUBTITLE_DETECTION_TARGET_SEGMENT_SECONDS))
        adaptive_count = int(math.ceil(max(0.0, float(duration)) / target_segment_seconds)) if duration > 0 else base_count
        return min(max_count, max(base_count, adaptive_count))

    def _score_frame_for_pre_detection(
        self,
        frame: np.ndarray,
        position_mode: str,
        roi_ratio: float,
    ) -> float:
        if self.detector is None or self.ocr_engine is None:
            return 0.0

        best_score = 0.0
        for mode in self.detector._resolve_search_modes(position_mode):
            roi_frame, _ = self.detector._extract_focus_roi(frame, mode, roi_ratio)
            should_probe, metrics = should_run_ocr(roi_frame, enabled=self.prefilter_enabled)
            if not should_probe:
                score = float(analyze_textness(roi_frame).get("score") or 0.0) * 0.15
                if score > best_score:
                    best_score = score
                continue

            detections = self.ocr_engine.detect_text(roi_frame)
            roi_height, roi_width = roi_frame.shape[:2]
            score = 0.0
            for det in detections:
                box = det.get("box")
                if not box:
                    continue
                width_ratio = max(0.0, min(1.0, (box[2] - box[0]) / max(roi_width, 1)))
                height_ratio = max(0.0, min(1.0, (box[3] - box[1]) / max(roi_height, 1)))
                center_x_ratio = ((box[0] + box[2]) / 2) / max(roi_width, 1)
                center_prior = 1.0 - min(1.0, abs(center_x_ratio - 0.5) * 2.0)
                detection_score = (
                    0.55 * float(det.get("confidence") or 0.0) +
                    0.30 * min(1.0, width_ratio / 0.35) +
                    0.15 * center_prior
                )
                if width_ratio < 0.04 or height_ratio > 0.45:
                    detection_score *= 0.6
                score = max(score, detection_score)
            if score > best_score:
                best_score = score
        return best_score

    def _collect_pre_detection_frames(
        self,
        processor: VideoProcessor,
        position_mode: str,
        roi_ratio: float,
        start_time: float = 0.0,
        end_time: Optional[float] = None,
    ) -> Tuple[List[np.ndarray], List[float], List[dict]]:
        video_duration = max(0.0, float(processor.duration or 0.0))
        extraction_start = min(video_duration, self._normalize_skip_seconds(start_time))
        extraction_end = video_duration if end_time is None else min(video_duration, self._normalize_skip_seconds(end_time))
        if extraction_end < extraction_start:
            extraction_end = extraction_start
        effective_duration = max(0.0, extraction_end - extraction_start)
        if effective_duration <= 0:
            return [], [], []

        target_count = self._resolve_detection_sample_count(effective_duration)
        probe_count = max(1, int(settings.SUBTITLE_DETECTION_SEGMENT_PROBES))
        total_frames = max(1, int(processor.total_frames))
        fps = max(float(processor.fps), 1.0)
        window_start_idx = int(max(0.0, extraction_start) * fps)
        window_end_idx = int(max(0.0, extraction_end) * fps) - 1
        window_start_idx = max(0, min(total_frames - 1, window_start_idx))
        window_end_idx = max(window_start_idx, min(total_frames - 1, window_end_idx))
        window_frame_count = max(1, window_end_idx - window_start_idx + 1)

        frames: List[np.ndarray] = []
        timestamps: List[float] = []
        debug_samples: List[dict] = []
        used_indices = set()

        for segment_idx in range(target_count):
            start_idx = window_start_idx + int(round(segment_idx * window_frame_count / target_count))
            end_idx = window_start_idx + int(round((segment_idx + 1) * window_frame_count / target_count)) - 1
            start_idx = max(window_start_idx, min(window_end_idx, start_idx))
            end_idx = max(start_idx, min(window_end_idx, end_idx))

            if probe_count == 1 or start_idx == end_idx:
                probe_indices = [start_idx + (end_idx - start_idx) // 2]
            else:
                probe_indices = []
                span = max(1, end_idx - start_idx)
                for probe_idx in range(probe_count):
                    fraction = (probe_idx + 0.5) / probe_count
                    candidate_idx = start_idx + int(round(span * fraction))
                    candidate_idx = max(start_idx, min(end_idx, candidate_idx))
                    if candidate_idx not in probe_indices:
                        probe_indices.append(candidate_idx)

            best_frame = None
            best_index = None
            best_score = -1.0

            for candidate_idx in probe_indices:
                frame = processor.get_frame_at_index(candidate_idx)
                if frame is None:
                    continue
                score = self._score_frame_for_pre_detection(frame, position_mode, roi_ratio)
                if score > best_score:
                    best_frame = frame
                    best_index = candidate_idx
                    best_score = score

            if best_frame is None or best_index is None or best_index in used_indices:
                continue

            used_indices.add(best_index)
            timestamp = best_index / fps
            frames.append(best_frame)
            timestamps.append(timestamp)
            debug_samples.append({
                "segment": int(segment_idx),
                "frame_index": int(best_index),
                "timestamp": round(float(timestamp), 3),
                "score": round(float(best_score), 4),
                "probe_indices": probe_indices,
                "extraction_start": round(float(extraction_start), 3),
                "extraction_end": round(float(extraction_end), 3),
            })

        return frames, timestamps, debug_samples

    def _compute_detector_stage_progress(self, stage: str, details: Optional[dict]) -> int:
        details = details or {}
        current = int(details.get("current", 0) or 0)
        total = int(details.get("total", 0) or 0)
        fraction = current / max(1, total)
        if stage == "region_scanning_roi":
            return min(42, 36 + int(round(fraction * 6)))
        if stage == "region_scanning_full_frame":
            return min(46, 43 + int(round(fraction * 3)))
        if stage == "region_scanning_visual_band":
            return min(49, 47 + int(round(fraction * 2)))
        return 36

    def _build_region_progress_callback(
        self,
        progress_callback: Optional[Callable[[int, str, Optional[dict]], None]],
    ) -> Callable[[str, Optional[dict]], None]:
        def _callback(stage: str, details: Optional[dict] = None) -> None:
            progress = self._compute_detector_stage_progress(stage, details)
            self._emit_progress(progress_callback, progress, stage, details)

        return _callback

    def _apply_selected_geometry_recognition(
        self,
        frame: np.ndarray,
        detection: dict,
        geometry_mode: str,
        ocr_lang: Optional[str],
    ) -> Optional[dict]:
        mode = (geometry_mode or settings.SUBTITLE_GEOMETRY_MODE_DEFAULT).lower()
        if mode == "axis_aligned":
            return {
                "mode": mode,
                "applied": False,
                "reason": "default_axis_aligned_merge",
            }

        crop = crop_by_geometry(
            frame,
            geometry_mode=mode,
            box=detection.get("box"),
            polygon=detection.get("polygon"),
            rotated_box=detection.get("rotated_box"),
        )
        if crop is None or crop.size == 0:
            return {
                "mode": mode,
                "applied": False,
                "reason": "empty_crop",
            }

        refined = self.ocr_engine.recognize_text_line(crop, ocr_lang)
        if not refined or not refined.get("text"):
            return {
                "mode": mode,
                "applied": False,
                "reason": "recognizer_empty",
                "crop_shape": list(crop.shape[:2]),
            }

        detection["text"] = refined["text"]
        detection["confidence"] = float(max(detection.get("confidence", 0.0), refined.get("confidence", 0.0)))
        return {
            "mode": mode,
            "applied": True,
            "crop_shape": list(crop.shape[:2]),
            "text": refined["text"],
            "confidence": round(float(refined["confidence"]), 4),
        }

    def generate_srt(self, result: SubtitleExtractionResult) -> str:
        """
        Generate SRT format subtitle

        Args:
            result: Extraction result

        Returns:
            SRT format string
        """
        return SRTGenerator.generate(result.subtitles)

    def save_srt(self, result: SubtitleExtractionResult, output_path: str) -> str:
        """
        Save SRT file

        Args:
            result: Extraction result
            output_path: Output file path

        Returns:
            Saved file path
        """
        return SRTGenerator.save_to_file(result.subtitles, output_path)

    def extract_and_save(
        self,
        video_path: str,
        output_path: str,
        **kwargs
    ) -> SubtitleExtractionResult:
        """
        Extract subtitles and save to file

        Args:
            video_path: Path to video file
            output_path: Output SRT file path
            **kwargs: Additional arguments for extract_subtitles

        Returns:
            SubtitleExtractionResult
        """
        result = self.extract_subtitles(video_path, **kwargs)
        self.save_srt(result, output_path)
        return result

    def _merge_detections_in_frame(self, detections: List[dict]) -> Optional[dict]:
        cleaned = self._clean_text_detections(detections)

        if not cleaned:
            return None

        lines = self._group_detections_into_lines(cleaned)

        line_texts = []
        all_boxes = []
        all_scores = []
        all_polygons = []
        for line in lines:
            line = sorted(line, key=lambda d: d['box'][0])
            line_text = self._join_line_texts(line)
            if line_text:
                line_texts.append(line_text)
                all_boxes.extend([d['box'] for d in line])
                all_scores.extend([d['confidence'] for d in line])
                for det in line:
                    polygon = det.get('polygon') or box_to_polygon(det['box'])
                    if polygon:
                        all_polygons.append(polygon)

        if not line_texts:
            return None

        x1 = min(b[0] for b in all_boxes)
        y1 = min(b[1] for b in all_boxes)
        x2 = max(b[2] for b in all_boxes)
        y2 = max(b[3] for b in all_boxes)
        text = "\n".join(line_texts)
        confidence = float(np.mean(all_scores))
        box = (x1, y1, x2, y2)
        polygon = merge_polygons(all_polygons, target_box=box) or box_to_polygon(box)
        rotated_box = polygon_to_rotated_box(polygon)
        return {
            "text": text,
            "confidence": confidence,
            "box": box,
            "polygon": polygon,
            "rotated_box": rotated_box,
        }

    def _clean_text_detections(self, detections: List[dict]) -> List[dict]:
        cleaned = []
        for det in detections:
            text = det.get('text', '').strip()
            if not text:
                continue
            if det.get('confidence', 0.0) < settings.SUBTITLE_LOCALIZER_MIN_CONFIDENCE:
                continue
            cleaned.append(det)
        return cleaned

    def _group_detections_into_lines(self, detections: List[dict]) -> List[List[dict]]:
        if not detections:
            return []

        ordered = sorted(
            detections,
            key=lambda d: ((d['box'][1] + d['box'][3]) / 2, d['box'][0])
        )
        heights = [max(1, d['box'][3] - d['box'][1]) for d in ordered]
        line_gap = max(8, int(np.mean(heights) * 0.75))
        lines: List[List[dict]] = []
        current = [ordered[0]]

        for det in ordered[1:]:
            prev_center_y = np.mean([(d['box'][1] + d['box'][3]) / 2 for d in current])
            cur_center_y = (det['box'][1] + det['box'][3]) / 2
            current_heights = [max(1, d['box'][3] - d['box'][1]) for d in current]
            current_height = float(np.median(current_heights))
            det_height = max(1, det['box'][3] - det['box'][1])
            height_ratio = max(current_height, det_height) / max(1.0, min(current_height, det_height))
            vertical_overlap = max(self._vertical_overlap_ratio(det['box'], existing['box']) for existing in current)
            center_gap = abs(cur_center_y - prev_center_y)
            current_box = self._line_to_box(current)
            horizontal_gap = self._horizontal_gap(current_box, det['box'])
            horizontal_overlap = self._horizontal_overlap_ratio(current_box, det['box'])
            max_horizontal_gap = max(
                36.0,
                min(current_height, det_height) * 3.4,
            )
            horizontal_close = horizontal_gap <= max_horizontal_gap or horizontal_overlap >= 0.08
            same_line = (
                center_gap <= line_gap
                and height_ratio <= 1.8
                and horizontal_close
                and (
                    vertical_overlap >= 0.18
                    or center_gap <= max(8.0, min(current_height, det_height) * 0.45)
                )
            )
            if same_line:
                current.append(det)
            else:
                lines.extend(self._split_line_by_horizontal_gap(current))
                current = [det]
        lines.extend(self._split_line_by_horizontal_gap(current))
        return lines

    def _line_to_box(self, line: List[dict]) -> Tuple[int, int, int, int]:
        return (
            min(det['box'][0] for det in line),
            min(det['box'][1] for det in line),
            max(det['box'][2] for det in line),
            max(det['box'][3] for det in line),
        )

    def _pad_tight_box(
        self,
        box: Tuple[int, int, int, int],
        frame_shape: Tuple[int, ...],
    ) -> Tuple[int, int, int, int]:
        x1, y1, x2, y2 = box
        width = max(1, x2 - x1)
        height = max(1, y2 - y1)
        pad_x = max(settings.SUBTITLE_TIGHT_REGION_PAD_X_MIN, int(width * settings.SUBTITLE_TIGHT_REGION_PAD_X_RATIO))
        pad_y = max(settings.SUBTITLE_TIGHT_REGION_PAD_Y_MIN, int(height * settings.SUBTITLE_TIGHT_REGION_PAD_Y_RATIO))
        return self._clamp_box((x1 - pad_x, y1 - pad_y, x2 + pad_x, y2 + pad_y), frame_shape)

    def _filter_detections_to_focus_box(
        self,
        detections: List[dict],
        focus_box: Tuple[int, int, int, int],
    ) -> List[dict]:
        filtered = []
        focus_height = max(1, focus_box[3] - focus_box[1])
        for det in detections:
            box = det.get("box")
            if not box:
                continue
            vertical_overlap = self._vertical_overlap_ratio(box, focus_box)
            horizontal_overlap = self._horizontal_overlap_ratio(box, focus_box)
            center_y = (box[1] + box[3]) / 2
            vertical_offset = abs(center_y - ((focus_box[1] + focus_box[3]) / 2))
            if (
                vertical_overlap >= 0.38
                and (
                    horizontal_overlap >= 0.08
                    or vertical_offset <= focus_height * 0.55
                )
            ):
                filtered.append(det)
        return filtered or detections

    def _filter_variety_recall_frame_detections(
        self,
        detections: List[dict],
        frame_shape: Tuple[int, ...],
    ) -> List[dict]:
        if not self.variety_recall_enabled or not detections:
            return detections

        frame_height, frame_width = frame_shape[:2]
        candidates = []
        for det in detections:
            box = det.get("box")
            text = (det.get("text") or "").strip()
            if not box or not text:
                continue
            x1, y1, x2, y2 = [float(v) for v in box]
            center_x_ratio = ((x1 + x2) / 2) / max(1, frame_width)
            center_y_ratio = ((y1 + y2) / 2) / max(1, frame_height)
            bottom_ratio = y2 / max(1, frame_height)
            width_ratio = (x2 - x1) / max(1, frame_width)
            right_overlay = self._is_variety_right_overlay_detection(det, frame_width)
            speaker_tag = self._is_variety_speaker_tag(det, frame_width)
            center_subtitle = (
                _has_cjk_text(text)
                and not right_overlay
                and 0.27 <= center_x_ratio <= 0.77
                and center_y_ratio >= 0.58
                and bottom_ratio >= 0.66
            )
            candidates.append({
                "det": det,
                "text": text,
                "center_x_ratio": center_x_ratio,
                "center_y_ratio": center_y_ratio,
                "bottom_ratio": bottom_ratio,
                "width_ratio": width_ratio,
                "right_overlay": right_overlay,
                "speaker_tag": speaker_tag,
                "center_subtitle": center_subtitle,
            })

        if not candidates:
            return []

        center_candidates = [candidate for candidate in candidates if candidate["center_subtitle"]]
        if center_candidates:
            center_y = float(np.median([candidate["center_y_ratio"] for candidate in center_candidates]))
            kept = []
            for candidate in candidates:
                if candidate["right_overlay"] or candidate["speaker_tag"]:
                    continue
                if abs(candidate["center_y_ratio"] - center_y) > 0.08:
                    continue
                if candidate["center_subtitle"] or (
                    _has_cjk_text(candidate["text"])
                    and candidate["center_x_ratio"] >= 0.36
                    and candidate["bottom_ratio"] >= 0.64
                ):
                    kept.append(candidate["det"])
            return kept or [candidate["det"] for candidate in center_candidates]

        return [
            candidate["det"]
            for candidate in candidates
            if not candidate["right_overlay"]
            and not candidate["speaker_tag"]
            and (
                _has_cjk_text(candidate["text"])
                or candidate["width_ratio"] >= 0.18
            )
        ]

    def _horizontal_overlap_ratio(
        self,
        left_box: Tuple[int, int, int, int],
        right_box: Tuple[int, int, int, int],
    ) -> float:
        overlap = max(0, min(left_box[2], right_box[2]) - max(left_box[0], right_box[0]))
        base = max(1, min(left_box[2] - left_box[0], right_box[2] - right_box[0]))
        return overlap / base

    def _vertical_overlap_ratio(
        self,
        top_box: Tuple[int, int, int, int],
        bottom_box: Tuple[int, int, int, int],
    ) -> float:
        overlap = max(0, min(top_box[3], bottom_box[3]) - max(top_box[1], bottom_box[1]))
        base = max(1, min(top_box[3] - top_box[1], bottom_box[3] - bottom_box[1]))
        return overlap / base

    def _horizontal_gap(
        self,
        left_box: Tuple[int, int, int, int],
        right_box: Tuple[int, int, int, int],
    ) -> float:
        return float(max(0, max(right_box[0] - left_box[2], left_box[0] - right_box[2])))

    def _split_line_by_horizontal_gap(self, line: List[dict]) -> List[List[dict]]:
        ordered = sorted(line, key=lambda d: d['box'][0])
        if len(ordered) <= 1:
            return [ordered]

        heights = [max(1, det['box'][3] - det['box'][1]) for det in ordered]
        median_height = float(np.median(heights))
        sub_lines: List[List[dict]] = []
        current = [ordered[0]]

        for det in ordered[1:]:
            prev_box = current[-1]['box']
            gap = self._horizontal_gap(prev_box, det['box'])
            horizontal_overlap = self._horizontal_overlap_ratio(prev_box, det['box'])
            prev_width = max(1, prev_box[2] - prev_box[0])
            gap_limit = max(36.0, median_height * 3.4, prev_width * 0.85)
            if gap > gap_limit and horizontal_overlap < 0.08:
                sub_lines.append(current)
                current = [det]
            else:
                current.append(det)

        sub_lines.append(current)
        return sub_lines

    def _normalize_subtitle_candidate_text(self, text: str) -> str:
        normalized = re.sub(r"\s+", "", (text or "").strip().lower())
        return re.sub(r"[^\w\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7a3]", "", normalized)

    def _build_subtitle_meta(
        self,
        box: Tuple[int, int, int, int],
        text: str,
    ) -> Dict[str, Any]:
        x1, y1, x2, y2 = box
        return {
            "box": tuple(int(v) for v in box),
            "center_x": float((x1 + x2) / 2),
            "center_y": float((y1 + y2) / 2),
            "width": float(max(1, x2 - x1)),
            "height": float(max(1, y2 - y1)),
            "text": text or "",
            "normalized_text": self._normalize_subtitle_candidate_text(text or ""),
        }

    def _compute_position_alignment_prior(
        self,
        line_box: Tuple[int, int, int, int],
        search_region: Tuple[int, int, int, int],
        anchor: SubtitleAnchor,
    ) -> float:
        search_x1, search_y1, search_x2, search_y2 = search_region
        search_height = max(1, search_y2 - search_y1)
        position_mode = (anchor.position_mode or "bottom").lower()

        if position_mode == "top":
            target_value = search_y1 + search_height * 0.08
            candidate_value = line_box[1]
            tolerance = search_height * 0.38
        elif position_mode == "middle":
            target_value = search_y1 + search_height * 0.5
            candidate_value = (line_box[1] + line_box[3]) / 2
            tolerance = search_height * 0.34
        else:
            target_value = search_y2 - search_height * 0.08
            candidate_value = line_box[3]
            tolerance = search_height * 0.38

        return max(0.0, 1.0 - abs(candidate_value - target_value) / max(1.0, tolerance))

    def _compute_style_match(
        self,
        candidate_meta: Dict[str, Any],
        tracker_state: Dict[str, Any],
        current_timestamp: Optional[float] = None,
    ) -> float:
        style_profile = tracker_state.get("subtitle_style")
        if not style_profile or style_profile.get("count", 0) < settings.SUBTITLE_LOCALIZER_STYLE_PROFILE_MIN_COUNT:
            return 0.55
        last_seen_timestamp = style_profile.get("last_seen_timestamp")
        if current_timestamp is not None and last_seen_timestamp is not None:
            style_age = max(0.0, float(current_timestamp) - float(last_seen_timestamp))
            if style_age >= settings.SUBTITLE_LOCALIZER_STYLE_PROFILE_MAX_AGE_SECONDS:
                return 0.55
        else:
            style_age = 0.0

        width_prior = 1.0 - min(
            1.0,
            abs(candidate_meta["width"] - style_profile["width"]) / max(1.0, style_profile["width"] * 0.4),
        )
        height_prior = 1.0 - min(
            1.0,
            abs(candidate_meta["height"] - style_profile["height"]) / max(1.0, style_profile["height"] * 0.35),
        )
        center_x_prior = 1.0 - min(
            1.0,
            abs(candidate_meta["center_x"] - style_profile["center_x"]) / max(1.0, style_profile["width"] * 0.5),
        )
        bottom_prior = 1.0 - min(
            1.0,
            abs(candidate_meta["box"][3] - style_profile["bottom_y"]) / max(1.0, style_profile["height"] * 0.8),
        )
        raw_score = max(0.0, min(1.0, float(
            0.34 * height_prior
            + 0.28 * width_prior
            + 0.18 * center_x_prior
            + 0.20 * bottom_prior
        )))
        if current_timestamp is None or last_seen_timestamp is None:
            return raw_score

        freshness = max(
            0.0,
            1.0 - style_age / max(1e-6, float(settings.SUBTITLE_LOCALIZER_STYLE_PROFILE_MAX_AGE_SECONDS)),
        )
        return max(0.0, min(1.0, float(0.55 * (1.0 - freshness) + raw_score * freshness)))

    def _update_subtitle_style_profile(
        self,
        tracker_state: Dict[str, Any],
        box: Tuple[int, int, int, int] | None,
        timestamp: Optional[float] = None,
    ) -> None:
        if box is None:
            return

        x1, y1, x2, y2 = box
        width = float(max(1, x2 - x1))
        height = float(max(1, y2 - y1))
        center_x = float((x1 + x2) / 2)
        bottom_y = float(y2)
        style_profile = tracker_state.get("subtitle_style")
        if not style_profile:
            tracker_state["subtitle_style"] = {
                "count": 1,
                "width": width,
                "height": height,
                "center_x": center_x,
                "bottom_y": bottom_y,
                "last_seen_timestamp": float(timestamp) if timestamp is not None else None,
            }
            return

        alpha = 0.3
        style_profile["count"] = min(50, int(style_profile.get("count", 0)) + 1)
        style_profile["width"] = style_profile["width"] * (1.0 - alpha) + width * alpha
        style_profile["height"] = style_profile["height"] * (1.0 - alpha) + height * alpha
        style_profile["center_x"] = style_profile["center_x"] * (1.0 - alpha) + center_x * alpha
        style_profile["bottom_y"] = style_profile["bottom_y"] * (1.0 - alpha) + bottom_y * alpha
        style_profile["last_seen_timestamp"] = float(timestamp) if timestamp is not None else style_profile.get("last_seen_timestamp")
        tracker_state["subtitle_style"] = style_profile

    def _remember_overlay_candidate(
        self,
        tracker_state: Dict[str, Any],
        candidate_meta: Optional[Dict[str, Any]],
        timestamp: Optional[float] = None,
    ) -> None:
        if not candidate_meta:
            return

        overlay_tracks = list(tracker_state.get("overlay_tracks") or [])
        for track in overlay_tracks:
            support = self._compute_candidate_temporal_support(
                candidate_meta,
                track,
                search_width=max(1, int(track.get("width", 1) * 4)),
                search_height=max(1, int(track.get("height", 1) * 4)),
            )
            if support >= self.localizer_profile["overlay_track_threshold"]:
                hits = min(8, int(track.get("hits", 1)) + 1)
                alpha = 1.0 / hits
                track["hits"] = hits
                track["center_x"] = track["center_x"] * (1.0 - alpha) + candidate_meta["center_x"] * alpha
                track["center_y"] = track["center_y"] * (1.0 - alpha) + candidate_meta["center_y"] * alpha
                track["width"] = track["width"] * (1.0 - alpha) + candidate_meta["width"] * alpha
                track["height"] = track["height"] * (1.0 - alpha) + candidate_meta["height"] * alpha
                track["box"] = candidate_meta["box"]
                track["text"] = candidate_meta["text"]
                track["normalized_text"] = candidate_meta["normalized_text"]
                track["last_seen_timestamp"] = float(timestamp) if timestamp is not None else track.get("last_seen_timestamp")
                tracker_state["overlay_tracks"] = overlay_tracks[:settings.SUBTITLE_LOCALIZER_OVERLAY_TRACK_MAX_SIZE]
                return

        overlay_tracks.insert(0, {
            **candidate_meta,
            "hits": 1,
            "last_seen_timestamp": float(timestamp) if timestamp is not None else None,
        })
        tracker_state["overlay_tracks"] = overlay_tracks[:settings.SUBTITLE_LOCALIZER_OVERLAY_TRACK_MAX_SIZE]

    def _compute_overlay_track_support(
        self,
        candidate_meta: Dict[str, Any],
        tracker_state: Dict[str, Any],
        search_width: int,
        search_height: int,
        current_timestamp: Optional[float] = None,
    ) -> float:
        overlay_tracks = tracker_state.get("overlay_tracks") or []
        if not overlay_tracks:
            return 0.0

        best_support = 0.0
        for track in overlay_tracks:
            if current_timestamp is not None:
                last_seen_timestamp = track.get("last_seen_timestamp")
                if last_seen_timestamp is not None:
                    track_age = max(0.0, float(current_timestamp) - float(last_seen_timestamp))
                    if track_age >= settings.SUBTITLE_LOCALIZER_OVERLAY_TRACK_MAX_AGE_SECONDS:
                        continue
                else:
                    track_age = 0.0
            else:
                track_age = 0.0
            support = self._compute_candidate_temporal_support(candidate_meta, track, search_width, search_height)
            hits = max(1, int(track.get("hits", 1)))
            support *= min(1.0, 0.55 + hits * 0.18)
            if current_timestamp is not None:
                freshness = max(
                    0.0,
                    1.0 - track_age / max(1e-6, float(settings.SUBTITLE_LOCALIZER_OVERLAY_TRACK_MAX_AGE_SECONDS)),
                )
                support *= 0.40 + 0.60 * freshness
            best_support = max(best_support, support)
        return max(0.0, min(1.0, float(best_support)))

    def _compute_edge_column_score(
        self,
        candidate: Dict[str, Any],
        candidates: List[Dict[str, Any]],
        search_region: Tuple[int, int, int, int],
    ) -> float:
        if len(candidates) <= 1:
            return 0.0

        search_x1, _, search_x2, _ = search_region
        search_width = max(1.0, float(search_x2 - search_x1))
        candidate_box = candidate["box"]
        candidate_height = max(1.0, float(candidate["height"]))
        align_tolerance = max(24.0, search_width * 0.035)
        center_tolerance = max(28.0, search_width * 0.04)
        gap_tolerance = max(candidate_height * 3.2, 64.0)

        aligned_count = 0
        top = float(candidate_box[1])
        bottom = float(candidate_box[3])
        for other in candidates:
            if other is candidate:
                continue

            other_box = other["box"]
            left_aligned = abs(float(other_box[0]) - float(candidate_box[0])) <= align_tolerance
            right_aligned = abs(float(other_box[2]) - float(candidate_box[2])) <= align_tolerance
            center_aligned = abs(float(other["center_x"]) - float(candidate["center_x"])) <= center_tolerance
            similar_width = abs(float(other["width_ratio"]) - float(candidate["width_ratio"])) <= 0.16
            vertical_gap = max(
                0.0,
                max(float(other_box[1]) - float(candidate_box[3]), float(candidate_box[1]) - float(other_box[3])),
            )
            if (left_aligned or right_aligned or center_aligned) and similar_width and vertical_gap <= gap_tolerance:
                aligned_count += 1
                top = min(top, float(other_box[1]))
                bottom = max(bottom, float(other_box[3]))

        if aligned_count == 0:
            return 0.0

        span_ratio = max(0.0, (bottom - top) / candidate_height)
        stack_score = max(0.0, min(1.0, (span_ratio - 2.0) / 2.8))
        count_score = max(0.0, min(1.0, aligned_count / 3.0))
        return max(0.0, min(1.0, float(0.55 * stack_score + 0.45 * count_score)))

    def _compute_candidate_temporal_support(
        self,
        candidate_meta: Dict[str, Any],
        reference_meta: Optional[Dict[str, Any]],
        search_width: int,
        search_height: int,
    ) -> float:
        if not reference_meta:
            return 0.0

        center_x_prior = 1.0 - min(
            1.0,
            abs(candidate_meta["center_x"] - reference_meta["center_x"]) / max(1.0, search_width * 0.18),
        )
        center_y_prior = 1.0 - min(
            1.0,
            abs(candidate_meta["center_y"] - reference_meta["center_y"]) / max(1.0, search_height * 0.22),
        )
        height_prior = 1.0 - min(
            1.0,
            abs(candidate_meta["height"] - reference_meta["height"]) / max(1.0, reference_meta["height"] * 0.45),
        )
        width_prior = 1.0 - min(
            1.0,
            abs(candidate_meta["width"] - reference_meta["width"]) / max(1.0, reference_meta["width"] * 0.55),
        )
        text_bonus = 0.0
        if candidate_meta["normalized_text"] and candidate_meta["normalized_text"] == reference_meta.get("normalized_text", ""):
            text_bonus = 0.08
        support = (
            0.34 * center_x_prior
            + 0.34 * center_y_prior
            + 0.16 * height_prior
            + 0.16 * width_prior
            + text_bonus
        )
        return max(0.0, min(1.0, float(support)))

    def _compute_subtitle_text_penalties(
        self,
        text: str,
        width_ratio: float,
    ) -> Tuple[float, Dict[str, float]]:
        normalized = re.sub(r"\s+", "", (text or "").strip())
        if not normalized:
            return 1.0, {"empty_text": 1.0}

        cjk_count = sum(1 for ch in normalized if '\u4e00' <= ch <= '\u9fff')
        kana_count = sum(1 for ch in normalized if '\u3040' <= ch <= '\u30ff')
        hangul_count = sum(1 for ch in normalized if '\uac00' <= ch <= '\ud7a3')
        digit_count = sum(1 for ch in normalized if ch.isdigit())
        latin_count = sum(1 for ch in normalized if ('A' <= ch <= 'Z') or ('a' <= ch <= 'z'))
        east_asian_count = cjk_count + kana_count + hangul_count
        alnum_count = digit_count + latin_count
        char_count = len(normalized)
        alnum_ratio = alnum_count / max(1, char_count)

        penalties: Dict[str, float] = {}
        if char_count <= 2 and east_asian_count == 0:
            penalties["too_short_non_cjk"] = 0.28
        if digit_count > 0 and latin_count > 0 and east_asian_count == 0:
            penalties["mixed_alnum_phrase"] = 0.22
        if char_count <= 8 and digit_count > 0 and latin_count > 0 and east_asian_count == 0:
            penalties["short_mixed_alnum"] = 0.26
        if char_count <= 10 and digit_count >= max(4, int(char_count * 0.6)) and east_asian_count == 0:
            penalties["mostly_numeric"] = 0.18
        if re.fullmatch(r"[\u4e00-\u9fff]?[A-Z][A-Z0-9]{5,7}", normalized.upper()):
            penalties["plate_like"] = 0.32
        if width_ratio < self.localizer_profile["min_width_ratio"] and char_count < 5:
            if east_asian_count == 0:
                penalties["narrow_short_line"] = 0.18
            elif char_count <= 2:
                penalties["narrow_short_east_asian"] = 0.08
        if width_ratio < 0.12 and east_asian_count == 0 and char_count >= 6:
            penalties["narrow_latin_line"] = 0.22
        if width_ratio < 0.12 and east_asian_count > 0 and latin_count > 0:
            penalties["narrow_mixed_script"] = 0.28
        if east_asian_count == 0 and alnum_ratio > 0.9 and char_count < 12:
            penalties["non_language_like"] = 0.14

        total_penalty = max(0.0, min(0.7, float(sum(penalties.values()))))
        return total_penalty, penalties

    def _compute_credit_text_score(self, text: str) -> Tuple[float, Dict[str, float]]:
        stripped = (text or "").strip()
        if not stripped:
            return 0.0, {}

        normalized = re.sub(r"\s+", " ", stripped)
        joined = normalized.replace(" ", "").replace("\n", "")
        tokens = [token for token in re.split(r"[\s/|]+", normalized.replace("\n", " ")) if token]
        cjk_short_tokens = [
            token
            for token in tokens
            if 1 <= len(token) <= 4 and all('\u4e00' <= ch <= '\u9fff' for ch in token)
        ]
        latin_tokens = [
            token
            for token in tokens
            if len(token) >= 4 and all(('A' <= ch <= 'Z') or ('a' <= ch <= 'z') for ch in token)
        ]
        organization_terms = (
            "有限公司",
            "传媒",
            "股份",
            "娱乐",
            "乐团",
            "集团",
            "文化",
            "文创",
        )
        organization_hits = [term for term in organization_terms if term in joined]
        credit_role_terms = (
            "参与演出人员",
            "主演",
            "领衔主演",
            "特别出演",
            "友情出演",
            "剧场统筹",
            "统筹",
            "后期制作",
            "音乐制作",
            "制作人",
            "执行制片",
            "监制",
            "总监",
            "剪辑师",
            "混音",
            "作词",
            "作曲",
            "编曲",
            "演唱",
            "出品",
            "制作公司",
            "营销公司",
            "合作媒体",
            "媒体合作",
            "特别鸣谢",
            "著作权",
            "着作权",
            "版权",
            "摄影",
            "灯光",
            "录音",
            "美术",
            "道具",
            "服装",
            "化妆",
            "场务",
            "剧务",
            "宣传",
            "发行",
            "商务",
            "策划",
        )
        credit_role_hits = [term for term in credit_role_terms if term in joined]
        lowered_joined = joined.lower()
        latin_company_terms = (
            "media",
            "entertainment",
            "studio",
            "pictures",
            "production",
            "company",
            "copyright",
            "sunshine",
        )
        latin_company_hit = any(term in lowered_joined for term in latin_company_terms)

        score = 0.0
        breakdown: Dict[str, float] = {}
        if len(cjk_short_tokens) >= 3 and len(tokens) >= 3:
            score += 0.58
            breakdown["short_name_list"] = 0.58
        if len(set(cjk_short_tokens)) < len(cjk_short_tokens) and len(cjk_short_tokens) >= 3:
            score += 0.10
            breakdown["repeated_names"] = 0.10
        if organization_hits and len(joined) >= 6:
            score += 0.46
            breakdown["organization_suffix"] = 0.46
        if credit_role_hits:
            score += 0.38
            breakdown["credit_role_term"] = 0.38
        if latin_company_hit and len(latin_tokens) >= 1:
            score += 0.34
            breakdown["latin_company_term"] = 0.34
        latin_repeat_like = False
        if len(latin_tokens) >= 2:
            lowered = [token.lower() for token in latin_tokens]
            latin_repeat_like = len(set(lowered)) < len(lowered)
            if not latin_repeat_like:
                for idx, token in enumerate(lowered):
                    for other in lowered[idx + 1:]:
                        similarity = (
                            self.merger._text_similarity(token, other)
                            if self.merger is not None
                            else _safe_text_similarity(token, other)
                        )
                        if similarity >= 0.78:
                            latin_repeat_like = True
                            break
                    if latin_repeat_like:
                        break
        if latin_repeat_like:
            score += 0.44
            breakdown["latin_label_repeat"] = 0.44
        if "\n" in stripped and (organization_hits or len(cjk_short_tokens) >= 2):
            score += 0.08
            breakdown["multiline_credit_layout"] = 0.08

        return max(0.0, min(1.0, float(score))), breakdown

    def _compute_signage_overlay_score(
        self,
        text: str,
        width_ratio: float,
        center_x_prior: float,
        position_prior: float,
        frame_width_ratio: Optional[float] = None,
    ) -> Tuple[float, Dict[str, float]]:
        normalized = re.sub(r"\s+", "", (text or "").strip())
        if not normalized:
            return 0.0, {}

        cjk_count = sum(1 for ch in normalized if '\u4e00' <= ch <= '\u9fff')
        kana_count = sum(1 for ch in normalized if '\u3040' <= ch <= '\u30ff')
        hangul_count = sum(1 for ch in normalized if '\uac00' <= ch <= '\ud7a3')
        digit_count = sum(1 for ch in normalized if ch.isdigit())
        latin_count = sum(1 for ch in normalized if ('A' <= ch <= 'Z') or ('a' <= ch <= 'z'))
        punctuation_count = sum(1 for ch in normalized if not ch.isalnum() and ch not in {'_', '-'})
        hyphen_count = normalized.count('-') + normalized.count('_')
        east_asian_count = cjk_count + kana_count + hangul_count
        char_count = len(normalized)

        pattern_score = 0.0
        components: Dict[str, float] = {}
        if east_asian_count > 0 and latin_count > 0:
            pattern_score += 0.34
            components["mixed_script"] = 0.34
        if digit_count >= 2:
            pattern_score += 0.16
            components["digit_tag"] = 0.16
        if hyphen_count > 0 or punctuation_count > 0:
            pattern_score += 0.10
            components["tag_separator"] = 0.10
        effective_width_ratio = min(width_ratio, frame_width_ratio if frame_width_ratio is not None else width_ratio)
        if char_count <= 26 and effective_width_ratio < self.localizer_profile["signage_strict_width_ratio"]:
            pattern_score += 0.14
            components["compact_label"] = 0.14
        if east_asian_count == 0 and latin_count > 0 and digit_count > 0:
            pattern_score += 0.08
            components["latin_numeric"] = 0.08

        pattern_score = max(0.0, min(1.0, pattern_score))
        narrow_score = max(
            0.0,
            min(
                1.0,
                (self.localizer_profile["signage_strict_width_ratio"] - effective_width_ratio)
                / max(0.01, self.localizer_profile["signage_strict_width_ratio"]),
            ),
        )
        off_center_score = max(0.0, (0.90 - center_x_prior) / 0.90)
        band_mismatch_score = max(0.0, 1.0 - position_prior)

        score = (
            0.48 * pattern_score
            + 0.20 * narrow_score
            + 0.16 * off_center_score
            + 0.16 * band_mismatch_score
        )
        score = max(0.0, min(1.0, float(score)))
        if narrow_score > 0:
            components["narrow_score"] = round(float(narrow_score), 4)
        if off_center_score > 0:
            components["off_center_score"] = round(float(off_center_score), 4)
        if band_mismatch_score > 0:
            components["band_mismatch_score"] = round(float(band_mismatch_score), 4)
        return score, components

    def _compute_dense_text_scene_score(
        self,
        candidates: List[Dict[str, Any]],
        component_count: int,
        search_height: int,
    ) -> Tuple[float, Dict[str, float]]:
        if not candidates:
            return 0.0, {}

        line_count = len(candidates)
        fragmented_line_count = sum(1 for candidate in candidates if len(candidate["detections"]) >= 4)
        tall_line_count = sum(
            1
            for candidate in candidates
            if candidate["height"] / max(1.0, float(search_height)) >= 0.42
        )
        wide_line_count = sum(1 for candidate in candidates if candidate["width_ratio"] >= 0.45)
        total_width_ratio = sum(min(1.0, float(candidate["width_ratio"])) for candidate in candidates)

        line_count_score = max(0.0, min(1.0, (line_count - 2) / 3.0))
        component_count_score = max(0.0, min(1.0, (component_count - 6) / 18.0))
        fragmented_line_score = max(0.0, min(1.0, fragmented_line_count / 3.0))
        tall_line_score = max(0.0, min(1.0, tall_line_count / 2.0))
        coverage_score = max(0.0, min(1.0, (total_width_ratio - 1.1) / 1.4))
        wide_line_score = max(0.0, min(1.0, wide_line_count / 2.0))

        breakdown = {
            "line_count_score": round(float(line_count_score), 4),
            "component_count_score": round(float(component_count_score), 4),
            "fragmented_line_score": round(float(fragmented_line_score), 4),
            "tall_line_score": round(float(tall_line_score), 4),
            "coverage_score": round(float(coverage_score), 4),
            "wide_line_score": round(float(wide_line_score), 4),
            "line_count": float(line_count),
            "component_count": float(component_count),
            "fragmented_line_count": float(fragmented_line_count),
            "tall_line_count": float(tall_line_count),
        }
        score = (
            0.22 * line_count_score
            + 0.20 * component_count_score
            + 0.20 * fragmented_line_score
            + 0.14 * tall_line_score
            + 0.14 * coverage_score
            + 0.10 * wide_line_score
        )
        return max(0.0, min(1.0, float(score))), breakdown

    def _is_variety_right_overlay_text(self, text: str) -> bool:
        normalized = self._normalize_subtitle_candidate_text(text or "")
        if not normalized:
            return False
        overlay_keywords = (
            "千问",
            "阿里ai助手",
            "ali",
            "viva",
            "romance",
            "妻子的浪漫旅行",
            "浪漫旅行2026",
            "买会员",
            "会员",
            "广告",
            "花絮",
            "预告",
            "umL",
            "cfumL",
            "supplement",
            "prevention",
        )
        normalized_lower = normalized.lower()
        return any(keyword.lower() in normalized_lower for keyword in overlay_keywords)

    def _is_variety_right_overlay_detection(
        self,
        detection_or_candidate: Dict[str, Any],
        frame_width: int,
    ) -> bool:
        box = detection_or_candidate.get("box")
        if not box:
            return False
        x1, _, x2, _ = [float(v) for v in box]
        center_x = (x1 + x2) / 2
        text = detection_or_candidate.get("text", "")
        if self._is_variety_right_overlay_text(text):
            return True
        return x1 / max(1, frame_width) >= 0.74 or center_x / max(1, frame_width) >= 0.82

    def _is_variety_speaker_tag(
        self,
        detection_or_candidate: Dict[str, Any],
        frame_width: int,
    ) -> bool:
        box = detection_or_candidate.get("box")
        if not box:
            return False
        x1, _, x2, _ = [float(v) for v in box]
        width_ratio = (x2 - x1) / max(1, frame_width)
        normalized = self._normalize_subtitle_candidate_text(detection_or_candidate.get("text", ""))
        cjk_count = sum(1 for ch in normalized if '\u4e00' <= ch <= '\u9fff')
        return (
            cjk_count > 0
            and len(normalized) <= 5
            and x2 / max(1, frame_width) <= 0.43
            and width_ratio <= 0.20
        )

    def _subtitle_only_mode_enabled(self) -> bool:
        return (
            self.subtitle_extraction_mode == "conservative"
            and not self.variety_recall_enabled
            and not self.manual_region_active
        )

    def _compute_subtitle_only_reject_reasons(
        self,
        candidate: Dict[str, Any],
        frame_shape: Tuple[int, ...],
        position_mode: str,
        has_established_subtitle_context: bool,
    ) -> List[str]:
        if not self._subtitle_only_mode_enabled():
            return []

        frame_height, frame_width = frame_shape[:2]
        box = candidate["box"]
        x1, y1, x2, y2 = [float(v) for v in box]
        box_width = max(1.0, x2 - x1)
        box_height = max(1.0, y2 - y1)
        center_x_ratio = ((x1 + x2) / 2) / max(1.0, float(frame_width))
        bottom_ratio = y2 / max(1.0, float(frame_height))
        frame_width_ratio = box_width / max(1.0, float(frame_width))
        aspect_ratio = box_width / box_height
        normalized_text = candidate.get("normalized_text") or ""
        east_asian_count = sum(
            1
            for ch in normalized_text
            if ('\u4e00' <= ch <= '\u9fff')
            or ('\u3040' <= ch <= '\u30ff')
            or ('\uac00' <= ch <= '\ud7a3')
        )
        text_len = len(normalized_text)
        temporal_support = float(candidate.get("temporal_support") or 0.0)
        position_mode = (position_mode or "bottom").lower()

        reasons: List[str] = []
        # Default subtitle extraction should prefer centered horizontal captions.
        # Edge-aligned text in this project is usually channel branding, fixed title
        # labels, speaker tags, or picture text rather than the spoken subtitle.
        if x1 / max(1.0, float(frame_width)) >= 0.72 or center_x_ratio >= 0.82:
            reasons.append("subtitle_only_right_edge_text")
        if x2 / max(1.0, float(frame_width)) <= 0.28 or center_x_ratio <= 0.18:
            reasons.append("subtitle_only_left_edge_text")

        if (
            east_asian_count >= 3
            and aspect_ratio < 1.8
            and temporal_support < 0.78
        ):
            reasons.append("subtitle_only_vertical_or_narrow_text")

        if (
            frame_width_ratio < 0.08
            and text_len >= 4
            and not has_established_subtitle_context
        ):
            reasons.append("subtitle_only_contextless_narrow_text")

        if (
            position_mode == "bottom"
            and bottom_ratio < 0.62
            and temporal_support < 0.72
        ):
            reasons.append("subtitle_only_above_bottom_band")

        return reasons

    def _serialize_localizer_candidates(
        self,
        candidates: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        serialized: List[Dict[str, Any]] = []
        for candidate in candidates:
            box = candidate.get("box") or (0, 0, 0, 0)
            serialized.append({
                "line_index": int(candidate.get("line_index", -1)),
                "box": [int(v) for v in box],
                "text": candidate.get("text", ""),
                "confidence": round(float(candidate.get("confidence") or 0.0), 4),
                "width_ratio": round(float(candidate.get("width_ratio") or 0.0), 4),
                "frame_width_ratio": round(float(candidate.get("frame_width_ratio") or 0.0), 4),
                "center_x_prior": round(float(candidate.get("center_x_prior") or 0.0), 4),
                "position_prior": round(float(candidate.get("position_prior") or 0.0), 4),
                "temporal_support": round(float(candidate.get("temporal_support") or 0.0), 4),
                "previous_support": round(float(candidate.get("previous_support") or 0.0), 4),
                "pending_support": round(float(candidate.get("pending_support") or 0.0), 4),
                "overlay_track_support": round(float(candidate.get("overlay_track_support") or 0.0), 4),
                "style_match": round(float(candidate.get("style_match") or 0.0), 4),
                "edge_attachment": round(float(candidate.get("edge_attachment") or 0.0), 4),
                "edge_column_score": round(float(candidate.get("edge_column_score") or 0.0), 4),
                "signage_score": round(float(candidate.get("signage_score") or 0.0), 4),
                "bottom_centered_compact_subtitle": bool(candidate.get("bottom_centered_compact_subtitle", False)),
                "dense_text_scene_score": round(float(candidate.get("dense_text_scene_score") or 0.0), 4),
                "stacked_layout_score": round(float(candidate.get("stacked_layout_score") or 0.0), 4),
                "rank_penalty": round(float(candidate.get("rank_penalty") or 0.0), 4),
                "band_mismatch": round(float(candidate.get("band_mismatch") or 0.0), 4),
                "negative_penalty": round(float(candidate.get("negative_penalty") or 0.0), 4),
                "penalty_breakdown": {
                    str(key): round(float(value), 4)
                    for key, value in (candidate.get("penalty_breakdown") or {}).items()
                },
                "subtitle_score": round(float(candidate.get("subtitle_score") or 0.0), 4),
                "overlay_score": round(float(candidate.get("overlay_score") or 0.0), 4),
                "score": round(float(candidate.get("score") or 0.0), 4),
                "accepted": bool(candidate.get("accepted", False)),
                "waiting_confirmation": bool(candidate.get("waiting_confirmation", False)),
                "reject_reasons": list(candidate.get("reject_reasons") or []),
            })
        return serialized

    def _record_localization_failure(
        self,
        tracker_state: Dict[str, Any],
        reason: str,
        search_region: Tuple[int, int, int, int],
        frame_shape: Tuple[int, ...],
        timestamp: Optional[float] = None,
        candidates: Optional[List[Dict[str, Any]]] = None,
        extra_debug: Optional[Dict[str, Any]] = None,
    ) -> None:
        record: Dict[str, Any] = {
            "timestamp": round(float(timestamp), 3) if timestamp is not None else None,
            "reason": reason,
            "search_region": [int(v) for v in search_region],
            "frame_shape": [int(v) for v in frame_shape[:2]],
        }
        if extra_debug:
            record.update(extra_debug)
        if candidates is not None:
            record["line_candidates"] = self._serialize_localizer_candidates(candidates)

        tracker_state["last_localization_failure"] = record
        failures = tracker_state.setdefault("localization_failures", [])
        failures.append(record)
        max_records = max(0, int(settings.SUBTITLE_LOCALIZER_FAILURE_DEBUG_MAX_RECORDS))
        if max_records and len(failures) > max_records:
            del failures[:-max_records]

    def _collect_localization_failure_debug(
        self,
        tracker_states: List[Dict[str, Any]],
        anchors: List[SubtitleAnchor],
    ) -> List[Dict[str, Any]]:
        failures: List[Dict[str, Any]] = []
        max_records = max(0, int(settings.SUBTITLE_LOCALIZER_FAILURE_DEBUG_MAX_RECORDS))
        for anchor_idx, tracker_state in enumerate(tracker_states):
            anchor = anchors[anchor_idx] if anchor_idx < len(anchors) else None
            anchor_failures = list(tracker_state.get("localization_failures") or [])
            if max_records:
                anchor_failures = anchor_failures[-max_records:]
            for failure in anchor_failures:
                failures.append({
                    "anchor_index": anchor_idx,
                    "anchor_source": anchor.source if anchor is not None else "",
                    "anchor_position_mode": anchor.position_mode if anchor is not None else "",
                    **failure,
                })
        return failures

    def _localize_variety_recall_candidates(
        self,
        candidates: List[Dict[str, Any]],
        search_region: Tuple[int, int, int, int],
        frame_shape: Tuple[int, ...],
    ) -> Optional[dict]:
        if not candidates:
            return None

        frame_height, frame_width = frame_shape[:2]
        search_x1, _, search_x2, search_y2 = search_region
        search_width = max(1, search_x2 - search_x1)
        scored = []
        for candidate in candidates:
            if self._is_variety_right_overlay_detection(candidate, frame_width):
                continue
            text = candidate.get("text", "")
            if not _has_cjk_text(text):
                continue
            box = candidate["box"]
            center_x_ratio = candidate["center_x"] / max(1, frame_width)
            bottom_ratio = box[3] / max(1, frame_height)
            if center_x_ratio < 0.24 or center_x_ratio > 0.78:
                continue
            if bottom_ratio < 0.66:
                continue
            center_prior = 1.0 - min(1.0, abs(center_x_ratio - 0.52) / 0.30)
            bottom_prior = 1.0 - min(1.0, max(0.0, float(search_y2 - box[3])) / max(1.0, frame_height * 0.10))
            width_prior = min(1.0, max(1, box[2] - box[0]) / max(1.0, search_width * 0.32))
            speaker_penalty = 0.28 if self._is_variety_speaker_tag(candidate, frame_width) else 0.0
            score = (
                0.34 * center_prior
                + 0.34 * bottom_prior
                + 0.16 * width_prior
                + 0.16 * float(candidate.get("confidence") or 0.0)
                - speaker_penalty
            )
            candidate["variety_recall_score"] = float(score)
            scored.append(candidate)

        if not scored:
            return None

        scored = sorted(scored, key=lambda candidate: candidate["variety_recall_score"], reverse=True)
        primary = scored[0]
        selected = [primary]
        primary_box = primary["box"]
        max_vertical_gap = max(24, int(primary["height"] * 1.8))
        for candidate in scored[1:]:
            if candidate["line_index"] == primary["line_index"]:
                continue
            if len(selected) >= 2:
                break
            if abs(candidate["center_y"] - primary["center_y"]) > max_vertical_gap:
                continue
            if self._is_variety_speaker_tag(candidate, frame_width):
                continue
            horizontal_overlap = self._horizontal_overlap_ratio(primary_box, candidate["box"])
            center_offset = abs(candidate["center_x"] - primary["center_x"])
            if horizontal_overlap < 0.20 and center_offset > search_width * 0.22:
                continue
            selected.append(candidate)

        selected = sorted(selected, key=lambda candidate: candidate["center_y"])
        selected_detections = [det for candidate in selected for det in candidate["detections"]]
        tight_box = self._line_to_box(selected_detections)
        tight_region = self._pad_tight_box(tight_box, frame_shape)
        return {
            "recognition_region": tight_region,
            "selected_detections": selected_detections,
            "debug": {
                "mode": "variety_recall",
                "search_region": [int(v) for v in search_region],
                "tight_box": [int(v) for v in tight_box],
                "tight_region": [int(v) for v in tight_region],
                "selected_line_indices": [candidate["line_index"] for candidate in selected],
                "line_candidates": [
                    {
                        "line_index": candidate["line_index"],
                        "box": [int(v) for v in candidate["box"]],
                        "text": candidate["text"],
                        "confidence": round(float(candidate["confidence"]), 4),
                        "variety_recall_score": round(float(candidate.get("variety_recall_score", 0.0)), 4),
                        "right_overlay": self._is_variety_right_overlay_detection(candidate, frame_width),
                        "speaker_tag": self._is_variety_speaker_tag(candidate, frame_width),
                    }
                    for candidate in candidates
                ],
            },
        }

    def _localize_subtitle_region(
        self,
        detections: List[dict],
        search_region: Tuple[int, int, int, int],
        frame_shape: Tuple[int, ...],
        anchor: SubtitleAnchor,
        tracker_state: Dict[str, Any],
        timestamp: Optional[float] = None,
    ) -> Optional[dict]:
        cleaned = self._clean_text_detections(detections)
        if not cleaned:
            self._record_localization_failure(
                tracker_state,
                reason="no_cleaned_detections",
                search_region=search_region,
                frame_shape=frame_shape,
                timestamp=timestamp,
                extra_debug={
                    "coarse_detection_count": len(detections),
                    "cleaned_detection_count": 0,
                },
            )
            return None

        lines = self._group_detections_into_lines(cleaned)
        if not lines:
            self._record_localization_failure(
                tracker_state,
                reason="no_grouped_lines",
                search_region=search_region,
                frame_shape=frame_shape,
                timestamp=timestamp,
                extra_debug={
                    "coarse_detection_count": len(detections),
                    "cleaned_detection_count": len(cleaned),
                },
            )
            return None

        search_x1, search_y1, search_x2, search_y2 = search_region
        search_width = max(1, search_x2 - search_x1)
        search_height = max(1, search_y2 - search_y1)
        frame_height, frame_width = frame_shape[:2]

        stable_box = tracker_state.get("stable_box")
        previous_meta = tracker_state.get("last_subtitle_meta")
        pending_meta = tracker_state.get("pending_candidate")
        if stable_box is not None:
            target_center_x = (stable_box[0] + stable_box[2]) / 2
            target_center_y = (stable_box[1] + stable_box[3]) / 2
        else:
            target_center_x = anchor.center_x * frame_width
            target_center_y = anchor.center_y * frame_height

        position_mode = (anchor.position_mode or "bottom").lower()
        candidates = []
        for idx, line in enumerate(lines):
            line_box = self._line_to_box(line)
            line_text = self._join_texts([det['text'] for det in line])
            normalized_text = re.sub(r"\s+", "", line_text)
            line_width = max(1, line_box[2] - line_box[0])
            line_height = max(1, line_box[3] - line_box[1])
            center_x = (line_box[0] + line_box[2]) / 2
            center_y = (line_box[1] + line_box[3]) / 2
            conf = float(np.mean([det['confidence'] for det in line]))
            width_ratio = line_width / search_width
            candidate_meta = self._build_subtitle_meta(line_box, line_text)
            candidates.append({
                "line_index": idx,
                "detections": line,
                "box": line_box,
                "center_x": center_x,
                "center_y": center_y,
                "height": line_height,
                "bottom_y": line_box[3],
                "text": line_text,
                "normalized_text": normalized_text,
                "confidence": conf,
                "width_ratio": width_ratio,
                "frame_width_ratio": line_width / max(1, frame_width),
                "candidate_meta": candidate_meta,
                "component_heights": [max(1, det['box'][3] - det['box'][1]) for det in line],
            })

        if self.variety_recall_enabled:
            localized = self._localize_variety_recall_candidates(
                candidates,
                search_region=search_region,
                frame_shape=frame_shape,
            )
            if localized:
                return localized

        dense_text_scene_score, dense_text_scene_breakdown = self._compute_dense_text_scene_score(
            candidates,
            component_count=len(cleaned),
            search_height=search_height,
        )
        dense_text_scene_suspect = (
            dense_text_scene_score >= self.localizer_profile["dense_text_scene_score_threshold"]
            and len(candidates) >= 4
        )
        dense_text_scene_soft = (
            dense_text_scene_score >= max(0.55, self.localizer_profile["dense_text_scene_score_threshold"] - 0.05)
            and len(candidates) >= 8
            and len(cleaned) >= 18
        )
        dense_text_scene_extreme = (
            dense_text_scene_score >= max(0.50, self.localizer_profile["dense_text_scene_score_threshold"] - 0.07)
            and len(candidates) >= 12
            and len(cleaned) >= 24
        )

        if position_mode == "top":
            ordered_candidates = sorted(candidates, key=lambda candidate: candidate["box"][1])
        elif position_mode == "middle":
            ordered_candidates = sorted(candidates, key=lambda candidate: abs(candidate["center_y"] - target_center_y))
        else:
            ordered_candidates = sorted(candidates, key=lambda candidate: candidate["box"][3], reverse=True)
        rank_map = {
            candidate["line_index"]: rank
            for rank, candidate in enumerate(ordered_candidates)
        }
        max_rank = max(1, len(candidates) - 1)

        for candidate in candidates:
            line_box = candidate["box"]
            width_ratio = candidate["width_ratio"]
            frame_width_ratio = candidate["frame_width_ratio"]
            line_height = candidate["height"]
            normalized_text = candidate["normalized_text"]
            candidate_meta = candidate["candidate_meta"]
            prev_support = self._compute_candidate_temporal_support(candidate_meta, previous_meta, search_width, search_height)
            pending_support = self._compute_candidate_temporal_support(candidate_meta, pending_meta, search_width, search_height)
            temporal_support = max(prev_support, pending_support)
            overlay_track_support = self._compute_overlay_track_support(
                candidate_meta,
                tracker_state,
                search_width,
                search_height,
                current_timestamp=timestamp,
            )
            center_x_prior = 1.0 - min(1.0, abs(candidate["center_x"] - target_center_x) / max(1.0, search_width * 0.40))
            position_prior = self._compute_position_alignment_prior(line_box, search_region, anchor)
            text_len_prior = min(1.0, len(normalized_text) / 8.0)
            width_prior = min(1.0, width_ratio / 0.30)
            negative_penalty, penalty_breakdown = self._compute_subtitle_text_penalties(candidate["text"], width_ratio)
            style_match = self._compute_style_match(candidate_meta, tracker_state, current_timestamp=timestamp)
            style_mismatch = 0.0
            style_profile = tracker_state.get("subtitle_style")
            if style_profile and style_profile.get("count", 0) >= settings.SUBTITLE_LOCALIZER_STYLE_PROFILE_MIN_COUNT:
                style_mismatch = 1.0 - style_match
            edge_column_score = self._compute_edge_column_score(candidate, candidates, search_region)

            component_heights = candidate["component_heights"]
            median_component_height = float(np.median(component_heights)) if component_heights else float(line_height)
            stacked_layout_score = 0.0
            if len(candidate["detections"]) > 1 and median_component_height > 0:
                stacked_layout_score = max(
                    0.0,
                    min(1.0, (line_height / max(1.0, median_component_height) - 1.55) / 0.60),
                )

            left_margin = max(0.0, float(line_box[0] - search_x1))
            right_margin = max(0.0, float(search_x2 - line_box[2]))
            edge_attachment = 1.0 - min(1.0, min(left_margin, right_margin) / max(1.0, search_width * 0.18))
            off_center_overlay = max(0.0, (0.55 - center_x_prior) / 0.55)
            frame_center_x_ratio = candidate["center_x"] / max(1.0, float(frame_width))
            frame_bottom_ratio = line_box[3] / max(1.0, float(frame_height))
            line_aspect_ratio = line_width / max(1.0, float(line_height))
            has_east_asian = any(
                ('\u4e00' <= ch <= '\u9fff')
                or ('\u3040' <= ch <= '\u30ff')
                or ('\uac00' <= ch <= '\ud7a3')
                for ch in normalized_text
            )
            bottom_centered_compact_subtitle = (
                position_mode == "bottom"
                and len(normalized_text) <= 12
                and candidate["confidence"] >= 0.88
                and frame_bottom_ratio >= 0.82
                and 0.28 <= frame_center_x_ratio <= 0.72
                and center_x_prior >= 0.76
                and edge_attachment < 0.35
                and line_aspect_ratio >= 1.25
                and bool(normalized_text)
            )
            short_centered_east_asian = (
                has_east_asian
                and len(normalized_text) <= 4
                and (position_prior >= 0.62 or bottom_centered_compact_subtitle)
                and center_x_prior >= 0.58
                and edge_attachment < 0.82
            )
            if position_mode == "top":
                corner_alignment = 1.0 - min(1.0, max(0.0, float(line_box[1] - search_y1)) / max(1.0, search_height * 0.18))
            elif position_mode == "middle":
                corner_alignment = 0.0
            else:
                corner_alignment = 1.0 - min(1.0, max(0.0, float(search_y2 - line_box[3])) / max(1.0, search_height * 0.18))
            corner_attachment = edge_attachment * corner_alignment
            rank_penalty = 0.0
            if len(candidates) > 1 and position_mode != "middle":
                rank_penalty = rank_map.get(candidate["line_index"], 0) / max_rank
            band_mismatch = 1.0 - position_prior
            signage_score, signage_breakdown = self._compute_signage_overlay_score(
                candidate["text"],
                width_ratio,
                center_x_prior,
                position_prior,
                frame_width_ratio=frame_width_ratio,
            )
            signage_confirmation_needed = (
                signage_score >= self.localizer_profile["signage_score_threshold"]
                and "mixed_script" in signage_breakdown
                and (
                    "digit_tag" in signage_breakdown
                    or "tag_separator" in signage_breakdown
                    or "latin_numeric" in signage_breakdown
                    or (
                        "compact_label" in signage_breakdown
                        and center_x_prior < 0.88
                    )
                )
            )
            has_established_subtitle_context = (
                previous_meta is not None
                or (
                    style_profile is not None
                    and style_profile.get("count", 0) >= settings.SUBTITLE_LOCALIZER_STYLE_PROFILE_MIN_COUNT
                )
            )
            subtitle_only_reject_reasons = self._compute_subtitle_only_reject_reasons(
                candidate,
                frame_shape,
                position_mode,
                has_established_subtitle_context,
            )
            signage_confirmed = (
                has_established_subtitle_context
                and (
                    temporal_support >= 0.72
                    or prev_support >= settings.SUBTITLE_LOCALIZER_PREV_MATCH_THRESHOLD
                    or pending_support >= settings.SUBTITLE_LOCALIZER_PENDING_MATCH_THRESHOLD
                )
            )
            compact_short_dialogue_candidate = (
                has_east_asian
                and len(normalized_text) <= 4
                and center_x_prior >= 0.90
                and (position_prior >= 0.72 or bottom_centered_compact_subtitle)
            )
            contextless_compact_label = (
                not has_established_subtitle_context
                and frame_width_ratio < 0.15
                and len(normalized_text) <= 12
                and temporal_support < 0.72
                and not compact_short_dialogue_candidate
                and not bottom_centered_compact_subtitle
            )
            contextless_mixed_script_label = (
                not has_established_subtitle_context
                and frame_width_ratio < 0.12
                and "mixed_script" in signage_breakdown
                and "compact_label" in signage_breakdown
            )
            style_drift_suspect = (
                style_profile is not None
                and style_profile.get("count", 0) >= settings.SUBTITLE_LOCALIZER_STYLE_PROFILE_MIN_COUNT
                and style_match < 0.48
                and temporal_support < 0.45
            )
            dense_text_scene_overlay = (
                (
                    dense_text_scene_soft
                    and (
                        len(candidate["detections"]) >= 3
                        or center_x_prior < 0.68
                        or edge_attachment >= 0.18
                        or style_drift_suspect
                        or signage_score >= max(0.32, self.localizer_profile["signage_score_threshold"] - 0.18)
                    )
                )
                or (
                    dense_text_scene_extreme
                    and temporal_support < 0.45
                    and frame_width_ratio < 0.30
                )
            )

            subtitle_score = (
                0.22 * candidate["confidence"]
                + 0.34 * position_prior
                + 0.12 * center_x_prior
                + 0.08 * width_prior
                + 0.06 * text_len_prior
                + 0.10 * temporal_support
                + 0.08 * style_match
            )
            if short_centered_east_asian:
                subtitle_score += 0.06
            if bottom_centered_compact_subtitle:
                subtitle_score += 0.08
            subtitle_score = max(0.0, min(1.0, float(subtitle_score - negative_penalty)))
            overlay_score = (
                0.22 * edge_attachment
                + 0.14 * corner_attachment
                + 0.24 * edge_column_score
                + 0.18 * stacked_layout_score
                + 0.12 * rank_penalty
                + 0.12 * overlay_track_support
                + 0.10 * band_mismatch
                + 0.08 * style_mismatch
                + 0.12 * off_center_overlay
                + 0.18 * signage_score
                + 0.28 * dense_text_scene_score
            )
            overlay_score = max(0.0, min(1.0, float(overlay_score)))
            final_margin = subtitle_score - overlay_score

            reject_reasons = []
            if (
                width_ratio < self.localizer_profile["min_width_ratio"]
                and len(normalized_text) < 4
                and not short_centered_east_asian
                and not bottom_centered_compact_subtitle
            ):
                reject_reasons.append("line_too_narrow")
            if subtitle_score < settings.SUBTITLE_LOCALIZER_MIN_SCORE:
                reject_reasons.append("score_too_low")
            if final_margin < 0:
                reject_reasons.append("overlay_dominant")
            if edge_column_score >= self.localizer_profile["credit_column_score_threshold"] and temporal_support < 0.55:
                reject_reasons.append("credit_column_suspect")
            if stacked_layout_score >= 0.65 and temporal_support < 0.45:
                reject_reasons.append("stacked_layout_suspect")
            if overlay_track_support >= 0.45 and (stacked_layout_score >= 0.45 or width_ratio < 0.12):
                reject_reasons.append("overlay_track_match")
            if dense_text_scene_suspect:
                reject_reasons.append("dense_text_scene")
            if dense_text_scene_overlay:
                reject_reasons.append("dense_text_scene_overlay")
            if contextless_compact_label:
                reject_reasons.append("contextless_compact_label")
            if contextless_mixed_script_label:
                reject_reasons.append("contextless_mixed_script_label")
            if signage_confirmation_needed and not signage_confirmed:
                reject_reasons.append("signage_unconfirmed")
            reject_reasons.extend(subtitle_only_reject_reasons)

            pending_eligible = (
                position_prior >= 0.45
                and edge_attachment < 0.75
                and edge_column_score < 0.45
                and stacked_layout_score < 0.6
                and negative_penalty < 0.12
                and not dense_text_scene_suspect
                and (
                    width_ratio >= 0.12
                    or any('\u4e00' <= ch <= '\u9fff' for ch in normalized_text)
                    or bottom_centered_compact_subtitle
                )
            )

            accepted = False
            waiting_confirmation = False
            if (
                subtitle_score >= settings.SUBTITLE_LOCALIZER_DIRECT_ACCEPT_SCORE
                and final_margin >= self.localizer_profile["direct_accept_margin"]
                and (not signage_confirmation_needed or signage_confirmed)
            ):
                accepted = True
            elif (
                subtitle_score >= settings.SUBTITLE_LOCALIZER_PENDING_SCORE
                and final_margin >= settings.SUBTITLE_LOCALIZER_PENDING_MARGIN
            ):
                if (
                    pending_support >= settings.SUBTITLE_LOCALIZER_PENDING_MATCH_THRESHOLD
                    and overlay_score < subtitle_score * 0.6
                    and edge_attachment < 0.75
                    and stacked_layout_score < 0.6
                ):
                    accepted = True
                elif (
                    prev_support >= settings.SUBTITLE_LOCALIZER_PREV_MATCH_THRESHOLD
                    and overlay_score < subtitle_score * 0.6
                    and edge_attachment < 0.75
                    and stacked_layout_score < 0.6
                ):
                    accepted = True
                elif pending_eligible:
                    waiting_confirmation = True

            candidate.update({
                "position_prior": position_prior,
                "center_x_prior": center_x_prior,
                "temporal_support": temporal_support,
                "previous_support": prev_support,
                "pending_support": pending_support,
                "overlay_track_support": overlay_track_support,
                "style_match": style_match,
                "edge_column_score": edge_column_score,
                "signage_score": signage_score,
                "signage_breakdown": signage_breakdown,
                "signage_confirmation_needed": signage_confirmation_needed,
                "signage_confirmed": signage_confirmed,
                "bottom_centered_compact_subtitle": bottom_centered_compact_subtitle,
                "subtitle_only_reject_reasons": subtitle_only_reject_reasons,
                "dense_text_scene_score": dense_text_scene_score,
                "dense_text_scene_suspect": dense_text_scene_suspect,
                "dense_text_scene_soft": dense_text_scene_soft,
                "dense_text_scene_extreme": dense_text_scene_extreme,
                "dense_text_scene_overlay": dense_text_scene_overlay,
                "edge_attachment": edge_attachment,
                "corner_attachment": corner_attachment,
                "stacked_layout_score": stacked_layout_score,
                "rank_penalty": rank_penalty,
                "band_mismatch": band_mismatch,
                "negative_penalty": negative_penalty,
                "penalty_breakdown": penalty_breakdown,
                "subtitle_score": subtitle_score,
                "overlay_score": overlay_score,
                "score": final_margin,
                "accepted": accepted and not reject_reasons,
                "waiting_confirmation": waiting_confirmation and not reject_reasons,
                "reject_reasons": reject_reasons,
            })

        accepted = [candidate for candidate in candidates if candidate["accepted"]]
        if not accepted:
            waiting = sorted(
                [candidate for candidate in candidates if candidate["waiting_confirmation"]],
                key=lambda candidate: candidate["subtitle_score"] - candidate["overlay_score"],
                reverse=True,
            )
            for candidate in candidates:
                if candidate["accepted"] or candidate["waiting_confirmation"]:
                    continue
                if (
                    candidate["overlay_score"] >= max(candidate["subtitle_score"], 0.35)
                    or candidate["overlay_track_support"] >= 0.35
                    or candidate["edge_attachment"] >= 0.9
                    or candidate["stacked_layout_score"] >= 0.7
                    or candidate["band_mismatch"] >= 0.75
                ):
                    self._remember_overlay_candidate(
                        tracker_state,
                        candidate["candidate_meta"],
                        timestamp=timestamp,
                    )
            if waiting:
                tracker_state["pending_candidate"] = waiting[0]["candidate_meta"]
            else:
                tracker_state["pending_candidate"] = None
            self._record_localization_failure(
                tracker_state,
                reason="waiting_confirmation" if waiting else "no_accepted_candidates",
                search_region=search_region,
                frame_shape=frame_shape,
                timestamp=timestamp,
                candidates=candidates,
                extra_debug={
                    "coarse_detection_count": len(detections),
                    "cleaned_detection_count": len(cleaned),
                    "line_count": len(lines),
                    "dense_text_scene_score": round(float(dense_text_scene_score), 4),
                    "dense_text_scene_suspect": dense_text_scene_suspect,
                    "dense_text_scene_soft": dense_text_scene_soft,
                    "dense_text_scene_extreme": dense_text_scene_extreme,
                    "dense_text_scene_breakdown": dense_text_scene_breakdown,
                },
            )
            return None

        accepted = sorted(accepted, key=lambda candidate: candidate["score"], reverse=True)
        tracker_state["pending_candidate"] = None
        tracker_state["last_localization_failure"] = None

        primary = accepted[0]
        selected = [primary]
        primary_box = primary["box"]
        max_vertical_gap = max(24, int(primary["height"] * 1.4))

        for candidate in accepted[1:]:
            if candidate["line_index"] == primary["line_index"]:
                continue
            if abs(candidate["center_y"] - primary["center_y"]) > max_vertical_gap:
                continue
            if candidate["score"] < primary["score"] * 0.7:
                continue
            overlap = self._horizontal_overlap_ratio(primary_box, candidate["box"])
            center_offset = abs(candidate["center_x"] - primary["center_x"])
            if overlap < 0.25 and center_offset > search_width * 0.18:
                continue
            selected.append(candidate)
            if len(selected) >= 2:
                break

        selected = sorted(selected, key=lambda candidate: candidate["center_y"])
        selected_detections = [det for candidate in selected for det in candidate["detections"]]
        tight_box = self._line_to_box(selected_detections)
        tight_region = self._pad_tight_box(tight_box, frame_shape)
        return {
            "recognition_region": tight_region,
            "selected_detections": selected_detections,
            "debug": {
                "search_region": [int(v) for v in search_region],
                "tight_box": [int(v) for v in tight_box],
                "tight_region": [int(v) for v in tight_region],
                "selected_line_indices": [candidate["line_index"] for candidate in selected],
                "dense_text_scene_score": round(float(dense_text_scene_score), 4),
                "dense_text_scene_suspect": dense_text_scene_suspect,
                "dense_text_scene_soft": dense_text_scene_soft,
                "dense_text_scene_extreme": dense_text_scene_extreme,
                "dense_text_scene_breakdown": dense_text_scene_breakdown,
                "line_candidates": [
                    {
                        "line_index": candidate["line_index"],
                        "box": [int(v) for v in candidate["box"]],
                        "text": candidate["text"],
                        "confidence": round(candidate["confidence"], 4),
                        "width_ratio": round(candidate["width_ratio"], 4),
                        "frame_width_ratio": round(candidate["frame_width_ratio"], 4),
                        "center_x_prior": round(candidate["center_x_prior"], 4),
                        "position_prior": round(candidate["position_prior"], 4),
                        "temporal_support": round(candidate["temporal_support"], 4),
                        "previous_support": round(candidate["previous_support"], 4),
                        "pending_support": round(candidate["pending_support"], 4),
                        "overlay_track_support": round(candidate["overlay_track_support"], 4),
                        "style_match": round(candidate["style_match"], 4),
                        "edge_attachment": round(candidate["edge_attachment"], 4),
                        "edge_column_score": round(candidate["edge_column_score"], 4),
                        "signage_score": round(candidate["signage_score"], 4),
                        "signage_breakdown": candidate["signage_breakdown"],
                        "signage_confirmation_needed": candidate["signage_confirmation_needed"],
                        "signage_confirmed": candidate["signage_confirmed"],
                        "bottom_centered_compact_subtitle": candidate["bottom_centered_compact_subtitle"],
                        "subtitle_only_reject_reasons": candidate["subtitle_only_reject_reasons"],
                        "dense_text_scene_score": round(candidate["dense_text_scene_score"], 4),
                        "dense_text_scene_suspect": candidate["dense_text_scene_suspect"],
                        "dense_text_scene_soft": candidate["dense_text_scene_soft"],
                        "dense_text_scene_extreme": candidate["dense_text_scene_extreme"],
                        "dense_text_scene_overlay": candidate["dense_text_scene_overlay"],
                        "corner_attachment": round(candidate["corner_attachment"], 4),
                        "stacked_layout_score": round(candidate["stacked_layout_score"], 4),
                        "rank_penalty": round(candidate["rank_penalty"], 4),
                        "band_mismatch": round(candidate["band_mismatch"], 4),
                        "negative_penalty": round(candidate["negative_penalty"], 4),
                        "penalty_breakdown": {k: round(v, 4) for k, v in candidate["penalty_breakdown"].items()},
                        "subtitle_score": round(candidate["subtitle_score"], 4),
                        "overlay_score": round(candidate["overlay_score"], 4),
                        "score": round(candidate["score"], 4),
                        "accepted": candidate["accepted"],
                        "waiting_confirmation": candidate["waiting_confirmation"],
                        "reject_reasons": candidate["reject_reasons"],
                    }
                    for candidate in candidates
                ],
            },
        }

    def _join_texts(self, pieces: List[str]) -> str:
        if not pieces:
            return ""

        merged = pieces[0].strip()
        for piece in pieces[1:]:
            right = piece.strip()
            if not right:
                continue
            if self._needs_space(merged[-1], right[0]):
                merged += " " + right
            else:
                merged += right

        merged = re.sub(r'\s+', ' ', merged).strip()
        return merged

    def _join_line_texts(self, line: List[dict]) -> str:
        """Join same-line detections, keeping only *visual* gaps as spaces.

        PaddleOCR recognition drops spaces inside CJK text, so the box gap is
        the only remaining signal. A gap comparable to a glyph width is an
        intentional separator (speaker change / phrase pause); anything
        smaller is detector fragmentation of a continuous phrase and must be
        concatenated without inventing a space. Latin/digit boundaries always
        get a space so English words don't fuse.
        """
        ordered = sorted(
            (det for det in line if (det.get('text') or '').strip()),
            key=lambda det: det['box'][0],
        )
        if not ordered:
            return ""

        merged = ordered[0]['text'].strip()
        prev_box = ordered[0]['box']
        for det in ordered[1:]:
            right = det['text'].strip()
            box = det['box']
            gap = float(box[0]) - float(prev_box[2])
            glyph_height = max(1.0, float(min(prev_box[3] - prev_box[1], box[3] - box[1])))
            has_visual_gap = gap >= max(6.0, glyph_height * 0.45)
            left_char = merged[-1] if merged else ""
            ascii_boundary = (
                bool(left_char)
                and left_char.isascii() and left_char.isalnum()
                and right[0].isascii() and right[0].isalnum()
            )
            if merged and (has_visual_gap or ascii_boundary):
                merged += " " + right
            else:
                merged += right
            prev_box = box

        return re.sub(r'\s+', ' ', merged).strip()

    def _needs_space(self, left_char: str, right_char: str) -> bool:
        return left_char.isalnum() and right_char.isalnum()

    def _is_implausible_merged_subtitle(self, detection: Optional[dict]) -> bool:
        if not detection:
            return True
        lines = [line.strip() for line in (detection.get("text") or "").splitlines() if line.strip()]
        return len(lines) > 2

    def _summarize_anchor_detection(self, detection: DetectedText) -> Optional[Dict[str, Any]]:
        sample_debug = detection.sample_debug or {}
        search_region = sample_debug.get("search_region")
        if not isinstance(search_region, list) or len(search_region) != 4:
            return None

        rx1, _, rx2, _ = [int(v) for v in search_region]
        region_width = max(1.0, float(rx2 - rx1))
        box = detection.box
        width_ratio = max(0.0, min(1.0, (box[2] - box[0]) / region_width))
        center_x = (box[0] + box[2]) / 2
        region_center_x = (rx1 + rx2) / 2
        center_x_prior = 1.0 - min(1.0, abs(center_x - region_center_x) / max(1.0, region_width * 0.42))
        left_margin = max(0.0, float(box[0] - rx1))
        right_margin = max(0.0, float(rx2 - box[2]))
        edge_attachment = 1.0 - min(1.0, min(left_margin, right_margin) / max(1.0, region_width * 0.18))
        normalized_text = self._normalize_subtitle_candidate_text(detection.text or "")

        return {
            "anchor_source": sample_debug.get("anchor_source") or "unknown",
            "anchor_position_mode": (sample_debug.get("anchor_position_mode") or "auto").lower(),
            "width_ratio": float(width_ratio),
            "center_x_prior": float(max(0.0, min(1.0, center_x_prior))),
            "edge_attachment": float(max(0.0, min(1.0, edge_attachment))),
            "normalized_text": normalized_text,
            "is_short_text": len(normalized_text) <= 10,
            "is_visual_band_anchor": "visual_band" in (sample_debug.get("anchor_source") or "").lower(),
        }

    def _should_drop_anchor_detections(
        self,
        anchor_source: str,
        anchor_stats: Dict[str, Any],
        has_bottom_anchor: bool,
    ) -> bool:
        count = int(anchor_stats["count"])
        if count < 5:
            return False

        position_mode = anchor_stats["position_mode"]
        unique_ratio = anchor_stats["unique_ratio"]
        repeated_text_share = anchor_stats["repeated_text_share"]
        short_text_share = anchor_stats["short_text_share"]
        median_width_ratio = anchor_stats["median_width_ratio"]
        median_center_x_prior = anchor_stats["median_center_x_prior"]
        median_edge_attachment = anchor_stats["median_edge_attachment"]
        weak_anchor = anchor_stats["weak_anchor"]

        if position_mode != "bottom":
            if (
                has_bottom_anchor
                and repeated_text_share >= 0.55
                and unique_ratio <= 0.40
                and count <= 8
                and median_width_ratio <= 0.45
            ):
                return True
            if (
                repeated_text_share >= 0.34
                and unique_ratio <= 0.60
                and short_text_share >= 0.60
                and (
                    median_center_x_prior < 0.78
                    or median_width_ratio < 0.24
                    or median_edge_attachment > 0.82
                )
            ):
                return True
            if (
                has_bottom_anchor
                and weak_anchor
                and repeated_text_share >= 0.30
                and short_text_share >= 0.50
                and median_center_x_prior < 0.84
            ):
                return True
            return False

        if (
            weak_anchor
            and repeated_text_share >= 0.50
            and unique_ratio <= 0.35
            and short_text_share >= 0.80
            and median_width_ratio < 0.18
            and median_edge_attachment > 0.82
        ):
            return True

        return False

    def _filter_repetitive_anchor_overlays(
        self,
        detections: List[DetectedText],
        anchors: List[SubtitleAnchor],
    ) -> List[DetectedText]:
        if not detections:
            return detections

        has_bottom_anchor = any((anchor.position_mode or "").lower() == "bottom" for anchor in anchors)
        stats_by_anchor: Dict[str, Dict[str, Any]] = {}
        detections_by_anchor: Dict[str, List[DetectedText]] = {}

        for detection in detections:
            summary = self._summarize_anchor_detection(detection)
            if not summary:
                continue
            anchor_source = summary["anchor_source"]
            anchor_stats = stats_by_anchor.setdefault(anchor_source, {
                "count": 0,
                "position_mode": summary["anchor_position_mode"],
                "weak_anchor": summary["is_visual_band_anchor"] or anchor_source.startswith("default_"),
                "width_ratios": [],
                "center_x_priors": [],
                "edge_attachments": [],
                "texts": [],
                "short_text_count": 0,
            })
            anchor_stats["count"] += 1
            anchor_stats["width_ratios"].append(summary["width_ratio"])
            anchor_stats["center_x_priors"].append(summary["center_x_prior"])
            anchor_stats["edge_attachments"].append(summary["edge_attachment"])
            if summary["normalized_text"]:
                anchor_stats["texts"].append(summary["normalized_text"])
            if summary["is_short_text"]:
                anchor_stats["short_text_count"] += 1
            detections_by_anchor.setdefault(anchor_source, []).append(detection)

        dropped_sources = set()
        for anchor_source, anchor_stats in stats_by_anchor.items():
            texts = anchor_stats["texts"]
            repeated_text_share = 0.0
            unique_ratio = 1.0
            if texts:
                counts: Dict[str, int] = {}
                for text in texts:
                    counts[text] = counts.get(text, 0) + 1
                repeated_text_share = max(counts.values()) / max(1, len(texts))
                unique_ratio = len(counts) / max(1, len(texts))

            anchor_stats["repeated_text_share"] = float(repeated_text_share)
            anchor_stats["unique_ratio"] = float(unique_ratio)
            anchor_stats["short_text_share"] = float(anchor_stats["short_text_count"] / max(1, anchor_stats["count"]))
            anchor_stats["median_width_ratio"] = float(np.median(anchor_stats["width_ratios"])) if anchor_stats["width_ratios"] else 0.0
            anchor_stats["median_center_x_prior"] = float(np.median(anchor_stats["center_x_priors"])) if anchor_stats["center_x_priors"] else 0.0
            anchor_stats["median_edge_attachment"] = float(np.median(anchor_stats["edge_attachments"])) if anchor_stats["edge_attachments"] else 0.0

            if self._should_drop_anchor_detections(anchor_source, anchor_stats, has_bottom_anchor):
                dropped_sources.add(anchor_source)

        if not dropped_sources:
            return detections

        filtered = [
            detection
            for detection in detections
            if (detection.sample_debug or {}).get("anchor_source") not in dropped_sources
        ]
        logger.info(
            "subtitle overlay anchor filter dropped_sources=%s removed=%s kept=%s",
            sorted(dropped_sources),
            len(detections) - len(filtered),
            len(filtered),
        )
        return filtered

    def _filter_competing_nonbottom_subtitles(
        self,
        subtitles: List[Subtitle],
        anchors: List[SubtitleAnchor],
    ) -> List[Subtitle]:
        if not subtitles:
            return subtitles
        if not any((anchor.position_mode or "").lower() == "bottom" for anchor in anchors):
            return subtitles
        if len(anchors) <= 1:
            return subtitles

        filtered: List[Subtitle] = []
        dropped = 0
        for subtitle in subtitles:
            raw_detections = (subtitle.debug_info or {}).get("raw_detections") or []
            anchor_modes = {
                (((item.get("sample_debug") or {}).get("anchor_position_mode")) or "").lower()
                for item in raw_detections
            }
            anchor_modes.discard("")
            if anchor_modes and "bottom" not in anchor_modes:
                dropped += 1
                continue
            filtered.append(subtitle)

        if dropped:
            logger.info(
                "subtitle non-bottom competing track filter dropped=%s kept=%s",
                dropped,
                len(filtered),
            )
        return filtered

    def _is_dense_scene_overlay_subtitle(self, subtitle: Subtitle) -> bool:
        raw_detections = (subtitle.debug_info or {}).get("raw_detections") or []
        if not raw_detections:
            return False

        suspect_hits = 0
        inspected = 0
        dense_threshold = max(0.55, self.localizer_profile["dense_text_scene_score_threshold"] - 0.05)
        dense_extreme_threshold = max(0.50, self.localizer_profile["dense_text_scene_score_threshold"] - 0.07)

        for item in raw_detections:
            sample_debug = item.get("sample_debug") or {}
            localization = sample_debug.get("localization") or {}
            line_candidates = localization.get("line_candidates") or []
            selected_line_indices = set(localization.get("selected_line_indices") or [])
            if not line_candidates or not selected_line_indices:
                continue

            credit_text_score, credit_text_breakdown = self._compute_credit_text_score(subtitle.text)
            dense_score = float(localization.get("dense_text_scene_score") or 0.0)
            dense_breakdown = localization.get("dense_text_scene_breakdown") or {}
            line_count = int(round(float(dense_breakdown.get("line_count") or 0.0)))
            component_count = int(round(float(dense_breakdown.get("component_count") or 0.0)))
            is_dense_scene = (
                dense_score >= dense_threshold
                and line_count >= 8
                and component_count >= 18
            )
            is_extreme_dense_scene = (
                dense_score >= dense_extreme_threshold
                and line_count >= 12
                and component_count >= 24
            )
            if not is_dense_scene and not is_extreme_dense_scene and credit_text_score < 0.44:
                continue

            selected_candidates = [
                candidate
                for candidate in line_candidates
                if candidate.get("line_index") in selected_line_indices
            ]
            if not selected_candidates:
                continue

            candidate = selected_candidates[0]
            inspected += 1
            center_x_prior = float(candidate.get("center_x_prior") or 0.0)
            edge_attachment = float(candidate.get("edge_attachment") or 0.0)
            style_match = float(candidate.get("style_match") or 0.0)
            temporal_support = float(candidate.get("temporal_support") or 0.0)
            frame_width_ratio = float(candidate.get("frame_width_ratio") or 0.0)
            signage_score = float(candidate.get("signage_score") or 0.0)
            organization_like = "organization_suffix" in credit_text_breakdown
            name_list_like = "short_name_list" in credit_text_breakdown
            latin_label_like = "latin_label_repeat" in credit_text_breakdown
            fragment_like = " " in (candidate.get("text") or "") or float(candidate.get("width_ratio") or 0.0) < 0.38

            if (
                center_x_prior < 0.68
                or edge_attachment >= 0.18
                or frame_width_ratio < 0.36
                or (is_extreme_dense_scene and frame_width_ratio < 0.30 and temporal_support < 0.45)
                or (credit_text_score >= 0.55 and style_match < 0.35 and frame_width_ratio < 0.25 and temporal_support < 0.82)
                or (organization_like and style_match < 0.35 and frame_width_ratio < 0.12)
                or (name_list_like and credit_text_score >= 0.65 and frame_width_ratio < 0.24 and temporal_support < 0.65)
                or (latin_label_like and style_match < 0.28 and frame_width_ratio < 0.10 and temporal_support < 0.20)
                or (style_match < 0.48 and temporal_support < 0.45)
                or signage_score >= max(0.32, self.localizer_profile["signage_score_threshold"] - 0.18)
                or fragment_like
            ):
                suspect_hits += 1

        return inspected > 0 and suspect_hits == inspected

    def _filter_dense_scene_overlay_subtitles(
        self,
        subtitles: List[Subtitle],
    ) -> List[Subtitle]:
        if not subtitles:
            return subtitles

        filtered: List[Subtitle] = []
        dropped = 0
        for subtitle in subtitles:
            if self._is_dense_scene_overlay_subtitle(subtitle):
                dropped += 1
                continue
            filtered.append(subtitle)

        if dropped:
            logger.info(
                "subtitle dense-scene overlay filter dropped=%s kept=%s",
                dropped,
                len(filtered),
            )
        return filtered

    def _collect_selected_candidate_metrics(self, subtitle: Subtitle) -> Dict[str, Any]:
        raw_detections = (subtitle.debug_info or {}).get("raw_detections") or []
        metrics: Dict[str, List[float]] = {
            "frame_width_ratio": [],
            "width_ratio": [],
            "edge_attachment": [],
            "style_match": [],
            "temporal_support": [],
            "dense_text_scene_score": [],
            "line_count": [],
            "component_count": [],
        }

        for item in raw_detections:
            sample_debug = item.get("sample_debug") or {}
            localization = sample_debug.get("localization") or {}
            selected_indices = set(localization.get("selected_line_indices") or [])
            dense_score = localization.get("dense_text_scene_score")
            dense_breakdown = localization.get("dense_text_scene_breakdown") or {}
            if dense_score is not None:
                metrics["dense_text_scene_score"].append(float(dense_score or 0.0))
            if dense_breakdown:
                metrics["line_count"].append(float(dense_breakdown.get("line_count") or 0.0))
                metrics["component_count"].append(float(dense_breakdown.get("component_count") or 0.0))

            for candidate in localization.get("line_candidates") or []:
                if selected_indices and candidate.get("line_index") not in selected_indices:
                    continue
                for key in (
                    "frame_width_ratio",
                    "width_ratio",
                    "edge_attachment",
                    "style_match",
                    "temporal_support",
                ):
                    value = candidate.get(key)
                    if value is not None:
                        metrics[key].append(float(value or 0.0))

        summary: Dict[str, Any] = {}
        for key, values in metrics.items():
            summary[key] = float(np.median(values)) if values else 0.0
        summary["sample_count"] = len(raw_detections)
        return summary

    def _is_structural_non_dialogue_subtitle(self, subtitle: Subtitle) -> bool:
        normalized_text = self._normalize_subtitle_candidate_text(subtitle.text or "")
        text_len = len(normalized_text)
        if text_len < int(settings.SUBTITLE_NON_DIALOGUE_LONG_LINE_MIN_CHARS):
            return False

        metrics = self._collect_selected_candidate_metrics(subtitle)
        duration = max(0.0, float(subtitle.end_time) - float(subtitle.start_time))
        sentence_like_score = self._compute_sentence_like_score(subtitle.text)
        width_ratio = max(
            float(metrics.get("frame_width_ratio") or 0.0),
            float(metrics.get("width_ratio") or 0.0) * 0.55,
        )
        edge_attachment = float(metrics.get("edge_attachment") or 0.0)
        style_match = float(metrics.get("style_match") or 0.0)
        temporal_support = float(metrics.get("temporal_support") or 0.0)
        dense_score = float(metrics.get("dense_text_scene_score") or 0.0)
        line_count = float(metrics.get("line_count") or 0.0)
        component_count = float(metrics.get("component_count") or 0.0)

        if sentence_like_score > float(settings.SUBTITLE_NON_DIALOGUE_SENTENCE_SCORE_MAX):
            return False
        if width_ratio < float(settings.SUBTITLE_NON_DIALOGUE_LONG_LINE_MIN_WIDTH_RATIO):
            return False

        long_intrusive_line = (
            duration >= float(settings.SUBTITLE_NON_DIALOGUE_LONG_LINE_MIN_DURATION)
            and (
                edge_attachment >= 0.62
                or style_match <= 0.48
                or dense_score >= 0.10
                or line_count >= 3
                or component_count >= 5
            )
        )
        single_frame_banner = (
            duration < float(settings.SUBTITLE_NON_DIALOGUE_LONG_LINE_MIN_DURATION)
            and edge_attachment >= 0.90
            and style_match <= 0.60
            and temporal_support <= 0.12
        )
        return bool(long_intrusive_line or single_frame_banner)

    def _filter_structural_non_dialogue_subtitles(
        self,
        subtitles: List[Subtitle],
    ) -> List[Subtitle]:
        if not subtitles:
            return subtitles

        filtered: List[Subtitle] = []
        dropped = 0
        for subtitle in subtitles:
            if self._is_structural_non_dialogue_subtitle(subtitle):
                dropped += 1
                continue
            filtered.append(subtitle)

        if dropped:
            logger.info(
                "subtitle structural non-dialogue filter dropped=%s kept=%s",
                dropped,
                len(filtered),
            )
        for index, subtitle in enumerate(filtered, start=1):
            subtitle.index = index
        return filtered

    def _subtitle_visual_features(self, subtitle: Subtitle) -> Optional[Dict[str, float]]:
        points = subtitle.polygon or []
        if points:
            xs = [float(point[0]) for point in points]
            ys = [float(point[1]) for point in points]
            x1, x2 = min(xs), max(xs)
            y1, y2 = min(ys), max(ys)
        elif subtitle.box:
            x1, y1, x2, y2 = [float(value) for value in subtitle.box]
        else:
            return None

        width = max(0.0, x2 - x1)
        height = max(0.0, y2 - y1)
        if width <= 1.0 or height <= 1.0:
            return None

        return {
            "x1": x1,
            "y1": y1,
            "x2": x2,
            "y2": y2,
            "width": width,
            "height": height,
            "center_x": (x1 + x2) / 2.0,
            "center_y": (y1 + y2) / 2.0,
            "bottom_y": y2,
        }

    def _build_main_visual_track_profile(self, subtitles: List[Subtitle]) -> Optional[Dict[str, float]]:
        min_profile_cues = int(settings.SUBTITLE_VISUAL_TRACK_MIN_PROFILE_CUES)
        features = [
            feature
            for subtitle in subtitles
            if (feature := self._subtitle_visual_features(subtitle)) is not None
        ]
        if len(features) < min_profile_cues:
            return None

        raw_median_height = float(np.median([feature["height"] for feature in features]))
        if raw_median_height <= 1.0:
            return None

        core_features = [
            feature
            for feature in features
            if 0.68 <= feature["height"] / raw_median_height <= 1.45
        ]
        if len(core_features) < min_profile_cues:
            core_features = features

        heights = [feature["height"] for feature in core_features]
        widths = [feature["width"] for feature in core_features]
        center_xs = [feature["center_x"] for feature in core_features]
        center_ys = [feature["center_y"] for feature in core_features]
        bottom_ys = [feature["bottom_y"] for feature in core_features]

        return {
            "count": float(len(core_features)),
            "height": float(np.median(heights)),
            "width": float(np.median(widths)),
            "center_x": float(np.median(center_xs)),
            "center_y": float(np.median(center_ys)),
            "bottom_y": float(np.median(bottom_ys)),
        }

    def _is_visual_track_non_dialogue_subtitle(
        self,
        subtitle: Subtitle,
        profile: Dict[str, float],
    ) -> bool:
        feature = self._subtitle_visual_features(subtitle)
        if not feature:
            return False

        profile_height = max(1.0, float(profile.get("height") or 0.0))
        profile_width = max(1.0, float(profile.get("width") or 0.0))
        height_ratio = feature["height"] / profile_height
        lower_center = feature["center_y"] - float(profile.get("center_y") or feature["center_y"]) >= profile_height * 0.14
        wider_than_track = feature["width"] >= profile_width * 1.45

        normalized_text = self._normalize_subtitle_candidate_text(subtitle.text or "")
        text_len = len(normalized_text)
        if text_len == 0:
            return False

        metrics = self._collect_selected_candidate_metrics(subtitle)
        frame_width_ratio = float(metrics.get("frame_width_ratio") or 0.0)
        local_width_ratio = float(metrics.get("width_ratio") or 0.0)
        edge_attachment = float(metrics.get("edge_attachment") or 0.0)
        style_match = float(metrics.get("style_match") or 0.0)
        temporal_support = float(metrics.get("temporal_support") or 0.0)
        line_count = float(metrics.get("line_count") or 0.0)
        component_count = float(metrics.get("component_count") or 0.0)

        credit_score, credit_breakdown = self._compute_credit_text_score(subtitle.text)
        credit_like = credit_score >= 0.38 or any(
            key in credit_breakdown
            for key in ("credit_role_term", "organization_suffix", "short_name_list", "latin_label_repeat")
        )
        sentence_like = self._compute_sentence_like_score(subtitle.text)
        duration = max(0.0, float(subtitle.end_time) - float(subtitle.start_time))

        small_height = height_ratio <= float(settings.SUBTITLE_VISUAL_TRACK_SMALL_HEIGHT_RATIO)
        strong_small_height = height_ratio <= float(settings.SUBTITLE_VISUAL_TRACK_STRONG_SMALL_HEIGHT_RATIO)
        long_text = text_len >= int(settings.SUBTITLE_NON_DIALOGUE_LONG_LINE_MIN_CHARS)
        medium_text = text_len >= 8
        wide_line = frame_width_ratio >= 0.34 or local_width_ratio >= 0.55 or wider_than_track
        edge_attached = edge_attachment >= 0.34
        multi_component = line_count >= 2 or component_count >= 3
        weak_style = 0.0 < style_match <= 0.55
        weak_temporal = temporal_support <= 0.55
        dialogue_like = sentence_like >= 0.48 and not credit_like and not edge_attached and not weak_style

        if text_len <= 4 and not credit_like:
            return False
        if not (small_height or strong_small_height):
            return False

        if strong_small_height and credit_like and text_len >= 4:
            return True

        if strong_small_height and medium_text and (wide_line or edge_attached or multi_component) and not dialogue_like:
            return True

        if small_height and long_text and wide_line and (edge_attached or multi_component or lower_center or weak_style):
            return not dialogue_like

        if small_height and long_text and edge_attached and (weak_style or weak_temporal or lower_center):
            return not dialogue_like

        if small_height and medium_text and credit_like and (lower_center or weak_temporal or duration <= 1.2):
            return True

        return False

    def _filter_visual_track_non_dialogue_subtitles(
        self,
        subtitles: List[Subtitle],
    ) -> List[Subtitle]:
        if not bool(settings.SUBTITLE_VISUAL_TRACK_FILTER_ENABLED):
            return subtitles
        if len(subtitles) < int(settings.SUBTITLE_VISUAL_TRACK_MIN_PROFILE_CUES):
            return subtitles

        profile = self._build_main_visual_track_profile(subtitles)
        if not profile:
            return subtitles

        filtered: List[Subtitle] = []
        dropped = 0
        for subtitle in subtitles:
            if self._is_visual_track_non_dialogue_subtitle(subtitle, profile):
                dropped += 1
                continue
            filtered.append(subtitle)

        if not dropped:
            return subtitles

        logger.info(
            "subtitle visual-track non-dialogue filter dropped=%s kept=%s profile_height=%.2f profile_center_y=%.2f",
            dropped,
            len(filtered),
            float(profile.get("height") or 0.0),
            float(profile.get("center_y") or 0.0),
        )
        for index, subtitle in enumerate(filtered, start=1):
            subtitle.index = index
        return filtered

    def _filter_variety_recall_overlay_subtitles(
        self,
        subtitles: List[Subtitle],
    ) -> List[Subtitle]:
        if not self.variety_recall_enabled or not subtitles:
            return subtitles

        filtered: List[Subtitle] = []
        dropped = 0
        for subtitle in subtitles:
            text = subtitle.text or ""
            box = subtitle.box
            right_side = False
            if box:
                x1, _, x2, _ = [float(v) for v in box]
                center_x = (x1 + x2) / 2
                right_side = x1 >= 1420 or center_x >= 1570
            if self._is_variety_right_overlay_text(text) or (right_side and not _has_cjk_text(text)):
                dropped += 1
                continue
            filtered.append(subtitle)

        if dropped:
            logger.info(
                "subtitle variety recall overlay filter dropped=%s kept=%s",
                dropped,
                len(filtered),
            )
        return filtered

    def _filter_main_temporal_window(
        self,
        subtitles: List[Subtitle],
        video_duration: Optional[float] = None,
    ) -> List[Subtitle]:
        if not bool(settings.SUBTITLE_MAIN_WINDOW_FILTER_ENABLED):
            return subtitles
        if len(subtitles) < int(settings.SUBTITLE_MAIN_WINDOW_MIN_TOTAL_CUES):
            return subtitles

        ordered = sorted(subtitles, key=lambda item: (item.start_time, item.end_time))
        first_start = float(ordered[0].start_time)
        last_end = float(ordered[-1].end_time)
        subtitle_span = max(0.0, last_end - first_start)
        program_duration = max(float(video_duration or 0.0), last_end)
        if subtitle_span < 300.0 and program_duration < 600.0:
            return subtitles

        start_index = self._detect_main_temporal_start_index(ordered)
        end_index = self._detect_main_temporal_end_index(
            ordered,
            start_index=start_index,
            program_duration=program_duration,
        )
        if start_index == 0 and end_index == len(ordered):
            return subtitles
        if start_index >= end_index:
            return subtitles

        filtered = ordered[start_index:end_index]
        logger.info(
            "subtitle main temporal-window filter start_index=%s end_index=%s dropped_head=%s dropped_tail=%s kept=%s",
            start_index,
            end_index,
            start_index,
            len(ordered) - end_index,
            len(filtered),
        )
        for index, subtitle in enumerate(filtered, start=1):
            subtitle.index = index
        return filtered

    def _detect_main_temporal_start_index(self, subtitles: List[Subtitle]) -> int:
        if len(subtitles) < int(settings.SUBTITLE_MAIN_WINDOW_MIN_TOTAL_CUES):
            return 0

        cluster_seconds = float(settings.SUBTITLE_MAIN_WINDOW_LEADING_CLUSTER_SECONDS)
        min_cluster_cues = int(settings.SUBTITLE_MAIN_WINDOW_LEADING_MIN_CLUSTER_CUES)
        boundary_gap = float(settings.SUBTITLE_MAIN_WINDOW_BOUNDARY_GAP_SECONDS)
        total_count = len(subtitles)
        first_start = float(subtitles[0].start_time)
        last_end = float(subtitles[-1].end_time)
        total_span = max(1.0, last_end - first_start)
        max_scan_count = min(total_count, max(40, int(total_count * 0.12)))

        window_end = 0
        for index in range(max_scan_count):
            start_time = float(subtitles[index].start_time)
            while (
                window_end < total_count
                and float(subtitles[window_end].start_time) - start_time <= cluster_seconds
            ):
                window_end += 1
            cluster_count = window_end - index
            if cluster_count < min_cluster_cues:
                continue
            if index == 0:
                return 0

            gap = float(subtitles[index].start_time) - float(subtitles[index - 1].end_time)
            prefix_duration = max(0.0, float(subtitles[index - 1].end_time) - first_start)
            prefix_count_limit = max(20, int(total_count * 0.08))
            prefix_duration_limit = max(180.0, total_span * 0.12)
            if (
                gap >= boundary_gap
                and index <= prefix_count_limit
                and prefix_duration <= prefix_duration_limit
            ):
                return index
            return 0

        return 0

    def _detect_main_temporal_end_index(
        self,
        subtitles: List[Subtitle],
        start_index: int,
        program_duration: float,
    ) -> int:
        total_count = len(subtitles)
        if total_count - start_index < int(settings.SUBTITLE_MAIN_WINDOW_MIN_TOTAL_CUES):
            return total_count

        boundary_gap = float(settings.SUBTITLE_MAIN_WINDOW_BOUNDARY_GAP_SECONDS)
        tail_start_ratio = float(settings.SUBTITLE_MAIN_WINDOW_TAIL_START_RATIO)
        max_suffix_cue_ratio = float(settings.SUBTITLE_MAIN_WINDOW_TAIL_MAX_SUFFIX_CUE_RATIO)
        max_suffix_duration_ratio = float(settings.SUBTITLE_MAIN_WINDOW_TAIL_MAX_SUFFIX_DURATION_RATIO)
        max_suffix_seconds = float(settings.SUBTITLE_MAIN_WINDOW_TAIL_MAX_SUFFIX_SECONDS)

        first_start = float(subtitles[start_index].start_time)
        last_end = float(subtitles[-1].end_time)
        effective_end = max(program_duration, last_end)
        tail_zone_start = max(
            first_start + max(0.0, last_end - first_start) * tail_start_ratio,
            effective_end * tail_start_ratio,
        )

        cut_index: Optional[int] = None
        for index in range(start_index + 1, total_count):
            suffix_start = float(subtitles[index].start_time)
            gap = suffix_start - float(subtitles[index - 1].end_time)
            if gap < boundary_gap:
                continue
            if suffix_start < tail_zone_start:
                continue

            prefix_count = index - start_index
            suffix_count = total_count - index
            if prefix_count < max(30, int(total_count * 0.55)):
                continue

            prefix_duration = max(1.0, float(subtitles[index - 1].end_time) - first_start)
            suffix_duration = max(0.0, last_end - suffix_start)
            suffix_cue_ratio = suffix_count / max(1.0, float(prefix_count))
            suffix_duration_ratio = suffix_duration / prefix_duration
            suffix_small_by_count = suffix_cue_ratio <= max_suffix_cue_ratio
            suffix_small_by_duration = (
                suffix_duration <= max_suffix_seconds
                or suffix_duration_ratio <= max_suffix_duration_ratio
            )
            if suffix_small_by_count and suffix_small_by_duration:
                cut_index = index

        return cut_index if cut_index is not None else total_count

    def _filter_subtitles_to_time_window(
        self,
        subtitles: List[Subtitle],
        start_time: float,
        end_time: float,
    ) -> List[Subtitle]:
        if not subtitles:
            return subtitles

        start_time = self._normalize_skip_seconds(start_time)
        end_time = max(start_time, float(end_time or 0.0))
        filtered: List[Subtitle] = []
        dropped = 0
        clipped = 0

        for subtitle in subtitles:
            if subtitle.end_time <= start_time or subtitle.start_time >= end_time:
                dropped += 1
                continue

            original_start = subtitle.start_time
            original_end = subtitle.end_time
            subtitle.start_time = max(subtitle.start_time, start_time)
            subtitle.end_time = min(subtitle.end_time, end_time)
            if subtitle.end_time <= subtitle.start_time:
                dropped += 1
                continue
            if subtitle.start_time != original_start or subtitle.end_time != original_end:
                clipped += 1
            filtered.append(subtitle)

        for index, subtitle in enumerate(filtered, start=1):
            subtitle.index = index

        if dropped or clipped:
            logger.info(
                "subtitle time-window filter start=%s end=%s dropped=%s clipped=%s kept=%s",
                round(float(start_time), 3),
                round(float(end_time), 3),
                dropped,
                clipped,
                len(filtered),
            )
        return filtered

    def _compute_sentence_like_score(self, text: str) -> float:
        joined = re.sub(r"\s+", "", (text or "").strip())
        if not joined:
            return 0.0

        punctuation_score = 0.35 if any(ch in joined for ch in "，。？！；：、") else 0.0
        dialogue_marker_score = 0.15 if any(ch in joined for ch in "我你他她它您咱吗呢啊呀吧") else 0.0
        function_chars = "的了是在有和就都又将与及而也把被给让着过来去要会可还才从向于因所以若则并且由后中成"
        function_char_count = sum(joined.count(ch) for ch in function_chars)
        function_char_score = min(1.0, function_char_count / max(1.0, len(joined) * 0.18))

        return max(
            0.0,
            min(
                1.0,
                float(
                    0.50 * function_char_score
                    + punctuation_score
                    + dialogue_marker_score
                ),
            ),
        )

    def _analyze_credit_like_subtitle(self, subtitle: Subtitle) -> Dict[str, Any]:
        score, breakdown = self._compute_credit_text_score(subtitle.text)
        strong_markers = {
            "credit_role_term",
            "organization_suffix",
            "short_name_list",
            "latin_label_repeat",
        }
        return {
            "score": float(score),
            "breakdown": breakdown,
            "sentence_like_score": self._compute_sentence_like_score(subtitle.text),
            "is_credit_like": score >= 0.38 or any(marker in breakdown for marker in strong_markers),
            "is_strong_credit_like": score >= 0.48 or any(
                marker in breakdown for marker in ("credit_role_term", "organization_suffix", "short_name_list")
            ),
        }

    def _filter_tail_non_dialogue_sequences(
        self,
        subtitles: List[Subtitle],
    ) -> List[Subtitle]:
        if len(subtitles) < 2:
            return subtitles

        def _subtitle_box_features(subtitle: Subtitle) -> Optional[Dict[str, float]]:
            if not subtitle.box:
                return None
            x1, y1, x2, y2 = [float(v) for v in subtitle.box]
            width = max(1.0, x2 - x1)
            height = max(1.0, y2 - y1)
            return {
                "center_x": (x1 + x2) / 2.0,
                "bottom_y": y2,
                "height": height,
                "width": width,
            }

        def _mad(values: List[float], center: float) -> float:
            if not values:
                return 0.0
            return float(np.median([abs(value - center) for value in values]))

        def _build_visual_style_profile(group: List[Subtitle]) -> Optional[Dict[str, float]]:
            features = [
                feature
                for subtitle in group
                if (feature := _subtitle_box_features(subtitle)) is not None
            ]
            if len(features) < 8:
                return None

            heights = [feature["height"] for feature in features]
            bottom_ys = [feature["bottom_y"] for feature in features]
            center_xs = [feature["center_x"] for feature in features]
            widths = [feature["width"] for feature in features]
            median_height = float(np.median(heights))
            median_bottom_y = float(np.median(bottom_ys))
            median_center_x = float(np.median(center_xs))
            median_width = float(np.median(widths))
            return {
                "count": float(len(features)),
                "height": median_height,
                "bottom_y": median_bottom_y,
                "center_x": median_center_x,
                "width": median_width,
                "height_tolerance": max(8.0, median_height * 0.55, _mad(heights, median_height) * 3.0),
                "bottom_tolerance": max(18.0, median_height * 1.20, _mad(bottom_ys, median_bottom_y) * 3.0),
                "center_tolerance": max(80.0, median_height * 5.0, _mad(center_xs, median_center_x) * 3.0),
            }

        def _visual_style_outlier_score(subtitle: Subtitle, profile: Optional[Dict[str, float]]) -> float:
            if not profile:
                return 0.0
            feature = _subtitle_box_features(subtitle)
            if feature is None:
                return 0.0

            height_delta = abs(feature["height"] - profile["height"]) / max(1.0, profile["height_tolerance"])
            bottom_delta = abs(feature["bottom_y"] - profile["bottom_y"]) / max(1.0, profile["bottom_tolerance"])
            center_delta = abs(feature["center_x"] - profile["center_x"]) / max(1.0, profile["center_tolerance"])

            return max(
                0.0,
                min(
                    1.0,
                    float(
                        0.42 * min(1.0, height_delta)
                        + 0.36 * min(1.0, bottom_delta)
                        + 0.22 * min(1.0, center_delta)
                    ),
                ),
            )

        def _visual_font_size_outlier(subtitle: Subtitle, profile: Optional[Dict[str, float]]) -> bool:
            if not profile:
                return False
            feature = _subtitle_box_features(subtitle)
            if feature is None:
                return False

            profile_height = max(1.0, float(profile["height"]))
            height = max(1.0, float(feature["height"]))
            height_ratio = height / profile_height
            height_delta = abs(height - profile_height)
            tolerance = max(12.0, profile_height * 0.28, float(profile.get("height_tolerance") or 0.0) * 0.35)
            return height_ratio <= 0.72 or height_ratio >= 1.38 or height_delta >= tolerance

        def _sequence_stats(group: List[Subtitle]) -> Dict[str, float]:
            group_size = max(1, len(group))
            sentence_scores = [self._compute_sentence_like_score(subtitle.text) for subtitle in group]
            normalized_lengths = [
                len(self._normalize_subtitle_candidate_text(subtitle.text or ""))
                for subtitle in group
            ]
            metrics = [self._collect_selected_candidate_metrics(subtitle) for subtitle in group]
            structural_hits = 0
            for item in metrics:
                has_debug_samples = int(item.get("sample_count") or 0) > 0
                if has_debug_samples and (
                    float(item.get("dense_text_scene_score") or 0.0) >= 0.07
                    or float(item.get("line_count") or 0.0) >= 3
                    or float(item.get("component_count") or 0.0) >= 5
                    or float(item.get("style_match") or 0.0) < 0.45
                    or float(item.get("edge_attachment") or 0.0) >= 0.85
                ):
                    structural_hits += 1
            return {
                "low_sentence_ratio": sum(
                    1 for score in sentence_scores
                    if score <= float(settings.SUBTITLE_NON_DIALOGUE_SENTENCE_SCORE_MAX)
                ) / group_size,
                "short_text_ratio": sum(1 for length in normalized_lengths if length <= 8) / group_size,
                "avg_length": sum(normalized_lengths) / group_size,
                "avg_duration": sum(max(0.0, subtitle.end_time - subtitle.start_time) for subtitle in group) / group_size,
                "very_short_duration_ratio": sum(
                    1
                    for subtitle in group
                    if max(0.0, subtitle.end_time - subtitle.start_time) <= 0.65
                ) / group_size,
                "structural_ratio": structural_hits / group_size,
            }

        min_group_size = int(settings.SUBTITLE_TAIL_NON_DIALOGUE_MIN_GROUP_SIZE)
        overall = _sequence_stats(subtitles)
        if (
            len(subtitles) >= min_group_size
            and overall["low_sentence_ratio"] >= 0.78
            and overall["short_text_ratio"] >= 0.45
            and overall["avg_length"] <= 10.0
            and overall["avg_duration"] <= 1.6
            and overall["structural_ratio"] >= 0.45
        ):
            logger.info(
                "subtitle tail non-dialogue whole-sequence filter dropped=%s kept=0",
                len(subtitles),
            )
            return []

        drop_indices = set()
        group_start = 0
        max_gap_seconds = 2.5
        last_end_time = max(1e-6, float(subtitles[-1].end_time))

        while group_start < len(subtitles):
            group_end = group_start + 1
            while (
                group_end < len(subtitles)
                and subtitles[group_end].start_time - subtitles[group_end - 1].end_time <= max_gap_seconds
            ):
                group_end += 1

            group = subtitles[group_start:group_end]
            group_size = len(group)
            tail_threshold = last_end_time * float(settings.SUBTITLE_TAIL_NON_DIALOGUE_START_RATIO)
            near_tail = group[0].start_time >= tail_threshold or group[-1].end_time >= tail_threshold
            if near_tail and group_size >= int(settings.SUBTITLE_TAIL_NON_DIALOGUE_MIN_GROUP_SIZE):
                stats = _sequence_stats(group)

                if (
                    stats["low_sentence_ratio"] >= 0.78
                    and stats["short_text_ratio"] >= 0.50
                    and stats["avg_length"] <= 9.0
                    and stats["avg_duration"] <= 1.6
                ):
                    drop_indices.update(range(group_start, group_end))

            group_start = group_end

        sparse_tail_start_ratio = float(settings.SUBTITLE_TAIL_SPARSE_SEQUENCE_START_RATIO)
        sparse_tail_min_gap = float(settings.SUBTITLE_TAIL_SPARSE_SEQUENCE_MIN_GAP_SECONDS)
        sparse_tail_min_size = int(settings.SUBTITLE_TAIL_SPARSE_SEQUENCE_MIN_GROUP_SIZE)
        for idx in range(1, len(subtitles)):
            gap_seconds = subtitles[idx].start_time - subtitles[idx - 1].end_time
            if gap_seconds < sparse_tail_min_gap:
                continue
            if subtitles[idx].start_time < last_end_time * sparse_tail_start_ratio:
                continue

            suffix = subtitles[idx:]
            first_duration = max(0.0, suffix[0].end_time - suffix[0].start_time)
            first_sentence_scores = [
                self._compute_sentence_like_score(subtitle.text)
                for subtitle in suffix[: min(2, len(suffix))]
            ]
            first_looks_dialogue_like = first_duration > 0.75 or max(first_sentence_scores or [0.0]) > 0.30

            stats = _sequence_stats(suffix)
            visual_profile = _build_visual_style_profile(subtitles[:idx])
            visual_outlier_scores = [
                _visual_style_outlier_score(subtitle, visual_profile)
                for subtitle in suffix
            ]
            visual_font_size_outlier_ratio = (
                sum(1 for subtitle in suffix if _visual_font_size_outlier(subtitle, visual_profile))
                / max(1, len(suffix))
            )
            visual_outlier_ratio = (
                sum(1 for score in visual_outlier_scores if score >= 0.58)
                / max(1, len(visual_outlier_scores))
            )
            long_sparse_suffix = (
                len(suffix) >= sparse_tail_min_size
                and stats["low_sentence_ratio"] >= 0.78
                and stats["short_text_ratio"] >= 0.55
                and stats["very_short_duration_ratio"] >= 0.70
                and stats["avg_length"] <= 10.0
                and stats["avg_duration"] <= 0.85
            )
            visual_track_break_suffix = (
                (visual_outlier_ratio >= 0.67 or visual_font_size_outlier_ratio >= 0.67)
                and stats["very_short_duration_ratio"] >= 0.67
                and stats["avg_duration"] <= 0.85
            )
            if first_looks_dialogue_like and not visual_track_break_suffix:
                continue

            short_noisy_suffix = (
                2 <= len(suffix) < sparse_tail_min_size
                and stats["very_short_duration_ratio"] >= 0.67
                and stats["avg_duration"] <= 0.75
                and (
                    visual_outlier_ratio >= 0.67
                    or visual_font_size_outlier_ratio >= 0.67
                    or (
                        stats["structural_ratio"] >= 0.67
                        and stats["low_sentence_ratio"] >= 0.67
                    )
                )
            )
            if long_sparse_suffix or visual_track_break_suffix or short_noisy_suffix:
                drop_indices.update(range(idx, len(subtitles)))
                break

        if not drop_indices:
            return subtitles

        filtered = [
            subtitle
            for idx, subtitle in enumerate(subtitles)
            if idx not in drop_indices
        ]
        logger.info(
            "subtitle tail non-dialogue sequence filter dropped=%s kept=%s",
            len(drop_indices),
            len(filtered),
        )
        for index, subtitle in enumerate(filtered, start=1):
            subtitle.index = index
        return filtered

    def _filter_credit_roll_sequences(
        self,
        subtitles: List[Subtitle],
    ) -> List[Subtitle]:
        if len(subtitles) < 4:
            return subtitles

        analyses = [self._analyze_credit_like_subtitle(subtitle) for subtitle in subtitles]
        drop_indices = set()
        group_start = 0
        max_gap_seconds = 2.5
        last_end_time = max(1e-6, float(subtitles[-1].end_time))

        while group_start < len(subtitles):
            group_end = group_start + 1
            while (
                group_end < len(subtitles)
                and subtitles[group_end].start_time - subtitles[group_end - 1].end_time <= max_gap_seconds
            ):
                group_end += 1

            group_analyses = analyses[group_start:group_end]
            credit_like_count = sum(1 for item in group_analyses if item["is_credit_like"])
            strong_credit_like_count = sum(1 for item in group_analyses if item["is_strong_credit_like"])
            low_sentence_like_count = sum(1 for item in group_analyses if item["sentence_like_score"] < 0.2)
            narrative_like_count = sum(1 for item in group_analyses if item["sentence_like_score"] >= 0.2)
            group_size = max(1, len(group_analyses))
            credit_like_ratio = credit_like_count / group_size
            low_sentence_like_ratio = low_sentence_like_count / group_size
            narrative_like_ratio = narrative_like_count / group_size
            if group_analyses:
                avg_credit_score = sum(item["score"] for item in group_analyses) / len(group_analyses)
            else:
                avg_credit_score = 0.0
            near_tail = subtitles[group_start].start_time >= last_end_time * 0.88
            broad_credit_evidence = (
                credit_like_count >= 2
                and (
                    credit_like_ratio >= 0.45
                    or strong_credit_like_count >= 2
                    or avg_credit_score >= 0.45
                )
            )
            mostly_non_sentence = low_sentence_like_ratio >= 0.70 and narrative_like_ratio <= 0.30

            if (
                len(group_analyses) >= 4
                and broad_credit_evidence
                and (
                    credit_like_ratio >= 0.55
                    or mostly_non_sentence
                    or strong_credit_like_count >= 3
                )
            ) or (
                len(group_analyses) >= 6
                and broad_credit_evidence
                and mostly_non_sentence
            ) or (
                near_tail
                and credit_like_count >= 2
                and mostly_non_sentence
                and (strong_credit_like_count >= 1 or avg_credit_score >= 0.35)
            ):
                drop_indices.update(range(group_start, group_end))

            group_start = group_end

        if not drop_indices:
            return subtitles

        filtered = [
            subtitle
            for idx, subtitle in enumerate(subtitles)
            if idx not in drop_indices
        ]
        logger.info(
            "subtitle credit-roll sequence filter dropped=%s kept=%s",
            len(drop_indices),
            len(filtered),
        )
        return filtered

    def _create_tracker_state(self) -> Dict[str, Any]:
        return {
            "stable_box": None,
            "history": [],
            "last_region_signature": None,
            "last_detection": None,
            "reuse_streak": 0,
            "last_subtitle_meta": None,
            "pending_candidate": None,
            "overlay_tracks": [],
            "subtitle_style": None,
            "last_success_timestamp": None,
            "consecutive_misses": 0,
            "transient_reset_done": False,
            "empty_region_signature": None,
            "empty_skip_streak": 0,
        }

    def _reset_tracker_transient_state(
        self,
        tracker_state: Dict[str, Any],
        signature: Optional[np.ndarray] = None,
        clear_pending: bool = True,
    ) -> None:
        tracker_state["last_region_signature"] = signature
        tracker_state["last_detection"] = None
        tracker_state["reuse_streak"] = 0
        tracker_state["last_subtitle_meta"] = None
        if clear_pending:
            tracker_state["pending_candidate"] = None

    def _reset_tracker_context(
        self,
        tracker_state: Dict[str, Any],
        signature: Optional[np.ndarray] = None,
    ) -> None:
        self._reset_tracker_transient_state(tracker_state, signature=signature, clear_pending=True)
        tracker_state["stable_box"] = None
        tracker_state["history"] = []
        tracker_state["overlay_tracks"] = []
        tracker_state["subtitle_style"] = None
        tracker_state["empty_region_signature"] = None
        tracker_state["empty_skip_streak"] = 0

    def _register_tracker_success(
        self,
        tracker_state: Dict[str, Any],
        timestamp: Optional[float],
    ) -> None:
        tracker_state["last_success_timestamp"] = float(timestamp) if timestamp is not None else None
        tracker_state["consecutive_misses"] = 0
        tracker_state["transient_reset_done"] = False

    def _register_tracker_miss(
        self,
        tracker_state: Dict[str, Any],
        timestamp: Optional[float],
        signature: Optional[np.ndarray] = None,
        clear_pending: bool = True,
    ) -> None:
        tracker_state["consecutive_misses"] = int(tracker_state.get("consecutive_misses", 0)) + 1
        last_success_timestamp = tracker_state.get("last_success_timestamp")
        no_success_gap = None
        if timestamp is not None and last_success_timestamp is not None:
            no_success_gap = max(0.0, float(timestamp) - float(last_success_timestamp))

        needs_hard_reset = (
            tracker_state["consecutive_misses"] >= settings.SUBTITLE_TRACKER_CONTEXT_RESET_MISSES
            or (
                no_success_gap is not None
                and no_success_gap >= settings.SUBTITLE_TRACKER_CONTEXT_RESET_GAP_SECONDS
            )
        )
        if needs_hard_reset:
            self._reset_tracker_context(tracker_state, signature=signature)
            tracker_state["last_success_timestamp"] = None
            tracker_state["consecutive_misses"] = 0
            tracker_state["transient_reset_done"] = False
            return

        if (
            tracker_state["consecutive_misses"] >= settings.SUBTITLE_TRACKER_TRANSIENT_RESET_MISSES
            and (
                no_success_gap is None
                or no_success_gap >= settings.SUBTITLE_TRACKER_TRANSIENT_RESET_GAP_SECONDS
            )
            and not tracker_state.get("transient_reset_done", False)
        ):
            self._reset_tracker_transient_state(
                tracker_state,
                signature=signature,
                clear_pending=True,
            )
            tracker_state["transient_reset_done"] = True
            return

        self._clear_tracker_reuse_candidate(
            tracker_state,
            signature=signature,
            clear_pending=clear_pending,
        )

    def _should_skip_secondary_recognition(
        self,
        localized: Dict[str, Any],
        search_region: Tuple[int, int, int, int],
    ) -> bool:
        """Decide if the tight-region second OCR pass adds nothing.

        The second pass exists to recover text that the coarse pass clipped at
        the search-region border or fragmented. When the coarse pass already
        produced a single confident line whose box sits well inside the search
        region, re-running OCR on the padded tight box returns the same text;
        skipping it halves the per-frame OCR cost on stable dialogue scenes.
        """
        if not settings.SUBTITLE_SECONDARY_RECOGNITION_SKIP_ENABLED:
            return False
        if self.variety_recall_enabled:
            return False

        debug = localized.get("debug") or {}
        selected_indices = debug.get("selected_line_indices") or []
        if len(selected_indices) != 1:
            return False
        selected = localized.get("selected_detections") or []
        if not selected:
            return False
        min_confidence = float(settings.SUBTITLE_SECONDARY_RECOGNITION_SKIP_MIN_CONFIDENCE)
        if any(float(det.get("confidence") or 0.0) < min_confidence for det in selected):
            return False

        tight_box = debug.get("tight_box")
        if not tight_box or len(tight_box) != 4:
            return False
        sx1, sy1, sx2, sy2 = [int(v) for v in search_region]
        tx1, ty1, tx2, ty2 = [int(v) for v in tight_box]
        height = max(1, ty2 - ty1)
        # Border contact means the coarse crop may have clipped glyphs - re-read.
        margin = max(4, int(height * 0.25))
        if tx1 - sx1 < margin or sx2 - tx2 < margin:
            return False
        if ty1 - sy1 < margin or sy2 - ty2 < margin:
            return False
        return True

    def _arm_empty_region_skip(
        self,
        tracker_state: Dict[str, Any],
        signature: Optional[np.ndarray],
    ) -> None:
        if not settings.SUBTITLE_EMPTY_REGION_SKIP_ENABLED or signature is None:
            return
        tracker_state["empty_region_signature"] = signature
        tracker_state["empty_skip_streak"] = 0

    def _maybe_skip_confirmed_empty_region(
        self,
        tracker_state: Dict[str, Any],
        signature: Optional[np.ndarray],
    ) -> bool:
        """Skip OCR while the region stays identical to a confirmed-empty frame.

        Mirrors the positive-reuse path: once OCR confirmed a region has no
        text, near-identical follow-up frames (static scenes between dialogue
        lines) cannot have gained text. Re-verified every MAX_CONSECUTIVE
        frames so a slow fade-in is caught at most a few samples late.
        """
        if not settings.SUBTITLE_EMPTY_REGION_SKIP_ENABLED or signature is None:
            return False
        empty_signature = tracker_state.get("empty_region_signature")
        if empty_signature is None:
            return False
        streak = int(tracker_state.get("empty_skip_streak", 0))
        if streak >= int(settings.SUBTITLE_EMPTY_REGION_SKIP_MAX_CONSECUTIVE):
            tracker_state["empty_region_signature"] = None
            tracker_state["empty_skip_streak"] = 0
            return False
        mean_diff = float(np.mean(np.abs(signature - empty_signature)))
        if mean_diff > settings.SUBTITLE_FRAME_REUSE_MAX_MEAN_DIFF:
            tracker_state["empty_region_signature"] = None
            tracker_state["empty_skip_streak"] = 0
            return False
        tracker_state["empty_skip_streak"] = streak + 1
        return True

    def _compute_region_signature(self, region_view: np.ndarray) -> Optional[np.ndarray]:
        if region_view is None or region_view.size == 0:
            return None
        if len(region_view.shape) == 3:
            gray = cv2.cvtColor(region_view, cv2.COLOR_BGR2GRAY)
        else:
            gray = region_view
        signature = cv2.resize(gray, (96, 32), interpolation=cv2.INTER_AREA)
        signature = cv2.GaussianBlur(signature, (3, 3), 0)
        return signature.astype(np.float32) / 255.0

    def _build_reused_detection(
        self,
        tracker_state: Dict[str, Any],
        signature: Optional[np.ndarray],
        timestamp: float,
        frame_index: int,
    ) -> Optional[DetectedText]:
        if not settings.SUBTITLE_FRAME_REUSE_ENABLED:
            return None
        if signature is None:
            return None

        previous_signature = tracker_state.get("last_region_signature")
        previous_detection = tracker_state.get("last_detection")
        if previous_signature is None or previous_detection is None:
            return None
        if previous_detection.get("confidence", 0.0) < settings.SUBTITLE_FRAME_REUSE_MIN_CONFIDENCE:
            return None
        if self.variety_recall_enabled and tracker_state.get("reuse_streak", 0) >= 1:
            return None
        if tracker_state.get("reuse_streak", 0) >= settings.SUBTITLE_FRAME_REUSE_MAX_CONSECUTIVE:
            return None

        mean_diff = float(np.mean(np.abs(signature - previous_signature)))
        if self.variety_recall_enabled and mean_diff > 0.012:
            return None
        if mean_diff > settings.SUBTITLE_FRAME_REUSE_MAX_MEAN_DIFF:
            return None

        tracker_state["last_region_signature"] = signature
        tracker_state["reuse_streak"] = tracker_state.get("reuse_streak", 0) + 1

        reused_box = tracker_state.get("stable_box") or previous_detection.get("box")
        if reused_box is None:
            reused_box = previous_detection.get("box")

        return DetectedText(
            text=previous_detection["text"],
            confidence=float(previous_detection["confidence"]),
            box=reused_box,
            polygon=previous_detection.get("polygon"),
            rotated_box=previous_detection.get("rotated_box"),
            recognition_region=None,
            recognition_executed=False,
            timestamp=timestamp,
            frame_index=frame_index,
        )

    def _update_tracker_reuse_candidate(
        self,
        tracker_state: Dict[str, Any],
        detection: dict,
        signature: Optional[np.ndarray],
        timestamp: Optional[float] = None,
    ) -> None:
        tracker_state["last_region_signature"] = signature
        tracker_state["last_detection"] = {
            "text": detection.get("text", ""),
            "confidence": float(detection.get("confidence", 0.0)),
            "box": detection.get("box"),
            "polygon": detection.get("polygon"),
            "rotated_box": detection.get("rotated_box"),
            "recognition_region": detection.get("recognition_region"),
        }
        box = detection.get("box")
        if box is not None:
            tracker_state["last_subtitle_meta"] = self._build_subtitle_meta(box, detection.get("text", ""))
            self._update_subtitle_style_profile(tracker_state, box, timestamp=timestamp)
        tracker_state["pending_candidate"] = None
        tracker_state["reuse_streak"] = 0
        tracker_state["empty_region_signature"] = None
        tracker_state["empty_skip_streak"] = 0
        self._register_tracker_success(tracker_state, timestamp)

    def _clear_tracker_reuse_candidate(
        self,
        tracker_state: Dict[str, Any],
        signature: Optional[np.ndarray] = None,
        clear_pending: bool = True,
    ) -> None:
        tracker_state["last_region_signature"] = signature
        tracker_state["last_detection"] = None
        tracker_state["reuse_streak"] = 0
        if clear_pending:
            tracker_state["pending_candidate"] = None

    def _resolve_detection_region(
        self,
        anchor: SubtitleAnchor,
        frame: np.ndarray,
        tracker_state: Dict[str, Any]
    ) -> Tuple[int, int, int, int]:
        base = self._expand_dialogue_search_region(
            self.detector.refine_anchor(anchor, frame),
            anchor,
            frame.shape,
        )
        stable = tracker_state.get("stable_box")
        if stable is None:
            return base

        sh = max(1, stable[3] - stable[1])
        sw = max(1, stable[2] - stable[0])
        pad_x = max(30, int(sw * 0.45))
        pad_y = max(20, int(sh * 0.9))
        adaptive = (
            stable[0] - pad_x,
            stable[1] - pad_y,
            stable[2] + pad_x,
            stable[3] + pad_y
        )
        combined = (
            min(base[0], adaptive[0]),
            min(base[1], adaptive[1]),
            max(base[2], adaptive[2]),
            max(base[3], adaptive[3])
        )
        return self._expand_dialogue_search_region(
            self._clamp_box(combined, frame.shape),
            anchor,
            frame.shape,
        )

    def _expand_dialogue_search_region(
        self,
        box: Tuple[int, int, int, int],
        anchor: SubtitleAnchor,
        frame_shape: Tuple[int, ...],
    ) -> Tuple[int, int, int, int]:
        if self.manual_region_active:
            return self._clamp_box(box, frame_shape)

        position_mode = (anchor.position_mode or "bottom").lower()
        if position_mode not in {"bottom", "middle", "top"}:
            return self._clamp_box(box, frame_shape)

        frame_height, frame_width = frame_shape[:2]
        x1, y1, x2, y2 = [float(v) for v in box]
        current_width = max(1.0, x2 - x1)
        current_height = max(1.0, y2 - y1)
        min_width = frame_width * max(0.10, min(1.0, float(settings.SUBTITLE_DIALOGUE_SEARCH_MIN_WIDTH_RATIO)))
        min_height = frame_height * max(0.04, min(0.60, float(settings.SUBTITLE_DIALOGUE_SEARCH_MIN_HEIGHT_RATIO)))

        if current_width < min_width:
            center_x = frame_width * 0.5
            x1 = center_x - min_width / 2.0
            x2 = center_x + min_width / 2.0

        if current_height < min_height:
            if position_mode == "bottom":
                center_y = (y1 + y2) / 2.0
                expanded_y1 = center_y - min_height * 0.55
                expanded_y2 = expanded_y1 + min_height
                if expanded_y2 > frame_height:
                    expanded_y2 = float(frame_height)
                    expanded_y1 = expanded_y2 - min_height
                y1 = min(y1, expanded_y1)
                y2 = max(y2, expanded_y2)
            elif position_mode == "top":
                top = min(y1, frame_height * 0.02)
                y1 = top
                y2 = top + min_height
            else:
                center_y = (y1 + y2) / 2.0
                y1 = center_y - min_height / 2.0
                y2 = center_y + min_height / 2.0

        return self._clamp_box(
            (int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2))),
            frame_shape,
        )

    def _self_optimize_box(
        self,
        raw_box: Tuple[int, int, int, int],
        confidence: float,
        tracker_state: Dict[str, Any],
        frame_shape: Tuple[int, int, int]
    ) -> Tuple[int, int, int, int]:
        expanded = self._expand_box(raw_box, frame_shape)
        stable = tracker_state.get("stable_box")

        if stable is None:
            candidate = expanded
        else:
            iou = self._box_iou(expanded, stable)
            if iou >= settings.SUBTITLE_TRACKER_IOU_THRESHOLD:
                alpha = settings.SUBTITLE_TRACKER_HIGH_CONF_ALPHA if confidence >= settings.SUBTITLE_MIN_CONFIDENCE else settings.SUBTITLE_TRACKER_LOW_CONF_ALPHA
                candidate = tuple(
                    int(round(alpha * expanded[i] + (1.0 - alpha) * stable[i]))
                    for i in range(4)
                )
            elif confidence < settings.SUBTITLE_MIN_CONFIDENCE * 0.9:
                candidate = stable
            else:
                candidate = expanded

        candidate = self._clamp_box(candidate, frame_shape)
        history = tracker_state["history"]
        history.append(candidate)
        if len(history) > settings.SUBTITLE_TRACKER_HISTORY_SIZE:
            history.pop(0)
        tracker_state["stable_box"] = self._median_box(history)
        return tracker_state["stable_box"]

    def _expand_box(
        self,
        box: Tuple[int, int, int, int],
        frame_shape: Tuple[int, int, int]
    ) -> Tuple[int, int, int, int]:
        x1, y1, x2, y2 = box
        width = max(1, x2 - x1)
        height = max(1, y2 - y1)
        pad_x = max(settings.SUBTITLE_BOX_PAD_X_MIN, int(width * settings.SUBTITLE_BOX_PAD_X_RATIO))
        pad_top = max(settings.SUBTITLE_BOX_PAD_TOP_MIN, int(height * settings.SUBTITLE_BOX_PAD_TOP_RATIO))
        pad_bottom = max(settings.SUBTITLE_BOX_PAD_BOTTOM_MIN, int(height * settings.SUBTITLE_BOX_PAD_BOTTOM_RATIO))
        expanded = (x1 - pad_x, y1 - pad_top, x2 + pad_x, y2 + pad_bottom)
        return self._clamp_box(expanded, frame_shape)

    def _median_box(self, boxes: List[Tuple[int, int, int, int]]) -> Tuple[int, int, int, int]:
        arr = np.array(boxes, dtype=np.float64)
        med = np.median(arr, axis=0)
        return (
            int(round(med[0])),
            int(round(med[1])),
            int(round(med[2])),
            int(round(med[3]))
        )

    def _clamp_box(
        self,
        box: Tuple[int, int, int, int],
        frame_shape: Tuple[int, int, int]
    ) -> Tuple[int, int, int, int]:
        h, w = frame_shape[:2]
        x1, y1, x2, y2 = box
        x1 = int(max(0, min(w - 1, x1)))
        y1 = int(max(0, min(h - 1, y1)))
        x2 = int(max(x1 + 1, min(w, x2)))
        y2 = int(max(y1 + 1, min(h, y2)))
        return (x1, y1, x2, y2)

    def _box_iou(
        self,
        box_a: Tuple[int, int, int, int],
        box_b: Tuple[int, int, int, int]
    ) -> float:
        ax1, ay1, ax2, ay2 = box_a
        bx1, by1, bx2, by2 = box_b
        ix1 = max(ax1, bx1)
        iy1 = max(ay1, by1)
        ix2 = min(ax2, bx2)
        iy2 = min(ay2, by2)
        iw = max(0, ix2 - ix1)
        ih = max(0, iy2 - iy1)
        inter = float(iw * ih)
        if inter <= 0.0:
            return 0.0
        area_a = float(max(1, ax2 - ax1) * max(1, ay2 - ay1))
        area_b = float(max(1, bx2 - bx1) * max(1, by2 - by1))
        union = area_a + area_b - inter
        if union <= 0.0:
            return 0.0
        return inter / union
