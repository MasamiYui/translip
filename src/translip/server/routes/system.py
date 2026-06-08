from __future__ import annotations

import platform
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path as PathParam, Query
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
    target: str = Field(description="目标缓存目录的绝对路径")
    create_if_missing: bool = Field(default=True, description="目录不存在时是否自动创建")


class MigrateRequest(BaseModel):
    target: str = Field(description="迁移目标缓存目录的绝对路径")
    mode: str = Field(default="move", pattern="^(move|copy)$", description="迁移方式：move 移动，copy 复制")
    switch_after: bool = Field(default=True, description="迁移完成后是否切换为新的活动缓存目录")
    allow_non_empty: bool = Field(default=False, description="是否允许目标目录非空")


class CleanupRequest(BaseModel):
    keys: list[str] = Field(description="要清理的缓存分组键列表")


class GcOutputsRequest(BaseModel):
    max_bytes: int | None = Field(default=None, description="output-pipeline 总字节上限，超出按 LRU 驱逐未引用产物；留空不按字节限制")
    max_count: int | None = Field(default=None, description="output-pipeline 目录数上限；留空不按数量限制")
    dry_run: bool = Field(default=False, description="仅返回将被驱逐的目录，不实际删除")


class ModelDownloadRequest(BaseModel):
    keys: list[str] | None = Field(default=None, description="指定要下载的模型注册键；留空则下载全部缺失的模型")


class HfTokenRequest(BaseModel):
    hf_token: str | None = Field(default=None, description="要保存的 HuggingFace 访问令牌；为空则清除已保存的令牌")


class HfTokenTestRequest(BaseModel):
    # Optional: test a not-yet-saved token. Falls back to the saved/env token.
    hf_token: str | None = Field(default=None, description="待校验的 HuggingFace 令牌；留空则回退到已保存或环境变量中的令牌")


class LlmKeyRequest(BaseModel):
    provider: str = Field(description="大模型服务商标识，如 deepseek")
    api_key: str | None = Field(default=None, description="要保存的 API 密钥；为空则清除该服务商已保存的密钥；不提交该字段则保持原值")
    base_url: str | None = Field(default=None, description="要保存的 API 基地址（如兼容代理）；为空则清除恢复官方地址；不提交该字段则保持原值")


class LlmKeyTestRequest(BaseModel):
    provider: str = Field(description="大模型服务商标识，如 deepseek")
    # Optional: test a not-yet-saved key. Falls back to the saved/env key when omitted.
    api_key: str | None = Field(default=None, description="待校验的 API 密钥；留空则回退到已保存或环境变量中的密钥")
    base_url: str | None = Field(default=None, description="待校验的 API 基地址；留空则回退到已保存或环境变量中的地址")


# ---------------------------------------------------------------------------
# Generic system info
# ---------------------------------------------------------------------------


@router.get("/config/effective", summary="有效配置内省")
def get_effective_config():
    """返回各运营关键配置项的有效值与来源（env 覆盖或内置默认）；密钥类只报告是否已设置，不回传明文。"""
    from ..config_introspect import introspect_config

    return {"knobs": introspect_config()}


@router.get("/info", summary="系统信息")
def get_system_info():
    """返回 Python 版本、运行平台、推理设备（CUDA/MPS/CPU）、当前缓存目录及其占用大小、各模型的本地状态。"""
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


@router.get("/probe", summary="探测媒体信息")
def probe_media(path: Annotated[str, Query(description="要探测的媒体文件的服务器本地路径")]):
    """探测本地媒体文件信息：返回时长、是否含视频/音频、采样率与容器格式；文件不存在返回 404。"""
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


class PickFileRequest(BaseModel):
    # A file or directory path used to position the dialog's starting folder.
    initial_path: str | None = Field(default=None, description="用于定位对话框初始目录的文件或目录路径")
    prompt: str | None = Field(default=None, description="文件选择对话框的提示文案")


class PickFileResponse(BaseModel):
    path: str | None = Field(description="用户选中的文件路径；取消选择时为 null")
    cancelled: bool = Field(description="用户是否取消了选择")


def _resolve_initial_dir(initial_path: str | None) -> str | None:
    """Return an existing directory to open the dialog in, or None.

    Accepts either a directory or a file path (its parent folder is used).
    """
    if not initial_path:
        return None
    p = Path(initial_path).expanduser()
    if p.is_dir():
        return str(p)
    if p.parent.is_dir():
        return str(p.parent)
    return None


