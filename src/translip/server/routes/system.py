from __future__ import annotations

import os
import platform
import shutil
import sys
from pathlib import Path

from fastapi import APIRouter

from ...config import CACHE_ROOT

router = APIRouter(prefix="/api/system", tags=["system"])

_CDX23_WEIGHT_GLOB = "*.th"


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


def _default_huggingface_cache_root() -> Path:
    if cache_root := os.environ.get("HUGGINGFACE_HUB_CACHE"):
        return Path(cache_root)
    if cache_root := os.environ.get("HF_HUB_CACHE"):
        return Path(cache_root)
    hf_home = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
    return hf_home / "hub"


def _matches_any_path(paths: list[Path]) -> bool:
    return any(path.exists() for path in paths)


def _has_cdx23_weights(paths: list[Path]) -> bool:
    for path in paths:
        if not path.exists():
            continue
        if path.is_file() and path.suffix == ".th":
            return True
        if path.is_dir() and any(path.glob(_CDX23_WEIGHT_GLOB)):
            return True
    return False


def _matches_huggingface_model_glob(cache_root: Path, pattern: str) -> bool:
    return any(path.is_dir() for path in cache_root.glob(pattern))


def _has_moss_tts_nano_onnx_assets(cache_root: Path, hf_cache_root: Path) -> bool:
    model_roots = [cache_root / "models"]
    if model_dir := os.environ.get("MOSS_TTS_NANO_MODEL_DIR"):
        model_roots.append(Path(model_dir))

    has_tts = any((root / "MOSS-TTS-Nano-100M-ONNX").exists() for root in model_roots)
    has_codec = any((root / "MOSS-Audio-Tokenizer-Nano-ONNX").exists() for root in model_roots)
    if has_tts and has_codec:
        return True

    return (
        _matches_huggingface_model_glob(hf_cache_root, "models--OpenMOSS-Team--MOSS-TTS-Nano-100M-ONNX*")
        and _matches_huggingface_model_glob(
            hf_cache_root,
            "models--OpenMOSS-Team--MOSS-Audio-Tokenizer-Nano-ONNX*",
        )
    )


def collect_model_statuses(
    *,
    cache_root: Path = CACHE_ROOT,
    huggingface_cache_root: Path | None = None,
) -> list[dict[str, str]]:
    hf_cache_root = huggingface_cache_root or _default_huggingface_cache_root()

    checks = [
        {
            "name": "CDX23 weights",
            "status": "available"
            if _has_cdx23_weights(
                [
                    cache_root / "models" / "cdx23",
                    cache_root / "models" / "CDX23",
                ]
            )
            else "missing",
        },
        {
            "name": "faster-whisper small",
            "status": "available"
            if (
                _matches_any_path([cache_root / "models" / "faster_whisper" / "small"])
                or _matches_huggingface_model_glob(
                    hf_cache_root, "models--Systran--faster-whisper-small*"
                )
            )
            else "missing",
        },
        {
            "name": "SpeechBrain ECAPA",
            "status": "available"
            if (
                _matches_any_path(
                    [
                        cache_root / "speechbrain" / "spkrec-ecapa-voxceleb",
                        cache_root / "speechbrain",
                    ]
                )
                or _matches_huggingface_model_glob(
                    hf_cache_root, "models--speechbrain--spkrec-ecapa-voxceleb*"
                )
            )
            else "missing",
        },
        {
            "name": "M2M100 418M",
            "status": "available"
            if (
                _matches_any_path(
                    [
                        cache_root / "transformers" / "models--facebook--m2m100_418M",
                        cache_root / "models" / "m2m100_418M",
                    ]
                )
                or _matches_huggingface_model_glob(hf_cache_root, "models--facebook--m2m100_418M*")
            )
            else "missing",
        },
        {
            "name": "MOSS-TTS-Nano ONNX",
            "status": "available" if _has_moss_tts_nano_onnx_assets(cache_root, hf_cache_root) else "missing",
        },
        {
            "name": "Qwen3TTS",
            "status": "available"
            if (
                _matches_any_path([cache_root / "models" / "qwen3tts"])
                or _matches_huggingface_model_glob(hf_cache_root, "models--Qwen--Qwen3-TTS-*")
            )
            else "missing",
        },
    ]
    return checks


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
    models = collect_model_statuses()

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
