"""Conservative logging helpers for runtime diagnostics."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import os
import sys


_LOGGING_CONFIGURED = False


def _env_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default

def resolve_log_dir() -> str:
    configured = (os.environ.get("MEDIA_SENSE_CORE_LOG_DIR") or os.environ.get("MEDIA_SENSE_LOG_DIR") or "").strip()
    if configured:
        return os.path.abspath(os.path.expanduser(configured))
    return os.path.abspath(os.path.join(os.environ.get("OUTPUT_DIR", "/tmp/outputs"), "logs"))


def configure_logging(log_level: str = "INFO") -> tuple[str, str]:
    global _LOGGING_CONFIGURED

    max_bytes = _env_int("MEDIA_SENSE_CORE_LOG_MAX_BYTES", 20 * 1024 * 1024)
    backup_count = _env_int("MEDIA_SENSE_CORE_LOG_BACKUP_COUNT", 5)
    level_name = (log_level or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    log_dir = resolve_log_dir()
    app_log_path = os.path.join(log_dir, "media-sense.log")
    crash_log_path = os.path.join(log_dir, "media-sense-crash.log")

    if _LOGGING_CONFIGURED:
        return app_log_path, crash_log_path

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] pid=%(process)d tid=%(threadName)s %(name)s: %(message)s"
    )
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)

    handlers = [stream_handler]
    file_handler = None
    candidate_dirs = [log_dir, "/tmp/media-sense-logs"]
    for candidate_dir in candidate_dirs:
        try:
            os.makedirs(candidate_dir, exist_ok=True)
            candidate_log_path = os.path.join(candidate_dir, "media-sense.log")
            file_handler = RotatingFileHandler(
                candidate_log_path,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
                delay=True,
            )
            file_handler.setFormatter(formatter)
            handlers.append(file_handler)
            app_log_path = candidate_log_path
            crash_log_path = os.path.join(candidate_dir, "media-sense-crash.log")
            break
        except OSError:
            file_handler = None

    logging.basicConfig(level=level, handlers=handlers, force=True)
    logging.captureWarnings(True)
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True
        uvicorn_logger.setLevel(level)
    root_logger = logging.getLogger(__name__)
    if file_handler is None:
        root_logger.warning("file logging unavailable, falling back to stdout only target_dir=%s", log_dir)
    _LOGGING_CONFIGURED = True
    return app_log_path, crash_log_path


def enable_faulthandler_logging(crash_log_path: str) -> None:
    # Intentionally disabled in conservative mode to avoid startup or security issues.
    return None


def install_signal_logging(logger: logging.Logger) -> None:
    # Intentionally disabled in conservative mode to avoid overriding process signal handling.
    return None


def log_runtime_snapshot(logger: logging.Logger, level: int, message: str, *args: object) -> None:
    logger.log(level, message, *args)


def start_runtime_heartbeat(logger: logging.Logger, interval_sec: int) -> None:
    # Intentionally disabled in conservative mode to avoid background-thread side effects.
    return None
