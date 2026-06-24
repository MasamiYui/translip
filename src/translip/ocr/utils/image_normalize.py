"""Adaptive resize for OCR recognition input.

The PP-OCRv5 recognition model is trained with ``image_shape=[3, 48, 320]``
(see PaddleOCR official ``inference.yml``). Whatever crop you feed it, the
in-model ``RecResizeImg`` will forcibly bilinear-resize the input to height
48 before inference. That in-model LINEAR resize is the largest single source
of avoidable accuracy loss on:

- low-resolution sources (e.g. 480p subtitles ~18 px): pure bilinear upscale
  cannot recover stroke detail that was never there in the first place;
- very high-resolution sources (e.g. 4K subtitles 120 px+): a single large
  bilinear downsample destroys thin strokes (anti-aliasing collapse).

This module proxies that resize step in image-space with higher-quality
interpolation (CUBIC for upscaling, AREA for downscaling) plus an optional
Unsharp Mask for severely low-res inputs.

Module-internal constants are *intentionally* not exposed as Settings -- the
``target_h``/``target_w`` values are dictated by the model's trained shape,
not tunable hyper-parameters. The Settings layer only exposes trigger
thresholds and the master toggle.
"""

from __future__ import annotations

import cv2
import numpy as np

ADAPTIVE_RESIZE_VERSION = "v1"

_RECOG_NATIVE_H = 48
_USM_SIGMA = 1.0
_USM_WEIGHT_ORIG = 1.5
_USM_WEIGHT_BLUR = -0.5
_TWO_STEP_DOWNSCALE_INTERMEDIATE_H = 96
_MIN_VALID_DIM = 4


def adaptive_resize_for_recognition(
    image: np.ndarray,
    *,
    upscale_trigger_h: int,
    downscale_trigger_h: int,
    sharpen_threshold_h: int,
    target_h: int = _RECOG_NATIVE_H,
) -> np.ndarray:
    """Normalise a cropped subtitle patch towards the rec model's native height.

    Behaviour by source height ``h``:
      * ``h < sharpen_threshold_h``     : CUBIC upscale to ``target_h`` + USM sharpening
      * ``h < upscale_trigger_h``       : CUBIC upscale to ``target_h``
      * inside [upscale, downscale]     : no-op (let the model handle the small delta)
      * ``h <= 2 * target_h``           : single-step AREA downscale to ``target_h``
      * ``h >  2 * target_h``           : two-step AREA downscale via ``_TWO_STEP_INTERMEDIATE_H``

    Args:
        image: BGR numpy array, shape (H, W, C). May also be grayscale (H, W).
        upscale_trigger_h: heights below this trigger upscaling.
        downscale_trigger_h: heights above this trigger downscaling.
        sharpen_threshold_h: heights below this additionally apply USM (0 disables).
        target_h: target height (kept as a parameter for testability; should
            always equal the model's native height in production).

    Returns:
        Resized image (or the original reference when no change was needed).
        Aspect ratio is preserved. Caller retains ownership of the input array.
    """
    if image is None or image.size == 0:
        return image
    if image.ndim < 2:
        return image

    h, w = image.shape[:2]
    if h < _MIN_VALID_DIM or w < _MIN_VALID_DIM:
        return image
    if target_h <= 0:
        return image

    if h < upscale_trigger_h:
        return _upscale(
            image,
            target_h=target_h,
            apply_sharpen=(sharpen_threshold_h > 0 and h < sharpen_threshold_h),
        )

    if h > downscale_trigger_h:
        return _downscale(image, target_h=target_h)

    return image


def _upscale(image: np.ndarray, *, target_h: int, apply_sharpen: bool) -> np.ndarray:
    h, w = image.shape[:2]
    scale = target_h / float(h)
    new_w = max(_MIN_VALID_DIM, int(round(w * scale)))
    upscaled = cv2.resize(image, (new_w, target_h), interpolation=cv2.INTER_CUBIC)
    if not apply_sharpen:
        return upscaled
    blurred = cv2.GaussianBlur(upscaled, ksize=(0, 0), sigmaX=_USM_SIGMA)
    sharpened = cv2.addWeighted(upscaled, _USM_WEIGHT_ORIG, blurred, _USM_WEIGHT_BLUR, 0)
    return np.clip(sharpened, 0, 255).astype(upscaled.dtype, copy=False)


def _downscale(image: np.ndarray, *, target_h: int) -> np.ndarray:
    h, w = image.shape[:2]
    if h <= 2 * target_h:
        scale = target_h / float(h)
        new_w = max(_MIN_VALID_DIM, int(round(w * scale)))
        return cv2.resize(image, (new_w, target_h), interpolation=cv2.INTER_AREA)

    intermediate_h = _TWO_STEP_DOWNSCALE_INTERMEDIATE_H
    intermediate_scale = intermediate_h / float(h)
    intermediate_w = max(_MIN_VALID_DIM, int(round(w * intermediate_scale)))
    step1 = cv2.resize(image, (intermediate_w, intermediate_h), interpolation=cv2.INTER_AREA)

    final_scale = target_h / float(intermediate_h)
    new_w = max(_MIN_VALID_DIM, int(round(intermediate_w * final_scale)))
    return cv2.resize(step1, (new_w, target_h), interpolation=cv2.INTER_AREA)
