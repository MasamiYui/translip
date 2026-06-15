"""Pure metric functions (numpy/scipy only). (prediction, ground_truth) -> scalar(s)."""
from __future__ import annotations

from .audio import si_sdr, sdr
from .detection import box_iou, match_boxes, prf
from .diarization import der, parse_rttm
from .image import psnr, ssim
from .text import cer, edit_distance, wer

__all__ = [
    "cer", "wer", "edit_distance",
    "der", "parse_rttm",
    "si_sdr", "sdr",
    "psnr", "ssim",
    "box_iou", "match_boxes", "prf",
]
