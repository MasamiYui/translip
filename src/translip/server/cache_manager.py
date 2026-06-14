"""Cache directory management: registry, persistence, cleanup and migration."""
from __future__ import annotations

import json
import logging
import os
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Literal

from .. import config as translip_config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Persistent user settings (~/.config/translip/settings.json by default)
# ---------------------------------------------------------------------------

_DEFAULT_USER_CONFIG_PATH = Path.home() / ".config" / "translip" / "settings.json"
_USER_CONFIG_PATH: Path = Path(
    os.environ.get("TRANSLIP_USER_CONFIG", str(_DEFAULT_USER_CONFIG_PATH))
)
_USER_CONFIG_LOCK = threading.Lock()


def get_user_config_path() -> Path:
    return _USER_CONFIG_PATH


def set_user_config_path(path: Path) -> None:
    """Override the user-config path (primarily for tests)."""
    global _USER_CONFIG_PATH
    _USER_CONFIG_PATH = Path(path)


def _load_user_settings() -> dict[str, Any]:
    path = get_user_config_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("Failed to read user settings %s: %s", path, exc)
        return {}


def _save_user_settings(data: dict[str, Any]) -> None:
    path = get_user_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def update_user_setting(key: str, value: Any | None) -> None:
    with _USER_CONFIG_LOCK:
        data = _load_user_settings()
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
        _save_user_settings(data)


def read_user_setting(key: str) -> Any | None:
    with _USER_CONFIG_LOCK:
        return _load_user_settings().get(key)


# ---------------------------------------------------------------------------
# Active cache-root resolution
# ---------------------------------------------------------------------------

_DEFAULT_CACHE_ROOT = Path.home() / ".cache" / "translip"


def default_cache_root() -> Path:
    """Return the built-in default cache root."""
    return _DEFAULT_CACHE_ROOT


def resolve_active_cache_root() -> Path:
    """Resolve the currently active cache root.

    Priority: TRANSLIP_CACHE_DIR env > persisted user setting > default.
    """
    env = os.environ.get("TRANSLIP_CACHE_DIR")
    if env:
        return Path(env).expanduser()
    stored = read_user_setting("cache_dir")
    if stored:
        return Path(stored).expanduser()
    return default_cache_root()


def apply_active_cache_root() -> Path:
    """Sync the resolved cache root into translip_config.CACHE_ROOT."""
    root = resolve_active_cache_root()
    translip_config.CACHE_ROOT = root
    return root


# ---------------------------------------------------------------------------
# Cache registry — single source of truth for model/group paths
# ---------------------------------------------------------------------------


PathsProvider = Callable[[Path, Path], list[Path]]
TriStateProvider = Callable[[Path, Path], Literal["available", "missing", "needs_extra"]]


@dataclass(frozen=True)
class CacheGroup:
    key: str
    label: str
    group: Literal["model", "hub", "pipeline", "temp"]
    paths: PathsProvider
    removable: bool = True
    detection_extra: Callable[[Path, Path], bool] | None = None
    # Tri-state readiness for models whose availability depends on an optional
    # Python extra being installed (download alone can't make them usable).
    # When set it overrides ``detection_extra``/path-existence in both
    # ``collect_model_statuses`` and ``list_missing_model_keys``. ``needs_extra``
    # rows are surfaced as a hint and excluded from the one-click downloader.
    status_extra: TriStateProvider | None = None
    # Stable code (e.g. "ocr_extra_missing") the UI maps to a localized hint
    # when ``status_extra`` returns "needs_extra".
    needs_extra_detail: str | None = None


def _huggingface_cache_root() -> Path:
    if cache_root := os.environ.get("HUGGINGFACE_HUB_CACHE"):
        return Path(cache_root)
    if cache_root := os.environ.get("HF_HUB_CACHE"):
        return Path(cache_root)
    hf_home = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
    return hf_home / "hub"


def _modelscope_cache_root() -> Path:
    if cache_root := os.environ.get("MODELSCOPE_CACHE"):
        return Path(cache_root)
    return Path.home() / ".cache" / "modelscope" / "hub"


def _glob_dirs(root: Path, pattern: str) -> list[Path]:
    if not root.exists():
        return []
    return [p for p in root.glob(pattern) if p.is_dir()]


# Registry key for the in-tree PaddleOCR hard-subtitle weights.
_PADDLEOCR_KEY = "paddleocr_models"


def _paddleocr_extra_installed() -> bool:
    try:
        import paddleocr  # noqa: F401
    except Exception:
        return False
    return True


def _paddleocr_required_models() -> list[str]:
    """The PP-OCRv5 model names PaddleOCR needs locally, in sync with the
    downloader. The recognition model is the default (Chinese) one; the
    textline-orientation model is only required when angle-cls is enabled."""
    from translip.ocr.config import settings as ocr_settings

    required = [
        ocr_settings.PADDLEOCR_TEXT_DETECTION_MODEL_NAME,
        "PP-OCRv5_mobile_rec",  # default (Chinese) recognition model
    ]
    if ocr_settings.PADDLEOCR_USE_ANGLE_CLS:
        required.append(ocr_settings.PADDLEOCR_TEXTLINE_ORIENTATION_MODEL_NAME)
    return required


def _paddleocr_weights_present() -> bool:
    try:
        from translip.ocr.config import settings as ocr_settings
        from translip.ocr.utils.model_paths import resolve_model_dir

        for model_name in _paddleocr_required_models():
            if resolve_model_dir(
                model_name,
                base_dir=ocr_settings.PADDLEOCR_MODELS_BASE_DIR,
                layout=ocr_settings.PADDLEOCR_MODELS_LAYOUT,
                platform_tag=ocr_settings.PADDLEOCR_MODELS_PLATFORM_TAG,
            ) is None:
                return False
        return True
    except Exception:
        return False


def _paddleocr_status(cache_root: Path, hf_root: Path) -> Literal["available", "missing", "needs_extra"]:
    """Resolve PaddleOCR hard-subtitle OCR readiness into three states.

    - ``needs_extra``: the optional ``ocr`` extra isn't importable. The one-click
      downloader can't fix this (it fetches files, not pip packages), so the UI
      must surface it differently from a plain "missing weights" row.
    - ``available``: extra installed AND the local PP-OCRv5 weights resolve.
    - ``missing``: extra installed but weights absent — downloadable.

    Imports are lazy so the server never hard-depends on the heavy ``ocr`` extra.
    """
    if not _paddleocr_extra_installed():
        return "needs_extra"
    return "available" if _paddleocr_weights_present() else "missing"


def _paddleocr_ready(cache_root: Path, hf_root: Path) -> bool:
    """Backward-compatible ``detection_extra`` predicate (True only when fully
    usable: extra installed AND weights present)."""
    return _paddleocr_status(cache_root, hf_root) == "available"


