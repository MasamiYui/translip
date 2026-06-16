"""Readiness self-check — what's installed/present for each lab capability.

``translip-lab doctor`` answers "what can I actually run right now?": ffmpeg,
Pillow, ASR backends, the ocr/erase extras + their model weights, dataset
presence, and disk. Each check is ok / warn / missing; only ffmpeg/ffprobe are
critical (the whole engine needs them).
"""
from __future__ import annotations

import importlib.util
import os
import shutil
from pathlib import Path
from typing import Any

from .config import LabConfig


def _has_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def run_doctor(config: LabConfig) -> list[dict[str, Any]]:
    try:
        from translip.config import CACHE_ROOT
    except Exception:  # noqa: BLE001
        CACHE_ROOT = Path.home() / ".cache" / "translip"

    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str = "", *, critical: bool = False) -> None:
        status = "ok" if ok else ("missing" if critical else "warn")
        checks.append({"name": name, "status": status, "detail": detail, "critical": critical})

    # Core (required by the whole engine)
    add("ffmpeg", shutil.which("ffmpeg") is not None, "media I/O (required)", critical=True)
    add("ffprobe", shutil.which("ffprobe") is not None, "media probe (required)", critical=True)
    add("pillow", _has_module("PIL"), "synthetic-subtitle GT generator")

    # ASR backends
    add("faster-whisper", _has_module("faster_whisper"), "whisper ASR backend")
    add("funasr", _has_module("funasr"), "paraformer-zh ASR (recommended for Chinese)")

    # OCR extra + models
    add("paddleocr (extra: ocr)", _has_module("paddleocr"), "ocr-detect scenario")
    paddle_dir = Path(os.environ.get("PADDLEOCR_MODELS_BASE_DIR") or (CACHE_ROOT / "paddleocr_models"))
    add("paddle local models", paddle_dir.is_dir() and any(paddle_dir.iterdir()), str(paddle_dir))

    # Erase extra + weights
    add("opencv (extra: erase)", _has_module("cv2"), "subtitle-erase scenario")
    erase_dir = Path(os.environ.get("SUBTITLE_ERASE_MODELS_DIR") or (CACHE_ROOT / "erase_models"))
    add("erase weights (sttn.pth)", (erase_dir / "sttn.pth").is_file(), str(erase_dir / "sttn.pth"))

    # Lab paths + disk
    add("datasets dir", config.datasets_dir.exists(), str(config.datasets_dir))
    runs_ok = config.runs_dir.exists() or _can_create(config.runs_dir)
    add("runs dir writable", runs_ok, str(config.runs_dir))
    free_gb = _free_gb(config.home)
    if free_gb is not None:
        add("disk free", free_gb > 5.0, f"{free_gb:.1f} GB free")

    # Real corpora presence (the ones needing user-placed data)
    for name in ("aishell4", "alimeeting"):
        root = config.datasets_dir / name
        add(f"dataset: {name}", root.exists() and any(root.iterdir()), str(root))

    return checks


def _can_create(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        return True
    except OSError:
        return False


def _free_gb(path: Path) -> float | None:
    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    try:
        return shutil.disk_usage(probe).free / (1024 ** 3)
    except OSError:
        return None
