"""Minimal runtime-diagnostics helper used by the OCR pipeline.

The media-sense original also bundled file-logging / faulthandler / heartbeat /
uvicorn-logger setup. translip only needs the lightweight snapshot logger, so the
rest was dropped along with its stale ``MEDIA_SENSE_*`` env vars and ``/tmp`` log
paths.
"""

from __future__ import annotations

import logging


def log_runtime_snapshot(logger: logging.Logger, level: int, message: str, *args: object) -> None:
    logger.log(level, message, *args)