def _paddleocr_download_specs() -> list[tuple[str, Path]]:
    """Return ``(hf_repo_id, target_dir)`` pairs for the PP-OCRv5 weights.

    Files are downloaded directly into the local ``paddleocr_models`` layout
    (``<base>/<runtime-tag>/<model-name>/``) so ``resolve_model_dir`` finds them
    under both the ``auto`` and ``platform`` layouts — NOT into the HF hub cache.
    The repo names mirror ``_paddleocr_required_models`` so download and readiness
    stay in lockstep.
    """
    from translip.ocr.config import settings as ocr_settings
    from translip.ocr.utils.model_paths import current_runtime_tag

    base = Path(ocr_settings.PADDLEOCR_MODELS_BASE_DIR).expanduser()
    platform_tag = ocr_settings.PADDLEOCR_MODELS_PLATFORM_TAG
    if not platform_tag or platform_tag.strip().lower() == "auto":
        platform_tag = current_runtime_tag()
    target_root = base / platform_tag
    specs: list[tuple[str, Path]] = []
    for model_name in _paddleocr_required_models():
        specs.append((f"PaddlePaddle/{model_name}", target_root / model_name))
    return specs


# Registry keys for the in-tree subtitle-erase and vision weights.
_ERASE_STTN_KEY = "erase_sttn"
_ERASE_LAMA_KEY = "erase_lama"
_VISION_MLX_KEY = "vision_qwen3vl_mlx"


def _module_available(name: str) -> bool:
    """True if ``name`` is importable, without importing it (find_spec only)."""
    try:
        import importlib.util

        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _erase_models_dir(cache_root: Path) -> Path:
    """Resolve the subtitle-erase weights dir WITHOUT importing erase.config.

    erase.config is pydantic-settings (the optional `erase` extra), so reading
    the env var directly keeps status detection working on a base install.
    Mirrors ``Settings.SUBTITLE_ERASE_MODELS_DIR`` (default ``<cache>/erase_models``).
    """
    env = os.environ.get("SUBTITLE_ERASE_MODELS_DIR")
    return Path(env).expanduser() if env else cache_root / "erase_models"


def _vision_settings():
    """Load the stdlib-only vision settings (safe without any extra)."""
    from translip.vision.config import load_settings

    return load_settings()


def _vision_mlx_paths(cache_root: Path) -> list[Path]:
    """HF snapshot dir(s) for the resolved mlx vision model under its own cache."""
    try:
        settings = _vision_settings()
    except Exception:
        return [cache_root / "vision_models" / "hf"]
    hf_cache = Path(settings.hf_cache).expanduser()
    repo_dir = "models--" + settings.model.replace("/", "--")
    return [*_glob_dirs(hf_cache, repo_dir), hf_cache / repo_dir]


def _vision_mlx_status(cache_root: Path, hf_root: Path) -> Literal["available", "missing", "needs_extra"]:
    """Tri-state readiness for the mlx Qwen3-VL weights.

    The mlx weights are only loadable with the optional ``vision`` extra
    (``mlx-vlm``); without it, downloading multiple GB can't make them usable
    (and on non-Apple hosts mlx-vlm can't even install). So gate on the extra
    exactly like PaddleOCR — ``needs_extra`` rather than a perpetual "missing".
    """
    if not _module_available("mlx_vlm"):
        return "needs_extra"
    for path in _vision_mlx_paths(cache_root):
        if path.is_dir() and any(path.iterdir()):
            return "available"
    return "missing"


CACHE_REGISTRY: list[CacheGroup] = [
    CacheGroup(
        key="cdx23",
        label="CDX23 weights",
        group="model",
        paths=lambda r, _h: [r / "models" / "cdx23", r / "models" / "CDX23"],
    ),
    CacheGroup(
        key="faster_whisper_small",
        label="faster-whisper small",
        group="model",
        paths=lambda r, h: [
            r / "models" / "faster_whisper" / "small",
            *_glob_dirs(h, "models--Systran--faster-whisper-small*"),
        ],
    ),
    CacheGroup(
        key="speechbrain_ecapa",
        label="SpeechBrain ECAPA",
        group="model",
        paths=lambda r, h: [
            r / "speechbrain" / "spkrec-ecapa-voxceleb",
            *_glob_dirs(h, "models--speechbrain--spkrec-ecapa-voxceleb*"),
        ],
    ),
    CacheGroup(
        key="m2m100_418m",
        label="M2M100 418M",
        group="model",
        paths=lambda r, h: [
            r / "transformers" / "models--facebook--m2m100_418M",
            r / "models" / "m2m100_418M",
            *_glob_dirs(h, "models--facebook--m2m100_418M*"),
        ],
    ),
    CacheGroup(
        key="moss_tts_nano_onnx",
        label="MOSS-TTS-Nano ONNX",
        group="model",
        paths=lambda r, h: [
            r / "models" / "MOSS-TTS-Nano-100M-ONNX",
            r / "models" / "MOSS-Audio-Tokenizer-Nano-ONNX",
            *_glob_dirs(h, "models--OpenMOSS-Team--MOSS-TTS-Nano-100M-ONNX*"),
            *_glob_dirs(h, "models--OpenMOSS-Team--MOSS-Audio-Tokenizer-Nano-ONNX*"),
        ],
    ),
    CacheGroup(
        key="qwen3tts",
        label="Qwen3TTS",
        group="model",
        paths=lambda r, h: [
            r / "models" / "qwen3tts",
            *_glob_dirs(h, "models--Qwen--Qwen3-TTS-*"),
        ],
    ),
    CacheGroup(
        key="pyannote_speaker_diarization_31",
        label="pyannote speaker-diarization 3.1",
        group="model",
        paths=lambda r, h: [
            r / "models" / "pyannote" / "speaker-diarization-3.1",
            *_glob_dirs(h, "models--pyannote--speaker-diarization-3.1*"),
        ],
    ),
    CacheGroup(
        key="pyannote_segmentation_30",
        label="pyannote segmentation 3.0",
        group="model",
        paths=lambda r, h: [
            r / "models" / "pyannote" / "segmentation-3.0",
            *_glob_dirs(h, "models--pyannote--segmentation-3.0*"),
        ],
    ),
    CacheGroup(
        key="funasr_sensevoice_small",
        label="FunASR SenseVoiceSmall",
        group="model",
        paths=lambda r, _h: [
            r / "models" / "funasr" / "SenseVoiceSmall",
            _modelscope_cache_root() / "iic" / "SenseVoiceSmall",
            _modelscope_cache_root() / "models" / "iic" / "SenseVoiceSmall",
        ],
    ),
    CacheGroup(
        key="funasr_fsmn_vad",
        label="FunASR FSMN-VAD",
        group="model",
        paths=lambda r, _h: [
            r / "models" / "funasr" / "speech_fsmn_vad_zh-cn-16k-common-pytorch",
            _modelscope_cache_root() / "iic" / "speech_fsmn_vad_zh-cn-16k-common-pytorch",
            _modelscope_cache_root() / "models" / "iic" / "speech_fsmn_vad_zh-cn-16k-common-pytorch",
        ],
    ),
    CacheGroup(
        key="funasr_ct_punc",
        label="FunASR CT-Punc",
        group="model",
        # Must stay in sync with the model FunASR's "ct-punc" alias resolves to
        # (see funasr_backend._load_punc_model). The alias maps to the cn-en
        # 471067-large model, NOT the zh-cn 272727 one; tracking the wrong id
        # makes the status show "downloaded" while a 1.1GB on-demand fetch still
        # blocks the first transcription run.
        paths=lambda r, _h: [
            r / "models" / "funasr" / "punc_ct-transformer_cn-en-common-vocab471067-large",
            _modelscope_cache_root() / "iic" / "punc_ct-transformer_cn-en-common-vocab471067-large",
            _modelscope_cache_root()
            / "models"
            / "iic"
            / "punc_ct-transformer_cn-en-common-vocab471067-large",
        ],
    ),
    CacheGroup(
        key="voxcpm2",
        label="VoxCPM2",
        group="model",
        paths=lambda r, h: [
            r / "models" / "VoxCPM2",
            *_glob_dirs(h, "models--openbmb--VoxCPM2*"),
            *_glob_dirs(h, "models--OpenBMB--VoxCPM2*"),
        ],
    ),
    CacheGroup(
        key="paddleocr_models",
        label="PaddleOCR (hard-subtitle OCR)",
        group="model",
        # Readiness needs the `ocr` extra installed too, so it's decided by a
        # tri-state status_extra rather than mere path existence. Not removable:
        # the weights aren't re-fetchable via the one-click downloader yet.
        paths=lambda r, _h: [r / "paddleocr_models"],
        removable=False,
        detection_extra=_paddleocr_ready,
        status_extra=_paddleocr_status,
        needs_extra_detail="ocr_extra_missing",
    ),
    CacheGroup(
        key=_ERASE_STTN_KEY,
        label="Subtitle-erase STTN",
        group="model",
        paths=lambda r, _h: [_erase_models_dir(r) / "sttn.pth"],
    ),
    CacheGroup(
        key=_ERASE_LAMA_KEY,
        label="Subtitle-erase LaMa",
        group="model",
        paths=lambda r, _h: [_erase_models_dir(r) / "big-lama.pt"],
    ),
    CacheGroup(
        key=_VISION_MLX_KEY,
        label="Qwen3-VL (mlx)",
        group="model",
        # Gated on the `vision` extra (mlx-vlm); see _vision_mlx_status.
        paths=lambda r, _h: _vision_mlx_paths(r),
        status_extra=_vision_mlx_status,
        needs_extra_detail="vision_extra_missing",
    ),
    CacheGroup(
        key="hf_hub",
        label="HuggingFace Hub",
        group="hub",
        paths=lambda _r, h: [h],
    ),
    CacheGroup(
        key="pipeline_outputs",
        label="Pipeline Outputs",
        group="pipeline",
        paths=lambda r, _h: [r / "output-pipeline"],
    ),
    CacheGroup(
        key="temp",
        label="Temporary / partial downloads",
        group="temp",
        paths=lambda r, _h: _collect_temp_files(r),
    ),
]


