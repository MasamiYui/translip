from __future__ import annotations

import platform
import shutil
import sys
from pathlib import Path

from fastapi import APIRouter

from ...config import CACHE_ROOT

router = APIRouter(prefix="/api/system", tags=["system"])

_MODEL_CHECKS = [
    {"name": "CDX23 weights", "path": str(CACHE_ROOT / "models" / "CDX23")},
    {"name": "faster-whisper small", "path": str(CACHE_ROOT / "models" / "faster_whisper" / "small")},
    {"name": "SpeechBrain ECAPA", "path": str(CACHE_ROOT / "speechbrain")},
    {"name": "M2M100 418M", "path": str(CACHE_ROOT / "models" / "m2m100_418M")},
    {"name": "Qwen3TTS", "path": str(CACHE_ROOT / "models" / "qwen3tts")},
]


def _dir_size(p: Path) -> int:
    if not p.exists():
        return 0
    total = 0
    for f in p.rglob("*"):
        if f.is_file():
            try:
                total += f.stat().st_size
            except OSError:
                pass
    return total


@router.get("/info")
def get_system_info():
    import torch

    if torch.cuda.is_available():
        device = "CUDA"
    elif torch.backends.mps.is_available():
        device = "MPS (Apple Silicon)"
    else:
        device = "CPU"

    cache_size = _dir_size(CACHE_ROOT)

    models = []
    for m in _MODEL_CHECKS:
        p = Path(m["path"])
        models.append(
            {
                "name": m["name"],
                "status": "available" if p.exists() else "missing",
            }
        )

    return {
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "platform": platform.platform(),
        "device": device,
        "cache_dir": str(CACHE_ROOT),
        "cache_size_bytes": cache_size,
        "models": models,
    }


@router.get("/probe")
def probe_media(path: str):
    """Probe media file information."""
    from ...utils.ffmpeg import probe_media

    p = Path(path)
    if not p.exists():
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="File not found")

    info = probe_media(p)
    has_video = info.media_type == "video"
    return {
        "path": str(p),
        "duration_sec": info.duration_sec,
        "has_video": has_video,
        "has_audio": info.audio_stream_count > 0,
        "sample_rate": info.sample_rate,
        "format_name": info.format_name,
    }
