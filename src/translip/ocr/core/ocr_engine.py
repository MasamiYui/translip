"""OCR Engine module - wraps PaddleOCR for text detection and recognition"""

import cv2
import numpy as np
from typing import Any, Dict, List, Optional, Tuple
import logging
import platform
import time
from importlib import metadata as importlib_metadata

from translip.ocr.config import settings
from translip.ocr.models.domain import TextDetection
from translip.ocr.utils.geometry import (
    normalize_polygon,
    polygon_to_box,
    polygon_to_rotated_box,
    shift_polygon,
    shift_rotated_box,
)
from translip.ocr.utils.model_paths import current_runtime_supported, current_runtime_tag, resolve_model_dir
from translip.ocr.utils.runtime_diagnostics import log_runtime_snapshot

logger = logging.getLogger(__name__)


class OCREngineRuntimeError(RuntimeError):
    """Raised when PaddleOCR fails during inference."""


class OCREngine:
    """
    OCR Engine - wraps PaddleOCR for text detection and recognition

    Supports multiple languages and provides both detection-only and
    full OCR capabilities.

    Note: GPU usage is determined by the installed PaddlePaddle version:
    - paddlepaddle: CPU only
    - paddlepaddle-gpu: GPU acceleration
    """

    _PPOCR_V5_MOBILE_REC_MODELS = {
        "ch": "PP-OCRv5_mobile_rec",
        "en": "en_PP-OCRv5_mobile_rec",
    }

    def __init__(
        self,
        lang: str = 'ch',
        use_angle_cls: bool = True,
        det_db_thresh: Optional[float] = None,
        det_db_box_thresh: Optional[float] = None,
    ):
        """
        Initialize OCR engine

        Args:
            lang: Language code ('ch', 'en', 'korean', 'japan', etc.)
            use_angle_cls: Whether to use angle classifier
            det_db_thresh: Override PaddleOCR DB detection threshold
            det_db_box_thresh: Override PaddleOCR DB box threshold
        """
        self.lang = lang
        self.use_angle_cls = use_angle_cls
        self.det_db_thresh = settings.PADDLEOCR_DET_DB_THRESH if det_db_thresh is None else float(det_db_thresh)
        self.det_db_box_thresh = settings.PADDLEOCR_DET_DB_BOX_THRESH if det_db_box_thresh is None else float(det_db_box_thresh)

        # Lazy initialization of OCR instances
        self._ocr_instances = {}
        self._runtime_profile: Optional[Dict[str, Any]] = None

        logger.info(
            "OCREngine initialized lang=%s use_angle_cls=%s det_db_thresh=%s det_db_box_thresh=%s",
            lang,
            int(use_angle_cls),
            self.det_db_thresh,
            self.det_db_box_thresh,
        )

    @staticmethod
    def _installed_dist_version(name: str) -> Optional[str]:
        try:
            return importlib_metadata.version(name)
        except importlib_metadata.PackageNotFoundError:
            return None

    @staticmethod
    def _major_version(version: Optional[str]) -> Optional[int]:
        if not version:
            return None
        try:
            return int(str(version).split(".", 1)[0])
        except ValueError:
            return None

    def _get_runtime_profile(self) -> Dict[str, Optional[str]]:
        if self._runtime_profile is None:
            paddle_version = self._installed_dist_version("paddlepaddle")
            paddleocr_version = self._installed_dist_version("paddleocr")
            paddlex_version = self._installed_dist_version("paddlex")
            self._runtime_profile = {
                "paddle_version": paddle_version,
                "paddleocr_version": paddleocr_version,
                "paddlex_version": paddlex_version,
                "paddle_major": self._major_version(paddle_version),
                "paddleocr_major": self._major_version(paddleocr_version),
                "paddlex_major": self._major_version(paddlex_version),
            }
        return self._runtime_profile

    def _is_v3_runtime(self) -> bool:
        profile = self._get_runtime_profile()
        return bool(profile.get("paddle_major") and int(profile["paddle_major"]) >= 3)

    def _validate_runtime_distribution_versions(self) -> None:
        profile = self._get_runtime_profile()
        paddle_version = profile["paddle_version"]
        paddleocr_version = profile["paddleocr_version"]
        paddlex_version = profile["paddlex_version"]
        paddle_major = profile["paddle_major"]
        paddleocr_major = profile["paddleocr_major"]
        paddlex_major = profile["paddlex_major"]

        if paddle_major is None or paddleocr_major is None:
            raise OCREngineRuntimeError(
                "Paddle runtime packages are incomplete. "
                f"paddlepaddle=={paddle_version or 'not-installed'}, "
                f"paddleocr=={paddleocr_version or 'not-installed'}, "
                f"paddlex=={paddlex_version or 'not-installed'}."
            )

        if paddle_major != paddleocr_major:
            raise OCREngineRuntimeError(
                "Incompatible OCR runtime packages installed: "
                f"paddlepaddle=={paddle_version}, paddleocr=={paddleocr_version}, paddlex=={paddlex_version or 'not-installed'}. "
                "Install a matching major-version stack."
            )

        if paddle_major >= 3 and (paddlex_major is None or paddlex_major < 3):
            raise OCREngineRuntimeError(
                "PaddleOCR 3.x requires paddlex 3.x at runtime. "
                f"Found paddlepaddle=={paddle_version}, paddleocr=={paddleocr_version}, paddlex=={paddlex_version or 'not-installed'}."
            )

        if paddle_major == 2 and platform.system() == "Darwin" and platform.machine() == "arm64":
            raise OCREngineRuntimeError(
                "paddlepaddle 2.x + paddleocr 2.x is pathologically slow on macOS arm64 in this project. "
                f"Found paddlepaddle=={paddle_version}, paddleocr=={paddleocr_version}. "
                "Use paddlepaddle==3.1.1, paddleocr==3.2.0, paddlex==3.2.0 with PP-OCRv5 mobile models."
            )

    def _resolve_v3_mobile_model_names(self, lang: str) -> Tuple[Optional[str], Optional[str]]:
        normalized = (lang or self.lang or "ch").lower()
        rec_model_name = self._PPOCR_V5_MOBILE_REC_MODELS.get(normalized)
        det_model_name = settings.PADDLEOCR_TEXT_DETECTION_MODEL_NAME or None
        if det_model_name and rec_model_name:
            return det_model_name, rec_model_name
        return None, None

    def _resolve_v3_local_model_dirs(self, lang: str) -> Dict[str, Optional[str]]:
        det_model_name, rec_model_name = self._resolve_v3_mobile_model_names(lang)
        dirs: Dict[str, Optional[str]] = {
            "text_detection_model_name": det_model_name,
            "text_detection_model_dir": None,
            "text_recognition_model_name": rec_model_name,
            "text_recognition_model_dir": None,
            "textline_orientation_model_name": None,
            "textline_orientation_model_dir": None,
        }
        if not det_model_name or not rec_model_name:
            return dirs

        det_dir = resolve_model_dir(
            det_model_name,
            base_dir=settings.PADDLEOCR_MODELS_BASE_DIR or None,
            layout=settings.PADDLEOCR_MODELS_LAYOUT,
            platform_tag=settings.PADDLEOCR_MODELS_PLATFORM_TAG,
        )
        rec_dir = resolve_model_dir(
            rec_model_name,
            base_dir=settings.PADDLEOCR_MODELS_BASE_DIR or None,
            layout=settings.PADDLEOCR_MODELS_LAYOUT,
            platform_tag=settings.PADDLEOCR_MODELS_PLATFORM_TAG,
        )
        if det_dir is not None:
            dirs["text_detection_model_dir"] = str(det_dir)
        if rec_dir is not None:
            dirs["text_recognition_model_dir"] = str(rec_dir)

        if self.use_angle_cls:
            cls_model_name = settings.PADDLEOCR_TEXTLINE_ORIENTATION_MODEL_NAME or None
            cls_dir = resolve_model_dir(
                cls_model_name,
                base_dir=settings.PADDLEOCR_MODELS_BASE_DIR or None,
                layout=settings.PADDLEOCR_MODELS_LAYOUT,
                platform_tag=settings.PADDLEOCR_MODELS_PLATFORM_TAG,
            ) if cls_model_name else None
            dirs["textline_orientation_model_name"] = cls_model_name
            if cls_dir is not None:
                dirs["textline_orientation_model_dir"] = str(cls_dir)
        return dirs

    @staticmethod
    def _poly_to_box(poly) -> Optional[Tuple[float, float, float, float]]:
        polygon = normalize_polygon(poly)
        return polygon_to_box(polygon)

    @staticmethod
    def _poly_to_polygon(poly) -> Optional[List[Tuple[float, float]]]:
        return normalize_polygon(poly)

    @staticmethod
    def _poly_to_rotated_box(poly) -> Optional[dict]:
        polygon = normalize_polygon(poly)
        return polygon_to_rotated_box(polygon)

    @staticmethod
    def _shift_detection_geometry(det: dict, dx: float, dy: float) -> None:
        box = det.get("box")
        if box:
            det["box"] = (
                int(round(box[0] + dx)),
                int(round(box[1] + dy)),
                int(round(box[2] + dx)),
                int(round(box[3] + dy)),
            )

        polygon = det.get("polygon")
        if polygon:
            det["polygon"] = shift_polygon(polygon, dx, dy)

        rotated_box = det.get("rotated_box")
        if rotated_box:
            det["rotated_box"] = shift_rotated_box(rotated_box, dx, dy)

    def _normalize_prediction_result(self, result) -> List[dict]:
        if not result:
            return []

        if isinstance(result, list) and result and isinstance(result[0], dict):
            return self._parse_v3_predictions(result)

        return self._parse_v2_predictions(result)

    def _parse_v3_predictions(self, result: List[dict]) -> List[dict]:
        if not result or not result[0]:
            return []

        res = result[0]
        rec_texts = res.get('rec_texts', [])
        rec_scores = res.get('rec_scores', [])
        rec_polys = res.get('rec_polys', [])

        detections = []
        for i, text in enumerate(rec_texts):
            if i >= len(rec_scores) or i >= len(rec_polys):
                break

            polygon = self._poly_to_polygon(rec_polys[i])
            box = self._poly_to_box(rec_polys[i])
            if not box:
                continue

            detections.append({
                'box': box,
                'polygon': polygon,
                'rotated_box': self._poly_to_rotated_box(rec_polys[i]),
                'text': text,
                'confidence': float(rec_scores[i]),
            })

        return detections

    def _parse_v2_predictions(self, result) -> List[dict]:
        detections = []
        self._collect_v2_detections(result, detections)
        return detections

    @staticmethod
    def _looks_like_v2_line(item) -> bool:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            return False
        if not isinstance(item[0], (list, tuple, np.ndarray)):
            return False
        return isinstance(item[1], (list, tuple)) and len(item[1]) >= 2

    def _collect_v2_detections(self, node, output: List[dict]) -> None:
        if self._looks_like_v2_line(node):
            parsed = self._parse_v2_line(node)
            if parsed:
                output.append(parsed)
            return

        if isinstance(node, (list, tuple)):
            for item in node:
                self._collect_v2_detections(item, output)

    def _parse_v2_line(self, line) -> Optional[dict]:
        if not isinstance(line, (list, tuple)) or len(line) < 2:
            return None

        polygon = self._poly_to_polygon(line[0])
        box = self._poly_to_box(line[0])
        if not box:
            return None

        rec = line[1]
        if not isinstance(rec, (list, tuple)) or len(rec) < 2:
            return None

        text = str(rec[0]).strip()
        if not text:
            return None

        try:
            confidence = float(rec[1])
        except (TypeError, ValueError):
            confidence = 0.0

        return {
            'box': box,
            'polygon': polygon,
            'rotated_box': self._poly_to_rotated_box(line[0]),
            'text': text,
            'confidence': confidence,
        }

    @staticmethod
    def _looks_like_recognition_only(node) -> bool:
        if not isinstance(node, (list, tuple)) or len(node) < 2:
            return False
        return isinstance(node[0], str)

    def _collect_recognition_only(self, node, output: List[dict]) -> None:
        if self._looks_like_recognition_only(node):
            text = str(node[0]).strip()
            if not text:
                return
            try:
                confidence = float(node[1])
            except (TypeError, ValueError):
                confidence = 0.0
            output.append({"text": text, "confidence": confidence})
            return

        if isinstance(node, (list, tuple)):
            for item in node:
                self._collect_recognition_only(item, output)

    def recognize_text_line(
        self,
        image: np.ndarray,
        lang: Optional[str] = None,
    ) -> Optional[dict]:
        """
        Recognize text from an already cropped subtitle patch.

        This is used for secondary recognition after choosing a geometry mode.
        """
        if image is None or image.size == 0:
            return None

        if self._is_v3_runtime():
            detections = self.detect_text(image, lang)
            if not detections:
                return None
            merged_text = " ".join(det["text"] for det in detections if det.get("text")).strip()
            if not merged_text:
                return None
            return {
                "text": merged_text,
                "confidence": float(np.mean([det["confidence"] for det in detections])),
            }

        ocr = self._get_ocr_instance(lang)
        try:
            result = ocr.ocr(image, det=False, rec=True, cls=self.use_angle_cls)
        except Exception as e:
            log_runtime_snapshot(logger, logging.ERROR, "OCR failed during cropped-line recognition lang=%s", lang or self.lang)
            logger.exception("OCR failed during cropped-line recognition")
            raise self._build_runtime_error(e) from e

        recognized: List[dict] = []
        self._collect_recognition_only(result, recognized)
        if not recognized:
            return None

        text = "\n".join(item["text"] for item in recognized if item["text"]).strip()
        if not text:
            return None
        confidence = float(np.mean([item["confidence"] for item in recognized]))
        return {"text": text, "confidence": confidence}

    def _get_ocr_instance(self, lang: Optional[str] = None) -> 'PaddleOCR':
        """
        Get or create OCR instance for specified language

        Args:
            lang: Language code (uses default if None)

        Returns:
            PaddleOCR instance
        """
        target_lang = lang or self.lang

        if target_lang not in self._ocr_instances:
            started_at = time.monotonic()
            enable_mkldnn = bool(settings.PADDLEOCR_ENABLE_MKLDNN)
            runtime_profile = self._get_runtime_profile()
            device = "gpu:0" if settings.PADDLEOCR_USE_GPU else settings.PADDLEOCR_DEVICE
            log_runtime_snapshot(
                logger,
                logging.INFO,
                "creating PaddleOCR instance lang=%s paddle=%s paddleocr=%s paddlex=%s device=%s mkldnn=%s cpu_threads=%s",
                target_lang,
                runtime_profile.get("paddle_version"),
                runtime_profile.get("paddleocr_version"),
                runtime_profile.get("paddlex_version") or "not-installed",
                device,
                int(enable_mkldnn),
                settings.PADDLEOCR_CPU_THREADS,
            )
            try:
                self._validate_runtime_distribution_versions()
                from paddleocr import PaddleOCR
                if self._is_v3_runtime():
                    ocr_kwargs = dict(
                        device=device,
                        enable_hpi=settings.PADDLEOCR_ENABLE_HPI,
                        enable_mkldnn=enable_mkldnn,
                        cpu_threads=settings.PADDLEOCR_CPU_THREADS,
                        use_doc_orientation_classify=False,
                        use_doc_unwarping=False,
                        use_textline_orientation=self.use_angle_cls,
                        text_det_thresh=self.det_db_thresh,
                        text_det_box_thresh=self.det_db_box_thresh,
                    )
                    local_model_cfg = self._resolve_v3_local_model_dirs(target_lang)
                    det_model_name = local_model_cfg["text_detection_model_name"]
                    rec_model_name = local_model_cfg["text_recognition_model_name"]
                    det_model_dir = local_model_cfg["text_detection_model_dir"]
                    rec_model_dir = local_model_cfg["text_recognition_model_dir"]
                    cls_model_name = local_model_cfg["textline_orientation_model_name"]
                    cls_model_dir = local_model_cfg["textline_orientation_model_dir"]
                    if det_model_name and rec_model_name:
                        ocr_kwargs["text_detection_model_name"] = det_model_name
                        ocr_kwargs["text_recognition_model_name"] = rec_model_name
                        if det_model_dir:
                            ocr_kwargs["text_detection_model_dir"] = det_model_dir
                        if rec_model_dir:
                            ocr_kwargs["text_recognition_model_dir"] = rec_model_dir
                        if self.use_angle_cls and cls_model_name and cls_model_dir:
                            ocr_kwargs["textline_orientation_model_name"] = cls_model_name
                            ocr_kwargs["textline_orientation_model_dir"] = cls_model_dir

                        has_required_local_dirs = bool(
                            det_model_dir and rec_model_dir and (not self.use_angle_cls or cls_model_dir)
                        )
                        using_any_local_dirs = bool(
                            det_model_dir or rec_model_dir or (self.use_angle_cls and cls_model_dir)
                        )
                        if settings.PADDLEOCR_LOCAL_MODELS_ONLY and not has_required_local_dirs:
                            raise OCREngineRuntimeError(
                                "Configured to use local PaddleOCR models only, but required model files are missing. "
                                f"runtime_tag={current_runtime_tag()} supported_runtime={int(current_runtime_supported())} "
                                f"det_dir={det_model_dir or 'missing'} rec_dir={rec_model_dir or 'missing'} "
                                f"cls_dir={cls_model_dir or ('disabled' if not self.use_angle_cls else 'missing')} "
                                "Download them from Settings -> Model Status (one-click download), "
                                "or disable PADDLEOCR_LOCAL_MODELS_ONLY to allow PaddleOCR's runtime fetch."
                            )
                        logger.info(
                            "resolved PaddleOCR models lang=%s runtime_tag=%s source=%s det_dir=%s rec_dir=%s cls_dir=%s",
                            target_lang,
                            current_runtime_tag(),
                            "local+download" if using_any_local_dirs and not has_required_local_dirs else (
                                "local" if has_required_local_dirs else "official-download"
                            ),
                            det_model_dir or "-",
                            rec_model_dir or "-",
                            cls_model_dir or ("disabled" if not self.use_angle_cls else "-"),
                        )
                    else:
                        ocr_kwargs["lang"] = target_lang
                        ocr_kwargs["ocr_version"] = settings.PADDLEOCR_OCR_VERSION
                    self._ocr_instances[target_lang] = PaddleOCR(**ocr_kwargs)
                else:
                    ocr_kwargs = dict(
                        use_angle_cls=self.use_angle_cls,
                        lang=target_lang,
                        use_gpu=settings.PADDLEOCR_USE_GPU,
                        ir_optim=settings.PADDLEOCR_IR_OPTIM,
                        enable_mkldnn=enable_mkldnn,
                        cpu_threads=settings.PADDLEOCR_CPU_THREADS,
                        det_db_thresh=self.det_db_thresh,
                        det_db_box_thresh=self.det_db_box_thresh,
                        show_log=False,
                    )
                    try:
                        self._ocr_instances[target_lang] = PaddleOCR(**ocr_kwargs)
                    except AttributeError as exc:
                        if enable_mkldnn and "set_mkldnn_cache_capacity" in str(exc):
                            logger.warning(
                                "Paddle runtime does not support MKLDNN cache controls; retrying without MKLDNN lang=%s",
                                target_lang,
                            )
                            ocr_kwargs["enable_mkldnn"] = False
                            self._ocr_instances[target_lang] = PaddleOCR(**ocr_kwargs)
                        else:
                            raise
                log_runtime_snapshot(
                    logger,
                    logging.INFO,
                    "created PaddleOCR instance lang=%s runtime_ms=%s",
                    target_lang,
                    int((time.monotonic() - started_at) * 1000),
                )
            except Exception as e:
                logger.exception("Failed to create PaddleOCR instance lang=%s", target_lang)
                raise

        return self._ocr_instances[target_lang]

    def _build_runtime_error(self, exc: Exception) -> OCREngineRuntimeError:
        raw = str(exc)
        if "ConvertPirAttribute2RuntimeAttribute not support" in raw:
            return OCREngineRuntimeError(
                "PaddleOCR runtime incompatibility detected. "
                "Rebuild with paddlepaddle==3.1.1, paddleocr==3.2.0, paddlex==3.2.0. "
                f"Original error: {raw}"
            )
        return OCREngineRuntimeError(f"OCR inference failed: {raw}")

    def detect_text(
        self,
        image: np.ndarray,
        lang: Optional[str] = None
    ) -> List[dict]:
        """
        Detect text in image

        Args:
            image: OpenCV image (BGR format)
            lang: Optional language override

        Returns:
            List of detections: [{'box': (x1,y1,x2,y2), 'text': str, 'confidence': float}, ...]
        """
        ocr = self._get_ocr_instance(lang)

        try:
            if self._is_v3_runtime():
                result = ocr.predict(image)
            else:
                result = ocr.ocr(image, cls=self.use_angle_cls)
        except Exception as e:
            log_runtime_snapshot(logger, logging.ERROR, "OCR failed during PaddleOCR inference lang=%s", lang or self.lang)
            logger.exception("OCR failed during PaddleOCR inference")
            raise self._build_runtime_error(e) from e

        return self._normalize_prediction_result(result)

    def recognize_in_region(
        self,
        image: np.ndarray,
        region: Tuple[int, int, int, int],
        lang: Optional[str] = None
    ) -> List[dict]:
        """
        Recognize text in specified region

        Args:
            image: Full image
            region: (x1, y1, x2, y2) region coordinates
            lang: Optional language override

        Returns:
            List of recognition results with coordinates adjusted to original image
        """
        x1, y1, x2, y2 = region

        # Clamp coordinates to image bounds
        h, w = image.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)

        roi = image[y1:y2, x1:x2]

        if roi.size == 0:
            return []

        detections = self.detect_text(roi, lang)

        # Convert coordinates to original image coordinate system
        for det in detections:
            self._shift_detection_geometry(det, x1, y1)

        return detections

    def detect_with_language_detection(
        self,
        image: np.ndarray,
        languages: List[str] = None
    ) -> Tuple[List[dict], str]:
        """
        Detect text and identify best language

        Args:
            image: Image to process
            languages: List of languages to try (default: ['ch', 'en'])

        Returns:
            Tuple of (detections, detected_language)
        """
        if languages is None:
            languages = ['ch', 'en']

        best_lang = 'ch'  # Default to Chinese
        best_result = []
        max_confidence = 0

        for lang in languages:
            try:
                result = self.detect_text(image, lang)

                if result:
                    avg_conf = sum(d['confidence'] for d in result) / len(result)
                    if avg_conf > max_confidence:
                        max_confidence = avg_conf
                        best_result = result
                        best_lang = lang
            except Exception as e:
                logger.warning(f"OCR with lang={lang} failed: {e}")
                continue

        return best_result, best_lang

    def detect_text_objects(
        self,
        image: np.ndarray,
        lang: Optional[str] = None
    ) -> List[TextDetection]:
        """
        Detect text and return as TextDetection objects

        Args:
            image: OpenCV image
            lang: Optional language override

        Returns:
            List of TextDetection objects
        """
        detections = self.detect_text(image, lang)

        results = []
        for det in detections:
            box = det['box']
            x1, y1, x2, y2 = box

            text_det = TextDetection(
                box=box,
                text=det['text'],
                confidence=det['confidence'],
                polygon=det.get('polygon'),
                rotated_box=det.get('rotated_box'),
                center_y=(y1 + y2) / 2,
                center_x=(x1 + x2) / 2,
                height=y2 - y1,
                width=x2 - x1
            )
            results.append(text_det)

        return results

    def is_available(self) -> bool:
        """Check if PaddleOCR is available"""
        try:
            from paddleocr import PaddleOCR
            return True
        except ImportError:
            return False

    def warm_up(self, langs: List[str] = None) -> List[dict]:
        """
        Warm up OCR models by preloading them

        Args:
            langs: List of languages to preload
        """
        if langs is None:
            langs = [self.lang]

        results = []
        for lang in langs:
            started_at = time.monotonic()
            try:
                self._get_ocr_instance(lang)
                runtime_ms = int((time.monotonic() - started_at) * 1000)
                logger.info("Warmed up OCR model for lang=%s runtime_ms=%s", lang, runtime_ms)
                results.append({
                    "lang": lang,
                    "ok": True,
                    "runtime_ms": runtime_ms,
                })
            except Exception as e:
                runtime_ms = int((time.monotonic() - started_at) * 1000)
                logger.warning("Failed to warm up OCR for lang=%s runtime_ms=%s err=%s", lang, runtime_ms, e)
                results.append({
                    "lang": lang,
                    "ok": False,
                    "runtime_ms": runtime_ms,
                    "error": str(e),
                })
        return results