def _collect_temp_files(cache_root: Path) -> list[Path]:
    if not cache_root.exists():
        return []
    hf_root = _huggingface_cache_root()
    results: list[Path] = []
    for pattern in ("*.part", "*.tmp", "*.incomplete", "*.lock"):
        for p in cache_root.rglob(pattern):
            # Skip HF hub in-flight downloads to avoid breaking active
            # model fetches when the user triggers a cleanup.
            try:
                if hf_root in p.parents:
                    continue
            except Exception:
                pass
            results.append(p)
    return results


def find_group(key: str) -> CacheGroup | None:
    for item in CACHE_REGISTRY:
        if item.key == key:
            return item
    return None


# ---------------------------------------------------------------------------
# Size & breakdown helpers
# ---------------------------------------------------------------------------


def _path_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    total = 0
    for f in path.rglob("*"):
        if f.is_file():
            try:
                total += f.stat().st_size
            except OSError:
                pass
    return total


def dir_size(path: Path) -> int:
    return _path_size(path)


# ---------------------------------------------------------------------------
# Pipeline output GC (ARCH-7)
#
# `output-pipeline/<task_id>/` directories are only removed on an explicit task
# delete, so reruns and orphaned runs accumulate without bound. This adds an
# LRU/capacity GC that evicts *unreferenced* output dirs (no DB task points at
# them), oldest first, until under the configured byte/count limit. Directories
# still referenced by a DB task are never evicted.
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class PipelineOutputInfo:
    path: Path
    size_bytes: int
    mtime: float
    referenced: bool


def select_evictable_pipeline_outputs(
    infos: list[PipelineOutputInfo],
    *,
    max_bytes: int | None = None,
    max_count: int | None = None,
) -> list[PipelineOutputInfo]:
    """Pick unreferenced output dirs to evict (LRU first) until under the limits.

    Pure selection logic — no filesystem side effects, so it is unit-testable.
    Referenced directories are never candidates. Returns the dirs to delete.
    """
    total_bytes = sum(info.size_bytes for info in infos)
    total_count = len(infos)
    # Oldest unreferenced first (LRU eviction).
    candidates = sorted(
        (info for info in infos if not info.referenced),
        key=lambda info: info.mtime,
    )
    to_evict: list[PipelineOutputInfo] = []
    for candidate in candidates:
        over_bytes = max_bytes is not None and total_bytes > max_bytes
        over_count = max_count is not None and total_count > max_count
        if not (over_bytes or over_count):
            break
        to_evict.append(candidate)
        total_bytes -= candidate.size_bytes
        total_count -= 1
    return to_evict


def _referenced_output_roots(db_engine: Any | None) -> set[Path]:
    """Resolved per-task output_root paths still recorded in the DB."""
    from sqlmodel import Session, select

    from .database import engine as default_engine
    from .models import Task

    engine = db_engine or default_engine
    referenced: set[Path] = set()
    with Session(engine) as session:
        for raw in session.exec(select(Task.output_root)).all():
            if not raw:
                continue
            try:
                referenced.add(Path(str(raw)).expanduser().resolve())
            except Exception:
                continue
    return referenced


def gc_pipeline_outputs(
    *,
    max_bytes: int | None = None,
    max_count: int | None = None,
    dry_run: bool = False,
    cache_root: Path | None = None,
    db_engine: Any | None = None,
) -> dict[str, Any]:
    """Evict unreferenced pipeline output dirs by LRU until under the limits.

    Returns a report dict. With both limits None this is a no-op (returns the
    scan only), so it is safe to call unconditionally.
    """
    root = (cache_root or resolve_active_cache_root()) / "output-pipeline"
    if not root.exists():
        return {"scanned": 0, "referenced": 0, "evicted": [], "freed_bytes": 0, "dry_run": dry_run}

    referenced = _referenced_output_roots(db_engine)
    infos: list[PipelineOutputInfo] = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        try:
            resolved = child.resolve()
        except Exception:
            resolved = child
        try:
            mtime = child.stat().st_mtime
        except OSError:
            mtime = 0.0
        infos.append(
            PipelineOutputInfo(
                path=child,
                size_bytes=dir_size(child),
                mtime=mtime,
                referenced=resolved in referenced,
            )
        )

    evict = select_evictable_pipeline_outputs(infos, max_bytes=max_bytes, max_count=max_count)
    freed = 0
    evicted_paths: list[str] = []
    for info in evict:
        evicted_paths.append(str(info.path))
        freed += info.size_bytes
        if not dry_run:
            shutil.rmtree(info.path, ignore_errors=True)

    return {
        "scanned": len(infos),
        "referenced": sum(1 for info in infos if info.referenced),
        "evicted": evicted_paths,
        "freed_bytes": freed,
        "dry_run": dry_run,
    }


def _resolve_group_paths(group: CacheGroup, cache_root: Path, hf_root: Path) -> list[Path]:
    seen: set[Path] = set()
    resolved: list[Path] = []
    for path in group.paths(cache_root, hf_root):
        try:
            abs_path = path if path.is_absolute() else cache_root / path
        except Exception:
            abs_path = path
        if abs_path not in seen:
            seen.add(abs_path)
            resolved.append(abs_path)
    return resolved


