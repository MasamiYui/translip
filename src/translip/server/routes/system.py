from __future__ import annotations

import platform
import sys
import threading
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .. import cache_manager

router = APIRouter(prefix="/api/system", tags=["system"])


# Re-export the historical helper so existing tests (test_system_routes.py)
# can still import `from translip.server.routes import system` and access
# `system.collect_model_statuses`.
def collect_model_statuses(
    *,
    cache_root: Path | None = None,
    huggingface_cache_root: Path | None = None,
):
    return cache_manager.collect_model_statuses(
        cache_root=cache_root,
        huggingface_cache_root=huggingface_cache_root,
    )


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class SetDirRequest(BaseModel):
    target: str
    create_if_missing: bool = True


class MigrateRequest(BaseModel):
    target: str
    mode: str = Field(default="move", pattern="^(move|copy)$")
    switch_after: bool = True
    allow_non_empty: bool = False


class CleanupRequest(BaseModel):
    keys: list[str]


class ModelDownloadRequest(BaseModel):
    keys: list[str] | None = None


class HfTokenRequest(BaseModel):
    hf_token: str | None = None


# ---------------------------------------------------------------------------
# Generic system info
# ---------------------------------------------------------------------------


@router.get("/info")
def get_system_info():
    import torch

    if torch.cuda.is_available():
        device = "CUDA"
    elif torch.backends.mps.is_available():
        device = "MPS (Apple Silicon)"
    else:
        device = "CPU"

    cache_root = cache_manager.apply_active_cache_root()
    cache_size = cache_manager.dir_size(cache_root)
    models = cache_manager.collect_model_statuses()

    return {
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "platform": platform.platform(),
        "device": device,
        "cache_dir": str(cache_root),
        "cache_size_bytes": cache_size,
        "models": models,
    }


@router.get("/probe")
def probe_media(path: str):
    """Probe media file information."""
    from ...utils.ffmpeg import probe_media as _probe_media

    p = Path(path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="File not found")

    info = _probe_media(p)
    has_video = info.media_type == "video"
    return {
        "path": str(p),
        "duration_sec": info.duration_sec,
        "has_video": has_video,
        "has_audio": info.audio_stream_count > 0,
        "sample_rate": info.sample_rate,
        "format_name": info.format_name,
    }


# Media file extensions surfaced by the in-app file picker. Non-media files are
# hidden so the picker stays focused on selectable inputs.
_MEDIA_EXTENSIONS = frozenset(
    {
        ".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".flv",
        ".ts", ".m2ts", ".mts", ".wmv", ".mpg", ".mpeg", ".3gp", ".ogv",
        ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma",
    }
)


class FsEntry(BaseModel):
    name: str
    path: str
    is_dir: bool
    is_media: bool
    size_bytes: int | None = None


class BrowseResponse(BaseModel):
    path: str
    parent: str | None
    home: str
    entries: list[FsEntry]


@router.get("/browse", response_model=BrowseResponse)
def browse_filesystem(
    path: str | None = Query(default=None),
    show_hidden: bool = Query(default=False),
):
    """List directories and media files for the in-app file picker.

    translip is local-first: the server runs on the user's own machine, so
    browsing the local filesystem to pick an input video is the intended flow.
    Directories are always returned (to allow navigation); plain files are
    limited to recognised media extensions to keep the picker uncluttered.
    """
    base = Path(path).expanduser() if path else Path.home()
    try:
        base = base.resolve()
    except OSError as exc:
        raise HTTPException(status_code=400, detail="invalid_path") from exc

    if not base.exists():
        raise HTTPException(status_code=404, detail="path_not_found")
    # If a file was passed, browse its containing directory instead.
    if not base.is_dir():
        base = base.parent

    try:
        children = list(base.iterdir())
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="permission_denied") from exc

    entries: list[FsEntry] = []
    for child in children:
        if not show_hidden and child.name.startswith("."):
            continue
        try:
            is_dir = child.is_dir()
        except OSError:
            continue  # broken symlink / unreadable entry
        if is_dir:
            entries.append(FsEntry(name=child.name, path=str(child), is_dir=True, is_media=False))
            continue
        if child.suffix.lower() not in _MEDIA_EXTENSIONS:
            continue
        try:
            size = child.stat().st_size
        except OSError:
            size = None
        entries.append(
            FsEntry(name=child.name, path=str(child), is_dir=False, is_media=True, size_bytes=size)
        )

    # Directories first, then files; case-insensitive alphabetical within each.
    entries.sort(key=lambda e: (not e.is_dir, e.name.lower()))

    parent = str(base.parent) if base.parent != base else None
    return BrowseResponse(path=str(base), parent=parent, home=str(Path.home()), entries=entries)


# ---------------------------------------------------------------------------
# Cache management
# ---------------------------------------------------------------------------


@router.get("/cache/breakdown")
def get_cache_breakdown(refresh: bool = Query(default=False)):
    cache_manager.apply_active_cache_root()
    if refresh:
        _invalidate_breakdown_cache()
    return _cached_breakdown()


