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


@dataclass(frozen=True)
class CacheGroup:
    key: str
    label: str
    group: Literal["model", "hub", "pipeline", "temp"]
    paths: PathsProvider
    removable: bool = True
    detection_extra: Callable[[Path, Path], bool] | None = None


def _huggingface_cache_root() -> Path:
    if cache_root := os.environ.get("HUGGINGFACE_HUB_CACHE"):
        return Path(cache_root)
    if cache_root := os.environ.get("HF_HUB_CACHE"):
        return Path(cache_root)
    hf_home = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
    return hf_home / "hub"


def _glob_dirs(root: Path, pattern: str) -> list[Path]:
    if not root.exists():
        return []
    return [p for p in root.glob(pattern) if p.is_dir()]


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
) -> list[dict[str, str]]:
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
        if group.key == "cdx23":
            available = _has_cdx23(paths)
        else:
            available = any(p.exists() for p in paths)
        results.append({"name": group.label, "status": "available" if available else "missing"})
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


__all__ = [
    "CachePathError",
    "CacheGroup",
    "CACHE_REGISTRY",
    "MigrateTask",
    "MigrationError",
    "MigrationManager",
    "apply_active_cache_root",
    "cleanup_group",
    "cleanup_groups",
    "collect_model_statuses",
    "compute_breakdown",
    "default_cache_root",
    "dir_size",
    "find_group",
    "get_user_config_path",
    "migration_manager",
    "read_user_setting",
    "reset_cache_dir_to_default",
    "resolve_active_cache_root",
    "set_cache_dir",
    "set_user_config_path",
    "update_user_setting",
]