def compute_breakdown(
    *,
    cache_root: Path | None = None,
    huggingface_cache_root: Path | None = None,
) -> dict[str, Any]:
    cache_root = cache_root or resolve_active_cache_root()
    hf_root = huggingface_cache_root or _huggingface_cache_root()

    items: list[dict[str, Any]] = []
    total = 0
    # First pass: collect per-group paths; remember HF sub-paths already
    # accounted for by specific model groups so the catch-all hf_hub bucket
    # does not double-count them.
    group_paths: dict[str, list[Path]] = {}
    claimed_hf_paths: set[Path] = set()
    for group in CACHE_REGISTRY:
        paths = _resolve_group_paths(group, cache_root, hf_root)
        group_paths[group.key] = paths
        if group.group == "model":
            for p in paths:
                try:
                    if hf_root in p.parents or p == hf_root:
                        claimed_hf_paths.add(p)
                except Exception:
                    pass

    for group in CACHE_REGISTRY:
        paths = group_paths[group.key]
        if group.key == "hf_hub":
            size = 0
            try:
                if hf_root.exists():
                    for child in hf_root.iterdir():
                        if child in claimed_hf_paths:
                            continue
                        size += _path_size(child)
            except OSError:
                size = 0
            existing = [str(hf_root)] if hf_root.exists() else []
        else:
            size = sum(_path_size(p) for p in paths)
            existing = [str(p) for p in paths if p.exists()]
        items.append(
            {
                "key": group.key,
                "label": group.label,
                "group": group.group,
                "bytes": size,
                "paths": existing,
                "removable": group.removable,
                "present": bool(existing),
            }
        )
        total += size

    return {
        "cache_dir": str(cache_root),
        "huggingface_hub_dir": str(hf_root),
        "total_bytes": total,
        "items": items,
    }


def collect_model_statuses(
    *,
    cache_root: Path | None = None,
    huggingface_cache_root: Path | None = None,
) -> list[dict[str, Any]]:
    """Backwards-compatible wrapper used by GET /api/system/info."""
    cache_root = cache_root or resolve_active_cache_root()
    hf_root = huggingface_cache_root or _huggingface_cache_root()

    def _has_cdx23(paths: list[Path]) -> bool:
        for p in paths:
            if p.is_file() and p.suffix == ".th":
                return True
            if p.is_dir() and any(p.glob("*.th")):
                return True
        return False

    results: list[dict[str, str]] = []
    for group in CACHE_REGISTRY:
        if group.group != "model":
            continue
        paths = _resolve_group_paths(group, cache_root, hf_root)
        entry: dict[str, str] = {
            "key": group.key,
            "name": group.label,
            "auto_downloadable": is_auto_downloadable(group.key),
        }
        # status_extra groups expose a third state ("needs_extra") that a
        # download can't fix; surface it (plus a stable detail code the UI
        # localizes) so the row is honest rather than perpetually "missing".
        if group.status_extra is not None:
            status = group.status_extra(cache_root, hf_root)
            entry["status"] = status
            if status == "needs_extra" and group.needs_extra_detail:
                entry["detail"] = group.needs_extra_detail
            results.append(entry)
            continue
        if group.detection_extra is not None:
            available = group.detection_extra(cache_root, hf_root)
        elif group.key == "cdx23":
            available = _has_cdx23(paths)
        else:
            available = any(p.exists() for p in paths)
        entry["status"] = "available" if available else "missing"
        results.append(entry)
    return results


# ---------------------------------------------------------------------------
# Safety guards
# ---------------------------------------------------------------------------

_FORBIDDEN_PREFIXES = (
    Path("/bin"),
    Path("/sbin"),
    Path("/etc"),
    Path("/usr"),
    Path("/opt"),
    Path("/srv"),
    Path("/var/db"),
    Path("/System"),
    Path("/Library"),
    Path("/boot"),
    # macOS resolves some of the above via /private. Block the resolved
    # locations as well to avoid symlink-based bypasses.
    Path("/private/etc"),
    Path("/private/var/root"),
    Path("/private/var/db"),
    Path("/private/sbin"),
)


class CachePathError(ValueError):
    """Raised when a target path is invalid or unsafe."""


def validate_target_path(target: Path, *, allow_existing_files: bool = False) -> Path:
    raw = str(target) if target is not None else ""
    # Treat "", ".", and whitespace-only as invalid to avoid silently resolving
    # to the current working directory.
    if raw in ("", ".") or not raw.strip() or raw.strip() == ".":
        raise CachePathError("target_empty")
    target = Path(target).expanduser().resolve()

    # Disallow filesystem root and the user's home directory root itself.
    if target == Path("/"):
        raise CachePathError("target_is_filesystem_root")
    if target == Path.home():
        raise CachePathError("target_is_home_root")

    target_str = str(target)
    for prefix in _FORBIDDEN_PREFIXES:
        prefix_str = str(prefix).rstrip("/")
        if target_str == prefix_str or target_str.startswith(prefix_str + "/"):
            raise CachePathError(f"target_in_forbidden_prefix:{prefix}")

    if target.exists() and target.is_file() and not allow_existing_files:
        raise CachePathError("target_is_existing_file")

    return target


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Cleanup operations
# ---------------------------------------------------------------------------


def _remove_path(path: Path) -> int:
    if not path.exists():
        return 0
    size = _path_size(path)
    if path.is_file() or path.is_symlink():
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("Failed to remove file %s: %s", path, exc)
            return 0
    else:
        shutil.rmtree(path, ignore_errors=True)
    return size


def cleanup_group(key: str, *, cache_root: Path | None = None, hf_root: Path | None = None) -> int:
    group = find_group(key)
    if group is None:
        raise CachePathError(f"unknown_group:{key}")
    if not group.removable:
        raise CachePathError(f"group_not_removable:{key}")

    cache_root = cache_root or resolve_active_cache_root()
    hf_root = hf_root or _huggingface_cache_root()
    freed = 0
    for path in _resolve_group_paths(group, cache_root, hf_root):
        freed += _remove_path(path)
    return freed


def cleanup_groups(keys: Iterable[str]) -> dict[str, Any]:
    details: list[dict[str, Any]] = []
    total_freed = 0
    # De-duplicate while preserving order.
    unique_keys: list[str] = list(dict.fromkeys(keys))
    for key in unique_keys:
        try:
            freed = cleanup_group(key)
        except CachePathError as exc:
            details.append({"key": key, "freed_bytes": 0, "error": str(exc)})
            continue
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Cleanup failed for %s", key)
            details.append({"key": key, "freed_bytes": 0, "error": repr(exc)})
            continue
        details.append({"key": key, "freed_bytes": freed})
        total_freed += freed
    return {"ok": True, "freed_bytes": total_freed, "details": details}


# ---------------------------------------------------------------------------
# Cache-directory switching
# ---------------------------------------------------------------------------


def set_cache_dir(target: str, *, create_if_missing: bool = True) -> Path:
    path = validate_target_path(Path(target))
    if create_if_missing:
        ensure_directory(path)
    elif not path.exists():
        raise CachePathError("target_missing")
    if path.exists() and not path.is_dir():
        raise CachePathError("target_not_directory")

    update_user_setting("cache_dir", str(path))
    apply_active_cache_root()
    return path


