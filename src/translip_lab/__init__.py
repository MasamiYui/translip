"""translip-lab — a loosely-coupled evaluation lab for the translip pipeline.

This package tests/optimizes existing translip capabilities against external,
ground-truth-annotated datasets (CER / DER / SI-SDR / PSNR-SSIM / detection-F1).

Design rule (loose coupling): ``translip_lab`` depends on ``translip`` one way
only — translip never imports translip_lab. The integration surface is the
stable translip CLI/JSON contract (subprocess) plus a few pure helper imports
(``translip.transcription.benchmark`` for ASR scoring). Deleting this package and
the single nav link in the frontend leaves the main system untouched.

Everything in the core engine runs on translip's base dependencies
(numpy / scipy / soundfile) + ffmpeg + the stdlib, so the test suite needs no
extra installs.
"""
from __future__ import annotations

__all__ = ["__version__"]
__version__ = "0.1.0"