@router.post("/cache/set-dir")
def set_cache_dir(body: SetDirRequest):
    try:
        path = cache_manager.set_cache_dir(body.target, create_if_missing=body.create_if_missing)
    except cache_manager.CachePathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _invalidate_breakdown_cache()
    return {"ok": True, "cache_dir": str(path)}


@router.post("/cache/reset-default")
def reset_cache_dir():
    path = cache_manager.reset_cache_dir_to_default()
    _invalidate_breakdown_cache()
    return {"ok": True, "cache_dir": str(path)}


@router.delete("/cache/item")
def delete_cache_item(key: str = Query(..., min_length=1)):
    try:
        freed = cache_manager.cleanup_group(key)
    except cache_manager.CachePathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _invalidate_breakdown_cache()
    return {"ok": True, "key": key, "freed_bytes": freed}


@router.post("/cache/cleanup")
def cleanup_cache(body: CleanupRequest):
    if not body.keys:
        raise HTTPException(status_code=400, detail="keys_required")
    # Strip whitespace / empties before passing to service layer.
    keys = [k.strip() for k in body.keys if isinstance(k, str) and k.strip()]
    if not keys:
        raise HTTPException(status_code=400, detail="keys_required")
    result = cache_manager.cleanup_groups(keys)
    _invalidate_breakdown_cache()
    return result


@router.post("/cache/migrate")
def start_cache_migration(body: MigrateRequest):
    try:
        task = cache_manager.migration_manager.start(
            target=body.target,
            mode=body.mode,  # type: ignore[arg-type]
            switch_after=body.switch_after,
            allow_non_empty=body.allow_non_empty,
        )
    except cache_manager.CachePathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _invalidate_breakdown_cache()
    return task.to_dict()


@router.get("/cache/migrate/{task_id}")
def get_cache_migration(task_id: str):
    task = cache_manager.migration_manager.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task_not_found")
    return task.to_dict()


@router.post("/cache/migrate/{task_id}/cancel")
def cancel_cache_migration(task_id: str):
    ok = cache_manager.migration_manager.cancel(task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="task_not_cancellable")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Model download
# ---------------------------------------------------------------------------


@router.get("/models/missing")
def list_missing_models():
    """List model registry keys whose weights are not yet present locally."""
    keys = cache_manager.list_missing_model_keys()
    items = []
    for key in keys:
        group = cache_manager.find_group(key)
        items.append(
            {
                "key": key,
                "label": group.label if group else key,
                "auto_downloadable": cache_manager.is_auto_downloadable(key),
            }
        )
    return {"items": items}


@router.post("/models/download-missing")
def start_model_download(body: ModelDownloadRequest | None = None):
    only = body.keys if body else None
    try:
        job = cache_manager.model_download_manager.start_missing(only_keys=only)
    except cache_manager.ModelDownloadError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return job.to_dict()


@router.get("/models/download/{job_id}")
def get_model_download(job_id: str):
    job = cache_manager.model_download_manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job_not_found")
    return job.to_dict()


@router.post("/models/download/{job_id}/cancel")
def cancel_model_download(job_id: str):
    ok = cache_manager.model_download_manager.cancel(job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="job_not_cancellable")
    return {"ok": True}


# ---------------------------------------------------------------------------
# HuggingFace token (for gated models like pyannote diarization)
# ---------------------------------------------------------------------------


@router.get("/hf-token")
def get_hf_token():
    """Report whether a HuggingFace token is configured (never returns the value)."""
    return {"ok": True, "hf_token_set": bool(cache_manager.read_user_setting("hf_token"))}


@router.post("/hf-token")
def save_hf_token(body: HfTokenRequest):
    """Persist (or clear, when empty) the HuggingFace token used for gated models."""
    token = (body.hf_token or "").strip() or None
    cache_manager.update_user_setting("hf_token", token)
    cache_manager.apply_hf_token_to_env()
    return {"ok": True, "hf_token_set": bool(token)}


# ---------------------------------------------------------------------------
# Breakdown short-cache: prevent flood re-scans on React Query retries /
# StrictMode double-mount / rapid UI refreshes.
# ---------------------------------------------------------------------------

_BREAKDOWN_CACHE_TTL = 5.0  # seconds
_BREAKDOWN_CACHE_LOCK = threading.Lock()
_BREAKDOWN_CACHE: dict[str, object] | None = None
_BREAKDOWN_CACHE_AT: float = 0.0


def _cached_breakdown() -> dict[str, object]:
    global _BREAKDOWN_CACHE, _BREAKDOWN_CACHE_AT
    now = time.time()
    with _BREAKDOWN_CACHE_LOCK:
        if _BREAKDOWN_CACHE is not None and (now - _BREAKDOWN_CACHE_AT) < _BREAKDOWN_CACHE_TTL:
            return _BREAKDOWN_CACHE
    result = cache_manager.compute_breakdown()
    with _BREAKDOWN_CACHE_LOCK:
        _BREAKDOWN_CACHE = result
        _BREAKDOWN_CACHE_AT = time.time()
    return result


def _invalidate_breakdown_cache() -> None:
    global _BREAKDOWN_CACHE, _BREAKDOWN_CACHE_AT
    with _BREAKDOWN_CACHE_LOCK:
        _BREAKDOWN_CACHE = None
        _BREAKDOWN_CACHE_AT = 0.0