def reset_cache_dir_to_default() -> Path:
    update_user_setting("cache_dir", None)
    root = apply_active_cache_root()
    ensure_directory(root)
    return root


# ---------------------------------------------------------------------------
# Async migration tasks
# ---------------------------------------------------------------------------


@dataclass
class MigrateTask:
    task_id: str
    src: Path
    dst: Path
    mode: Literal["move", "copy"]
    switch_after: bool
    state: str = "pending"
    total_bytes: int = 0
    copied_bytes: int = 0
    current_file: str | None = None
    started_at: float | None = None
    finished_at: float | None = None
    error: str | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None

    def speed_bps(self) -> float:
        if not self.started_at or self.state not in {"running", "succeeded"}:
            return 0.0
        elapsed = max((self.finished_at or time.time()) - self.started_at, 1e-6)
        return self.copied_bytes / elapsed

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "state": self.state,
            "status": self.state,
            "src": str(self.src),
            "dst": str(self.dst),
            "mode": self.mode,
            "switch_after": self.switch_after,
            "progress": {
                "total_bytes": self.total_bytes,
                "copied_bytes": self.copied_bytes,
                "current_file": self.current_file,
                "speed_bps": self.speed_bps(),
            },
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


class MigrationError(RuntimeError):
    pass


class MigrationManager:
    def __init__(self) -> None:
        self._tasks: dict[str, MigrateTask] = {}
        self._lock = threading.Lock()
        self.chunk_size = 1024 * 1024  # 1 MiB

    def start(
        self,
        *,
        target: str,
        mode: Literal["move", "copy"] = "move",
        switch_after: bool = True,
        run_in_thread: bool = True,
        source: Path | None = None,
        allow_non_empty: bool = False,
    ) -> MigrateTask:
        src = (source or resolve_active_cache_root()).expanduser().resolve()
        if not src.exists():
            src.mkdir(parents=True, exist_ok=True)
        dst = validate_target_path(Path(target))
        if dst == src:
            raise CachePathError("target_equals_source")
        # Disallow nesting src inside dst or vice versa
        try:
            dst.relative_to(src)
            raise CachePathError("target_inside_source")
        except ValueError:
            pass
        try:
            src.relative_to(dst)
            raise CachePathError("source_inside_target")
        except ValueError:
            pass
        ensure_directory(dst)
        if not allow_non_empty:
            try:
                if any(dst.iterdir()):
                    raise CachePathError("target_not_empty")
            except OSError as exc:
                raise CachePathError(f"target_unreadable:{exc}") from exc

        self._gc_finished_tasks()
        task = MigrateTask(
            task_id=uuid.uuid4().hex,
            src=src,
            dst=dst,
            mode=mode,
            switch_after=switch_after,
        )
        with self._lock:
            self._tasks[task.task_id] = task
        if run_in_thread:
            t = threading.Thread(target=self._run, args=(task,), name=f"cache-migrate-{task.task_id}", daemon=True)
            task.thread = t
            t.start()
        else:
            self._run(task)
        return task

    # Keep at most N finished tasks in memory (LRU by finished_at).
    _TASK_HISTORY_LIMIT = 16

    def _gc_finished_tasks(self) -> None:
        with self._lock:
            finished = [
                (tid, t) for tid, t in self._tasks.items()
                if t.state in {"succeeded", "failed", "cancelled"} and t.finished_at
            ]
            if len(finished) <= self._TASK_HISTORY_LIMIT:
                return
            finished.sort(key=lambda kv: kv[1].finished_at or 0.0)
            to_drop = len(finished) - self._TASK_HISTORY_LIMIT
            for tid, _ in finished[:to_drop]:
                self._tasks.pop(tid, None)

    def get(self, task_id: str) -> MigrateTask | None:
        with self._lock:
            return self._tasks.get(task_id)

    def cancel(self, task_id: str) -> bool:
        task = self.get(task_id)
        if task is None:
            return False
        if task.state in {"succeeded", "failed", "cancelled"}:
            return False
        task.cancel_event.set()
        return True

    def list_tasks(self) -> list[MigrateTask]:
        with self._lock:
            return list(self._tasks.values())

    def reset(self) -> None:
        """Clear task history (primarily for tests)."""
        with self._lock:
            self._tasks.clear()

    # -- Internal ----------------------------------------------------------

    def _run(self, task: MigrateTask) -> None:
        task.state = "running"
        task.started_at = time.time()
        copied_files: list[Path] = []
        try:
            if not task.src.exists():
                task.total_bytes = 0
            else:
                task.total_bytes = _path_size(task.src)

            disk_free = shutil.disk_usage(task.dst.parent if task.dst.parent.exists() else task.dst).free
            # Reserve 5% headroom regardless of move/copy: cross-volume move
            # transparently degrades to copy+delete and still needs the full
            # extra space at the destination volume.
            required = int(task.total_bytes * 1.05)
            if required and disk_free < required:
                raise MigrationError(f"insufficient_space:{disk_free}<{required}")

            if task.src.exists():
                self._copy_tree(task, copied_files)

            if task.cancel_event.is_set():
                self._rollback(copied_files)
                task.state = "cancelled"
                return

            if task.mode == "move" and task.src.exists():
                shutil.rmtree(task.src, ignore_errors=True)

            if task.switch_after:
                update_user_setting("cache_dir", str(task.dst))
                apply_active_cache_root()

            task.state = "succeeded"
        except MigrationError as exc:
            task.state = "failed"
            task.error = str(exc)
            self._rollback(copied_files)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Migration task %s failed", task.task_id)
            task.state = "failed"
            task.error = repr(exc)
            self._rollback(copied_files)
        finally:
            task.finished_at = time.time()
            # Proactively GC finished history after each run to bound memory.
            self._gc_finished_tasks()

    def _copy_tree(self, task: MigrateTask, copied_files: list[Path]) -> None:
        for src_file in sorted(task.src.rglob("*")):
            if task.cancel_event.is_set():
                return
            rel = src_file.relative_to(task.src)
            target = task.dst / rel
            if src_file.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if src_file.is_symlink():
                target.parent.mkdir(parents=True, exist_ok=True)
                link_target = os.readlink(src_file)
                if target.exists() or target.is_symlink():
                    target.unlink()
                os.symlink(link_target, target)
                copied_files.append(target)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            task.current_file = str(rel)
            self._copy_file(src_file, target, task)
            copied_files.append(target)

    def _copy_file(self, src: Path, dst: Path, task: MigrateTask) -> None:
        chunk = self.chunk_size
        with src.open("rb") as fi, dst.open("wb") as fo:
            while True:
                if task.cancel_event.is_set():
                    return
                buf = fi.read(chunk)
                if not buf:
                    break
                fo.write(buf)
                task.copied_bytes += len(buf)
        shutil.copystat(src, dst, follow_symlinks=False)

    def _rollback(self, copied_files: list[Path]) -> None:
        for path in copied_files:
            try:
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    path.unlink(missing_ok=True)
            except OSError:
                pass


migration_manager = MigrationManager()


# ---------------------------------------------------------------------------
# Model download (HuggingFace snapshot) tasks
# ---------------------------------------------------------------------------


def _hf_snapshot_download(**kwargs: Any) -> Any:
    """Indirection for tests: defer import + allow monkeypatch."""
    from huggingface_hub import snapshot_download as _impl

    return _impl(**kwargs)