def _escape_applescript(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _open_native_file_dialog(initial_path: str | None, prompt: str) -> str | None:
    """Open a blocking native OS "open file" dialog and return the chosen path.

    Returns None when the user cancels. Raises RuntimeError when the host has no
    usable dialog helper. translip is local-first, so the dialog renders on the
    machine running the server; this is unavailable on headless/remote hosts.
    """
    initial_dir = _resolve_initial_dir(initial_path)

    if sys.platform == "darwin":
        choose = f'choose file with prompt "{_escape_applescript(prompt)}"'
        if initial_dir:
            choose += f' default location (POSIX file "{_escape_applescript(initial_dir)}")'
        # Foreground the GUI session so the dialog actually appears when the
        # server runs detached (start_new_session=True via dev.sh); otherwise
        # macOS returns an instant -128 "user canceled" and shows nothing.
        # Activating System Events (~0.1s) is used instead of a bare `activate`,
        # which carries a fixed ~2s app-activation delay.
        args = [
            "osascript",
            "-e", 'tell application "System Events" to activate',
            "-e", f"set f to {choose}",
            "-e", "POSIX path of f",
        ]
        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=600)
        except FileNotFoundError as exc:
            raise RuntimeError("osascript_unavailable") from exc
        except subprocess.TimeoutExpired:
            return None
        if result.returncode != 0:
            stderr = result.stderr.lower()
            if "-128" in stderr or "cancel" in stderr:
                return None  # user dismissed the dialog
            raise RuntimeError(result.stderr.strip() or "dialog_failed")
        return result.stdout.strip() or None

    if sys.platform.startswith("win"):
        ps = (
            "Add-Type -AssemblyName System.Windows.Forms;"
            "$d = New-Object System.Windows.Forms.OpenFileDialog;"
            + (f'$d.InitialDirectory = "{initial_dir}";' if initial_dir else "")
            + "if ($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK)"
            " { [Console]::Out.Write($d.FileName) }"
        )
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-STA", "-Command", ps],
                capture_output=True,
                text=True,
                timeout=600,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("powershell_unavailable") from exc
        except subprocess.TimeoutExpired:
            return None
        return result.stdout.strip() or None

    # Linux / other POSIX: try common desktop dialog helpers in turn.
    candidates = [
        ["zenity", "--file-selection", f"--title={prompt}"]
        + ([f"--filename={initial_dir}/"] if initial_dir else []),
        ["kdialog", "--getopenfilename", initial_dir or "."],
    ]
    for tool_args in candidates:
        try:
            result = subprocess.run(tool_args, capture_output=True, text=True, timeout=600)
        except FileNotFoundError:
            continue  # helper not installed; try the next one
        except subprocess.TimeoutExpired:
            return None
        if result.returncode == 0:
            return result.stdout.strip() or None
        return None  # non-zero from zenity/kdialog means cancelled
    raise RuntimeError("no_dialog_helper")


@router.post("/pick-file", response_model=PickFileResponse, summary="打开本地选择文件对话框")
def pick_file(body: PickFileRequest | None = None):
    """在运行服务的本机弹出原生文件选择对话框并返回所选路径。仅本地优先场景可用：用户取消时返回 cancelled=true；无可用原生对话框（如无界面主机）时返回 501，供前端回退到手动输入。"""
    initial_path = body.initial_path if body else None
    prompt = (body.prompt if body else None) or "Select input video"
    try:
        path = _open_native_file_dialog(initial_path, prompt)
    except RuntimeError as exc:
        raise HTTPException(status_code=501, detail=f"native_dialog_unavailable:{exc}") from exc
    return PickFileResponse(path=path, cancelled=path is None)


# ---------------------------------------------------------------------------
# Cache management
# ---------------------------------------------------------------------------


@router.get("/cache/breakdown", summary="缓存占用明细")
def get_cache_breakdown(
    refresh: bool = Query(default=False, description="是否强制重新扫描，忽略短期内的结果缓存"),
):
    """按分组返回缓存目录的占用明细；结果带短期缓存，传 refresh=true 可强制重新扫描。"""
    cache_manager.apply_active_cache_root()
    if refresh:
        _invalidate_breakdown_cache()
    return _cached_breakdown()


@router.post("/cache/set-dir", summary="设置缓存目录")
def set_cache_dir(body: SetDirRequest):
    """将活动缓存目录切换到指定路径（不迁移已有数据）；路径非法返回 400。"""
    try:
        path = cache_manager.set_cache_dir(body.target, create_if_missing=body.create_if_missing)
    except cache_manager.CachePathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _invalidate_breakdown_cache()
    return {"ok": True, "cache_dir": str(path)}