def _ms_snapshot_download(**kwargs: Any) -> Any:
    """Indirection for tests: defer import + raise a clear error if missing."""
    try:
        import modelscope.hub.snapshot_download as _ms_mod
    except ImportError as exc:  # pragma: no cover - depends on env
        raise RuntimeError(
            "modelscope_not_installed: please run "
            "`python -m pip install modelscope` and restart the server "
            f"(original error: {exc})"
        ) from exc
    return _ms_mod.snapshot_download(**kwargs)


# Map registry keys -> list of HF repo_ids that should be snapshot-downloaded.
# Models that cannot be auto-downloaded (e.g. CDX23 weights distributed
# manually) are intentionally absent from this map.
_MODEL_HF_REPOS: dict[str, list[str]] = {
    "faster_whisper_small": ["Systran/faster-whisper-small"],
    "speechbrain_ecapa": ["speechbrain/spkrec-ecapa-voxceleb"],
    "m2m100_418m": ["facebook/m2m100_418M"],
    "moss_tts_nano_onnx": [
        "OpenMOSS-Team/MOSS-TTS-Nano-100M-ONNX",
        "OpenMOSS-Team/MOSS-Audio-Tokenizer-Nano-ONNX",
    ],
    # NOTE: Qwen3-TTS-12Hz-0.6B-Base is publicly downloadable; the VoiceDesign
    # variant is gated and requires `huggingface-cli login`, so it's NOT pulled
    # automatically here to avoid spurious failures for users who only need the
    # default voice-clone path.
    "qwen3tts": [
        "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
    ],
    "voxcpm2": [
        "openbmb/VoxCPM2",
    ],
}

# Gated HuggingFace repos: only auto-downloadable when a HF token is detected
# in the environment. These models require the user to accept their model
# license on HuggingFace before downloading. We surface them to the
# "download missing" flow opportunistically rather than letting the job
# always fail with 401.
_MODEL_HF_REPOS_GATED: dict[str, list[str]] = {
    "pyannote_speaker_diarization_31": ["pyannote/speaker-diarization-3.1"],
    "pyannote_segmentation_30": ["pyannote/segmentation-3.0"],
}


# Map registry keys -> list of ModelScope model_ids. These are downloaded via
# `modelscope.hub.snapshot_download.snapshot_download` into
# `_modelscope_cache_root()` so that FunASR's `AutoModel(...)` finds them
# offline at runtime.
_MODEL_MS_REPOS: dict[str, list[str]] = {
    "funasr_sensevoice_small": ["iic/SenseVoiceSmall"],
    "funasr_fsmn_vad": ["iic/speech_fsmn_vad_zh-cn-16k-common-pytorch"],
    "funasr_ct_punc": ["iic/punc_ct-transformer_cn-en-common-vocab471067-large"],
}


# Custom (non-HF/non-ModelScope) downloaders. Each callback fetches the weights
# for one registry key into the active cache. Signature: (cancel_event,
# on_progress) -> None; raising marks the entry failed in the download job.
#  - erase weights: GitHub raw + sha256 via the in-tree, stdlib-only
#    erase.utils.weights.ensure_weight (importable without the `erase` extra).
#  - vision mlx weights: an HF snapshot into the vision module's OWN cache
#    (VISION_HF_CACHE), not the shared HF hub cache, so mlx-vlm loads them offline.
CustomDownloader = Callable[[threading.Event, Callable[[str], None]], None]


def _make_erase_downloader(weight_key: str) -> CustomDownloader:
    def _download(cancel_event: threading.Event, on_progress: Callable[[str], None]) -> None:
        from translip.erase.utils.weights import ensure_weight

        models_dir = _erase_models_dir(resolve_active_cache_root())
        ensure_weight(weight_key, models_dir=models_dir, local_only=False, on_progress=on_progress)

    return _download


def _download_vision_mlx(cancel_event: threading.Event, on_progress: Callable[[str], None]) -> None:
    settings = _vision_settings()
    on_progress(f"downloading {settings.model}")
    ensure_directory(Path(settings.hf_cache).expanduser())
    _hf_snapshot_download(
        repo_id=settings.model,
        cache_dir=str(Path(settings.hf_cache).expanduser()),
        local_files_only=False,
        resume_download=True,
    )


_MODEL_CUSTOM_DOWNLOADERS: dict[str, CustomDownloader] = {
    _ERASE_STTN_KEY: _make_erase_downloader("sttn"),
    _ERASE_LAMA_KEY: _make_erase_downloader("lama"),
    _VISION_MLX_KEY: _download_vision_mlx,
}


_HF_TOKEN_ENV_NAMES = ("HF_TOKEN", "HUGGINGFACE_HUB_TOKEN", "PYANNOTE_AUTH_TOKEN")


def _resolve_hf_token() -> str | None:
    """Best-effort HF token discovery.

    Priority: environment variables (mirroring pyannote_diarizer behaviour) >
    the token persisted via the settings UI (``read_user_setting("hf_token")``).
    """
    for env_name in _HF_TOKEN_ENV_NAMES:
        token = os.environ.get(env_name)
        if token:
            return token
    stored = read_user_setting("hf_token")
    if stored:
        return str(stored)
    return None


def apply_hf_token_to_env() -> None:
    """Inject the persisted HF token into the process environment if unset.

    pyannote diarization runs in an isolated subprocess that only reads the HF
    token from ``os.environ``. Calling this at server startup lets a token saved
    through the settings UI propagate to those subprocesses (which inherit the
    server environment) without coupling the transcription layer to the server.
    No-op when any HF token env var is already present.
    """
    if any(os.environ.get(name) for name in _HF_TOKEN_ENV_NAMES):
        return
    stored = read_user_setting("hf_token")
    if stored:
        os.environ["HF_TOKEN"] = str(stored)


# ---------------------------------------------------------------------------
# LLM API key (DeepSeek), used by transcript-correction arbitration, the
# DeepSeek translation backend, and the translation quality judge. Like the HF
# token, those steps read the key from os.environ (subprocesses, plus the
# in-process judge), so persisted keys must be bridged into the environment
# (at startup and immediately on save).
# ---------------------------------------------------------------------------

# provider id -> (user-setting key, environment variable name)
_LLM_KEY_PROVIDERS: dict[str, tuple[str, str]] = {
    "deepseek": ("deepseek_api_key", "DEEPSEEK_API_KEY"),
}

# provider id -> (user-setting key, environment variable name) for the optional
# API base URL (account-level, e.g. an OpenAI-compatible proxy). Stored next to
# the key and bridged into the environment the same way, so every consumer
# (translation backend, arbitration, judge — in-process or subprocess) resolves
# it via the env var without plumbing it through per-task config.
_LLM_BASE_URL_PROVIDERS: dict[str, tuple[str, str]] = {
    "deepseek": ("deepseek_base_url", "DEEPSEEK_BASE_URL"),
}


def llm_key_providers() -> tuple[str, ...]:
    """Return the provider ids that support a configurable API key."""
    return tuple(_LLM_KEY_PROVIDERS.keys())


def llm_key_is_set(provider: str) -> bool:
    """True if a key is available for ``provider`` (env var or persisted setting)."""
    spec = _LLM_KEY_PROVIDERS.get(provider)
    if spec is None:
        return False
    setting_key, env_name = spec
    return bool(os.environ.get(env_name) or read_user_setting(setting_key))


def read_llm_key(provider: str) -> str | None:
    """Return the effective API key for ``provider`` (env var wins over setting).

    Internal helper — never expose the value through a GET route; the UI only
    learns whether a key is set via :func:`llm_key_is_set`.
    """
    spec = _LLM_KEY_PROVIDERS.get(provider)
    if spec is None:
        return None
    setting_key, env_name = spec
    from_env = os.environ.get(env_name)
    if from_env:
        return from_env
    stored = read_user_setting(setting_key)
    return str(stored) if stored else None


def set_llm_key(provider: str, value: str | None) -> None:
    """Persist (or clear, when empty) the API key for ``provider``.

    Also reflects the change in this process's environment so newly spawned
    task subprocesses pick it up without a server restart. On clear, only a
    value we previously bridged is removed — a key the operator exported into
    the environment themselves is left untouched.
    """
    spec = _LLM_KEY_PROVIDERS.get(provider)
    if spec is None:
        raise KeyError(provider)
    setting_key, env_name = spec
    prev = read_user_setting(setting_key)
    cleaned = (value or "").strip() or None
    update_user_setting(setting_key, cleaned)
    if cleaned:
        os.environ[env_name] = cleaned
    elif prev is not None and os.environ.get(env_name) == str(prev):
        os.environ.pop(env_name, None)


def read_llm_base_url(provider: str) -> str | None:
    """Return the saved API base URL override for ``provider``, if any.

    Unlike the key, the saved value (not the env var) is what the UI shows and
    edits; the env var is just the delivery mechanism to consumers.
    """
    spec = _LLM_BASE_URL_PROVIDERS.get(provider)
    if spec is None:
        return None
    stored = read_user_setting(spec[0])
    return str(stored) if stored else None


def set_llm_base_url(provider: str, value: str | None) -> None:
    """Persist (or clear, when empty) the API base URL override for ``provider``.

    Mirrors :func:`set_llm_key`: the change is reflected in this process's
    environment immediately, and on clear only a value we bridged ourselves is
    removed — an operator-exported env var is left untouched.
    """
    spec = _LLM_BASE_URL_PROVIDERS.get(provider)
    if spec is None:
        raise KeyError(provider)
    setting_key, env_name = spec
    prev = read_user_setting(setting_key)
    cleaned = (value or "").strip().rstrip("/") or None
    update_user_setting(setting_key, cleaned)
    if cleaned:
        os.environ[env_name] = cleaned
    elif prev is not None and os.environ.get(env_name) == str(prev):
        os.environ.pop(env_name, None)


def apply_llm_keys_to_env() -> None:
    """Bridge persisted LLM API keys and base URLs into ``os.environ`` if unset.

    Mirrors :func:`apply_hf_token_to_env`: the subprocesses (and in-process
    judge) read ``DEEPSEEK_API_KEY`` / ``DEEPSEEK_BASE_URL`` only from the
    environment. No-op for any entry whose env var is already present.
    """
    for setting_key, env_name in (*_LLM_KEY_PROVIDERS.values(), *_LLM_BASE_URL_PROVIDERS.values()):
        if os.environ.get(env_name):
            continue
        stored = read_user_setting(setting_key)
        if stored:
            os.environ[env_name] = str(stored)


def _auto_downloadable_keys() -> set[str]:
    """Return the set of registry keys eligible for the one-click downloader."""
    keys = set(_MODEL_HF_REPOS.keys()) | set(_MODEL_MS_REPOS.keys())
    # PaddleOCR weights are public (Apache-2.0) and fetched into a custom local
    # layout rather than the HF hub cache; see _paddleocr_download_specs.
    keys.add(_PADDLEOCR_KEY)
    # erase (GitHub+sha256) and vision-mlx (HF→own cache) use custom downloaders.
    keys |= set(_MODEL_CUSTOM_DOWNLOADERS.keys())
    if _resolve_hf_token():
        keys |= set(_MODEL_HF_REPOS_GATED.keys())
    return keys


def is_auto_downloadable(key: str) -> bool:
    return key in _auto_downloadable_keys()


def downloadable_model_keys() -> tuple[str, ...]:
    return tuple(sorted(_auto_downloadable_keys()))


def list_missing_model_keys(
    *,
    cache_root: Path | None = None,
    huggingface_cache_root: Path | None = None,
) -> list[str]:
    """Return registry keys for model groups whose weights are not yet present."""
    cache_root = cache_root or resolve_active_cache_root()
    hf_root = huggingface_cache_root or _huggingface_cache_root()

    def _has_cdx23(paths: list[Path]) -> bool:
        for p in paths:
            if p.is_file() and p.suffix == ".th":
                return True
            if p.is_dir() and any(p.glob("*.th")):
                return True
        return False

    missing: list[str] = []
    for group in CACHE_REGISTRY:
        if group.group != "model":
            continue
        paths = _resolve_group_paths(group, cache_root, hf_root)
        # This list drives the one-click downloader, so a group counts as
        # "missing" only when downloading can actually fix it. PaddleOCR is the
        # special case: when the `ocr` extra is absent (needs_extra) the
        # downloader can't help, so it's deliberately NOT listed here (the status
        # panel surfaces that state via collect_model_statuses instead).
        if group.status_extra is not None:
            # needs_extra / available both count as "not downloadable-missing":
            # the one-click downloader can only resolve a plain "missing".
            present = group.status_extra(cache_root, hf_root) != "missing"
        elif group.detection_extra is not None:
            present = group.detection_extra(cache_root, hf_root)
        elif group.key == "cdx23":
            present = _has_cdx23(paths)
        else:
            present = any(p.exists() for p in paths)
        if not present:
            missing.append(group.key)
    return missing


@dataclass
class ModelDownloadEntry:
    key: str
    label: str
    state: str = "pending"  # pending | running | succeeded | failed | skipped
    error: str | None = None
    started_at: float | None = None
    finished_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "state": self.state,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


@dataclass
class ModelDownloadJob:
    job_id: str
    keys: list[str]
    items: dict[str, ModelDownloadEntry] = field(default_factory=dict)
    state: str = "pending"  # pending | running | succeeded | partial | failed | cancelled
    started_at: float | None = None
    finished_at: float | None = None
    current_key: str | None = None
    error: str | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None

    def to_dict(self) -> dict[str, Any]:
        items = [self.items[k].to_dict() for k in self.keys if k in self.items]
        succeeded = sum(1 for it in items if it["state"] == "succeeded")
        failed = sum(1 for it in items if it["state"] == "failed")
        skipped = sum(1 for it in items if it["state"] == "skipped")
        total = len(items)
        return {
            "job_id": self.job_id,
            "state": self.state,
            "status": self.state,
            "current_key": self.current_key,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "items": items,
            "summary": {
                "total": total,
                "succeeded": succeeded,
                "failed": failed,
                "skipped": skipped,
            },
        }


class ModelDownloadError(RuntimeError):
    pass