@router.post("/cache/reset-default", summary="重置缓存目录")
def reset_cache_dir():
    """将活动缓存目录恢复为默认路径。"""
    path = cache_manager.reset_cache_dir_to_default()
    _invalidate_breakdown_cache()
    return {"ok": True, "cache_dir": str(path)}


@router.delete("/cache/item", summary="删除缓存分组")
def delete_cache_item(
    key: str = Query(..., min_length=1, description="要删除的缓存分组键"),
):
    """删除指定分组的缓存文件并返回释放的字节数；分组键非法返回 400。"""
    try:
        freed = cache_manager.cleanup_group(key)
    except cache_manager.CachePathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _invalidate_breakdown_cache()
    return {"ok": True, "key": key, "freed_bytes": freed}


@router.post("/cache/cleanup", summary="批量清理缓存")
def cleanup_cache(body: CleanupRequest):
    """批量删除多个分组的缓存文件；keys 为空返回 400。"""
    if not body.keys:
        raise HTTPException(status_code=400, detail="keys_required")
    # Strip whitespace / empties before passing to service layer.
    keys = [k.strip() for k in body.keys if isinstance(k, str) and k.strip()]
    if not keys:
        raise HTTPException(status_code=400, detail="keys_required")
    result = cache_manager.cleanup_groups(keys)
    _invalidate_breakdown_cache()
    return result


@router.post("/cache/gc-outputs", summary="按 LRU/容量回收流水线产物")
def gc_pipeline_outputs(body: GcOutputsRequest):
    """对 output-pipeline 做 LRU/容量回收：仅驱逐 DB 不再引用的产物目录，最旧优先，直到低于上限。"""
    cache_manager.apply_active_cache_root()
    result = cache_manager.gc_pipeline_outputs(
        max_bytes=body.max_bytes,
        max_count=body.max_count,
        dry_run=body.dry_run,
    )
    if not body.dry_run and result.get("evicted"):
        _invalidate_breakdown_cache()
    return result


@router.post("/cache/migrate", summary="启动缓存迁移")
def start_cache_migration(body: MigrateRequest):
    """启动后台任务，将缓存数据移动或复制到目标目录（可在完成后切换为新目录）；目标路径非法返回 400。"""
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


@router.get("/cache/migrate/{task_id}", summary="查询缓存迁移进度")
def get_cache_migration(task_id: Annotated[str, PathParam(description="缓存迁移任务 ID")]):
    """查询指定缓存迁移任务的状态与进度；任务不存在返回 404。"""
    task = cache_manager.migration_manager.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task_not_found")
    return task.to_dict()


@router.post("/cache/migrate/{task_id}/cancel", summary="取消缓存迁移")
def cancel_cache_migration(task_id: Annotated[str, PathParam(description="缓存迁移任务 ID")]):
    """取消正在进行的缓存迁移任务；任务不存在或不可取消返回 404。"""
    ok = cache_manager.migration_manager.cancel(task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="task_not_cancellable")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Model download
# ---------------------------------------------------------------------------


@router.get("/models/missing", summary="缺失模型列表")
def list_missing_models():
    """列出本地尚未下载权重的模型注册键，并标注是否支持自动下载。"""
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


@router.post("/models/download-missing", summary="下载缺失模型")
def start_model_download(body: ModelDownloadRequest | None = None):
    """启动后台作业下载缺失的模型权重（可指定子集）；已有下载在进行中返回 409。"""
    only = body.keys if body else None
    try:
        job = cache_manager.model_download_manager.start_missing(only_keys=only)
    except cache_manager.ModelDownloadError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return job.to_dict()


@router.get("/models/download/{job_id}", summary="查询模型下载进度")
def get_model_download(job_id: Annotated[str, PathParam(description="模型下载作业 ID")]):
    """查询指定模型下载作业的状态与进度；作业不存在返回 404。"""
    job = cache_manager.model_download_manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job_not_found")
    return job.to_dict()


@router.post("/models/download/{job_id}/cancel", summary="取消模型下载")
def cancel_model_download(job_id: Annotated[str, PathParam(description="模型下载作业 ID")]):
    """取消正在进行的模型下载作业；作业不存在或不可取消返回 404。"""
    ok = cache_manager.model_download_manager.cancel(job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="job_not_cancellable")
    return {"ok": True}


# ---------------------------------------------------------------------------
# HuggingFace token (for gated models like pyannote diarization)
# ---------------------------------------------------------------------------