class ModelDownloadManager:
    """Manage background HuggingFace snapshot downloads for missing models."""

    _JOB_HISTORY_LIMIT = 8

    def __init__(self) -> None:
        self._jobs: dict[str, ModelDownloadJob] = {}
        self._lock = threading.Lock()
        self._active_job_id: str | None = None

    def reset(self) -> None:
        with self._lock:
            self._jobs.clear()
            self._active_job_id = None

    def get(self, job_id: str) -> ModelDownloadJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self) -> list[ModelDownloadJob]:
        with self._lock:
            return list(self._jobs.values())

    def cancel(self, job_id: str) -> bool:
        job = self.get(job_id)
        if job is None:
            return False
        if job.state in {"succeeded", "partial", "failed", "cancelled"}:
            return False
        job.cancel_event.set()
        return True

    def start_missing(
        self,
        *,
        run_in_thread: bool = True,
        only_keys: list[str] | None = None,
    ) -> ModelDownloadJob:
        eligible = _auto_downloadable_keys()
        if only_keys:
            requested = [k for k in only_keys if k in eligible]
            unknown = [k for k in only_keys if k not in eligible]
            if unknown:
                raise ModelDownloadError(f"unsupported_keys:{','.join(unknown)}")
            missing_keys = requested
        else:
            all_missing = list_missing_model_keys()
            missing_keys = [k for k in all_missing if k in eligible]

        with self._lock:
            if self._active_job_id and self._jobs[self._active_job_id].state in {
                "pending",
                "running",
            }:
                raise ModelDownloadError("another_job_running")
            self._gc_finished_jobs_locked()

        job = ModelDownloadJob(job_id=uuid.uuid4().hex, keys=list(missing_keys))
        for key in missing_keys:
            group = find_group(key)
            label = group.label if group else key
            job.items[key] = ModelDownloadEntry(key=key, label=label)
        with self._lock:
            self._jobs[job.job_id] = job
            self._active_job_id = job.job_id
        if not missing_keys:
            job.state = "succeeded"
            job.started_at = time.time()
            job.finished_at = job.started_at
            with self._lock:
                self._active_job_id = None
            return job
        if run_in_thread:
            t = threading.Thread(
                target=self._run,
                args=(job,),
                name=f"model-download-{job.job_id}",
                daemon=True,
            )
            job.thread = t
            t.start()
        else:
            self._run(job)
        return job

    def _gc_finished_jobs_locked(self) -> None:
        finished = [
            (jid, j) for jid, j in self._jobs.items()
            if j.state in {"succeeded", "partial", "failed", "cancelled"} and j.finished_at
        ]
        if len(finished) <= self._JOB_HISTORY_LIMIT:
            return
        finished.sort(key=lambda kv: kv[1].finished_at or 0.0)
        to_drop = len(finished) - self._JOB_HISTORY_LIMIT
        for jid, _ in finished[:to_drop]:
            self._jobs.pop(jid, None)

    def _run(self, job: ModelDownloadJob) -> None:
        from huggingface_hub.utils import HfHubHTTPError

        job.state = "running"
        job.started_at = time.time()
        cache_root = resolve_active_cache_root()
        hf_root = _huggingface_cache_root()
        ms_root = _modelscope_cache_root()
        ensure_directory(cache_root)
        ensure_directory(hf_root)
        hf_token = _resolve_hf_token()
        gated_repo_ids = {
            r for repos in _MODEL_HF_REPOS_GATED.values() for r in repos
        }
        try:
            for key in job.keys:
                if job.cancel_event.is_set():
                    break
                entry = job.items[key]
                job.current_key = key
                entry.state = "running"
                entry.started_at = time.time()
                hf_repos = _MODEL_HF_REPOS.get(key, []) + _MODEL_HF_REPOS_GATED.get(key, [])
                ms_repos = _MODEL_MS_REPOS.get(key, [])
                # PaddleOCR weights download into a custom local layout, not the
                # HF hub cache; resolve their (repo_id, target_dir) specs here.
                local_dir_specs = _paddleocr_download_specs() if key == _PADDLEOCR_KEY else []
                custom_downloader = _MODEL_CUSTOM_DOWNLOADERS.get(key)
                if not hf_repos and not ms_repos and not local_dir_specs and not custom_downloader:
                    entry.state = "skipped"
                    entry.error = "no_auto_download_source"
                    entry.finished_at = time.time()
                    continue
                try:
                    for repo_id in hf_repos:
                        if job.cancel_event.is_set():
                            break
                        kwargs: dict[str, Any] = {
                            "repo_id": repo_id,
                            "cache_dir": str(hf_root),
                            "local_files_only": False,
                            "resume_download": True,
                        }
                        if repo_id in gated_repo_ids and hf_token:
                            kwargs["token"] = hf_token
                        _hf_snapshot_download(**kwargs)
                    for repo_id, target_dir in local_dir_specs:
                        if job.cancel_event.is_set():
                            break
                        ensure_directory(target_dir)
                        _hf_snapshot_download(
                            repo_id=repo_id,
                            local_dir=str(target_dir),
                            local_files_only=False,
                        )
                    if ms_repos:
                        ensure_directory(ms_root)
                    for model_id in ms_repos:
                        if job.cancel_event.is_set():
                            break
                        _ms_snapshot_download(
                            model_id=model_id,
                            cache_dir=str(ms_root),
                        )
                    if custom_downloader and not job.cancel_event.is_set():
                        custom_downloader(job.cancel_event, lambda _msg: None)
                    if job.cancel_event.is_set():
                        entry.state = "failed"
                        entry.error = "cancelled"
                    else:
                        entry.state = "succeeded"
                except HfHubHTTPError as exc:  # network / 4xx / 5xx
                    entry.state = "failed"
                    entry.error = f"hf_http_error:{exc}"[:500]
                except Exception as exc:  # pragma: no cover - defensive
                    logger.exception("Download failed for %s", key)
                    entry.state = "failed"
                    entry.error = repr(exc)[:500]
                finally:
                    entry.finished_at = time.time()
            # Finalise overall state
            if job.cancel_event.is_set():
                job.state = "cancelled"
            else:
                states = {it.state for it in job.items.values()}
                if states == {"succeeded"}:
                    job.state = "succeeded"
                elif "succeeded" in states and "failed" in states:
                    job.state = "partial"
                elif "succeeded" in states and "skipped" in states and "failed" not in states:
                    job.state = "partial"
                elif "succeeded" in states:
                    job.state = "succeeded"
                else:
                    job.state = "failed"
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Download job %s failed", job.job_id)
            job.state = "failed"
            job.error = repr(exc)[:500]
        finally:
            job.finished_at = time.time()
            job.current_key = None
            with self._lock:
                if self._active_job_id == job.job_id:
                    self._active_job_id = None
                self._gc_finished_jobs_locked()


model_download_manager = ModelDownloadManager()


__all__ = [
    "CachePathError",
    "CacheGroup",
    "CACHE_REGISTRY",
    "MigrateTask",
    "MigrationError",
    "MigrationManager",
    "ModelDownloadError",
    "ModelDownloadJob",
    "ModelDownloadManager",
    "apply_active_cache_root",
    "apply_hf_token_to_env",
    "cleanup_group",
    "cleanup_groups",
    "collect_model_statuses",
    "compute_breakdown",
    "default_cache_root",
    "dir_size",
    "downloadable_model_keys",
    "find_group",
    "get_user_config_path",
    "is_auto_downloadable",
    "list_missing_model_keys",
    "migration_manager",
    "model_download_manager",
    "read_user_setting",
    "reset_cache_dir_to_default",
    "resolve_active_cache_root",
    "set_cache_dir",
    "set_user_config_path",
    "update_user_setting",
]