@router.get("/hf-token", summary="HuggingFace 令牌状态")
def get_hf_token():
    """返回是否已配置 HuggingFace 令牌（不返回令牌明文）。"""
    return {"ok": True, "hf_token_set": bool(cache_manager.read_user_setting("hf_token"))}


@router.post("/hf-token", summary="保存 HuggingFace 令牌")
def save_hf_token(body: HfTokenRequest):
    """保存（或在为空时清除）用于访问受限模型（如 pyannote 说话人分离）的 HuggingFace 令牌，并写入环境变量。"""
    token = (body.hf_token or "").strip() or None
    cache_manager.update_user_setting("hf_token", token)
    cache_manager.apply_hf_token_to_env()
    return {"ok": True, "hf_token_set": bool(token)}


def _verify_hf_token(token: str | None, *, timeout_sec: int = 15) -> dict:
    """Check a HuggingFace token via the whoami endpoint. Never raises."""
    if not token:
        return {"ok": False, "message": "No HuggingFace token provided."}
    import json
    import urllib.error
    import urllib.request

    request = urllib.request.Request(
        "https://huggingface.co/api/whoami-v2",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:
            data = json.loads(response.read().decode("utf-8"))
        name = str(data.get("name") or data.get("fullname") or "").strip()
        return {"ok": True, "message": f"OK ({name})" if name else "OK"}
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            return {"ok": False, "message": "Invalid token (401 Unauthorized)."}
        return {"ok": False, "message": f"HTTP {exc.code}"}
    except Exception as exc:  # network errors, timeouts
        return {"ok": False, "message": str(exc) or type(exc).__name__}


@router.post("/hf-token/test", summary="校验 HuggingFace 令牌")
def test_hf_token(body: HfTokenTestRequest):
    """校验 HuggingFace 令牌（优先用请求内传入的，否则回退到已保存或环境变量中的令牌）。"""
    token = (body.hf_token or "").strip() or cache_manager._resolve_hf_token()
    result = _verify_hf_token(token)
    return {"ok": bool(result.get("ok")), "message": result.get("message", "")}


# ---------------------------------------------------------------------------
# LLM API key (DeepSeek) for transcript correction + translation scoring
# ---------------------------------------------------------------------------


@router.get("/llm-keys", summary="仲裁密钥状态")
def get_llm_keys():
    """返回各大模型服务商是否已配置 API 密钥（不返回密钥明文），以及已保存的 API 基地址覆盖值（未覆盖时为 null，使用官方地址）。"""
    providers = cache_manager.llm_key_providers()
    return {
        "ok": True,
        "providers": {p: cache_manager.llm_key_is_set(p) for p in providers},
        "base_urls": {p: cache_manager.read_llm_base_url(p) for p in providers},
    }


@router.post("/llm-keys", summary="保存仲裁密钥")
def save_llm_key(body: LlmKeyRequest):
    """保存指定服务商的 API 密钥和/或 API 基地址：仅提交的字段生效，值为空表示清除；服务商未知返回 400。"""
    if body.provider not in cache_manager.llm_key_providers():
        raise HTTPException(status_code=400, detail="unknown_provider")
    submitted = body.model_dump(exclude_unset=True)
    if "api_key" in submitted:
        cache_manager.set_llm_key(body.provider, body.api_key)
    if "base_url" in submitted:
        cache_manager.set_llm_base_url(body.provider, body.base_url)
    return {
        "ok": True,
        "provider": body.provider,
        "set": cache_manager.llm_key_is_set(body.provider),
        "base_url": cache_manager.read_llm_base_url(body.provider),
    }


@router.post("/llm-keys/test", summary="校验仲裁密钥")
def test_llm_key(body: LlmKeyTestRequest):
    """对指定服务商端点做一次轻量的鉴权/连通性校验（可传入未保存的密钥/基地址试连）；服务商未知返回 400。"""
    if body.provider not in cache_manager.llm_key_providers():
        raise HTTPException(status_code=400, detail="unknown_provider")
    from ...transcription.arbitration import test_provider

    key = (body.api_key or "").strip() or cache_manager.read_llm_key(body.provider)
    base_url = (body.base_url or "").strip() or cache_manager.read_llm_base_url(body.provider)
    result = test_provider(body.provider, api_key=key, base_url=base_url)
    return {
        "ok": bool(result.get("ok")),
        "provider": body.provider,
        "model": result.get("model", ""),
        "message": result.get("message", ""),
    }


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
