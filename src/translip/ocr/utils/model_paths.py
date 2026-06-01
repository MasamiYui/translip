"""Helpers for resolving prebundled PaddleOCR model directories."""

from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import Iterable, Optional


# src/translip/ocr/utils/model_paths.py -> parents[4] is the repo root.
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_MODEL_CONFIG_FILES = ("inference.yml", "inference.json", "config.json")


def project_root() -> Path:
    return _PROJECT_ROOT


def default_models_base_dir() -> Path:
    return project_root() / "paddleocr_models"


def normalize_runtime_tag(system: str, machine: str) -> str:
    system_key = (system or "").strip().lower()
    arch_key = (machine or "").strip().lower()

    if system_key == "darwin":
        system_key = "macos"
    elif system_key.startswith("linux"):
        system_key = "linux"

    arch_aliases = {
        "x86_64": "x86_64",
        "amd64": "x86_64",
        "arm64": "arm64",
        "aarch64": "arm64",
    }
    arch_key = arch_aliases.get(arch_key, arch_key)
    return f"{system_key}-{arch_key}" if system_key and arch_key else "unknown"


def current_runtime_tag() -> str:
    return normalize_runtime_tag(platform.system(), platform.machine())


def current_runtime_supported() -> bool:
    return current_runtime_tag() in {"linux-x86_64", "linux-arm64", "macos-arm64"}


def _expand_base_dir(base_dir: Optional[str | os.PathLike[str]]) -> Path:
    if base_dir:
        return Path(base_dir).expanduser().resolve()
    env_dir = (os.environ.get("PADDLEOCR_MODELS_BASE_DIR") or "").strip()
    if env_dir:
        return Path(env_dir).expanduser().resolve()
    return default_models_base_dir().resolve()


def _resolve_layout(layout: Optional[str]) -> str:
    value = (layout or os.environ.get("PADDLEOCR_MODELS_LAYOUT") or "auto").strip().lower()
    if value not in {"auto", "platform", "shared"}:
        return "auto"
    return value


def _resolve_platform_tag(platform_tag: Optional[str]) -> str:
    value = (platform_tag or os.environ.get("PADDLEOCR_MODELS_PLATFORM_TAG") or "auto").strip().lower()
    if not value or value == "auto":
        return current_runtime_tag()
    return value


def iter_candidate_model_roots(
    base_dir: Optional[str | os.PathLike[str]] = None,
    layout: Optional[str] = None,
    platform_tag: Optional[str] = None,
) -> Iterable[Path]:
    base = _expand_base_dir(base_dir)
    resolved_layout = _resolve_layout(layout)
    resolved_tag = _resolve_platform_tag(platform_tag)

    candidates: list[Path] = []
    if resolved_layout == "platform":
        candidates.extend([base / resolved_tag, base])
    elif resolved_layout == "shared":
        candidates.extend([base / "shared", base])
    else:
        candidates.extend([base / resolved_tag, base / "shared", base])

    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        yield resolved


def looks_like_model_dir(path: Optional[str | os.PathLike[str]]) -> bool:
    if path is None:
        return False
    model_dir = Path(path)
    if not model_dir.is_dir():
        return False
    return any((model_dir / name).exists() for name in _MODEL_CONFIG_FILES)


def resolve_model_dir(
    model_name: str,
    *,
    base_dir: Optional[str | os.PathLike[str]] = None,
    layout: Optional[str] = None,
    platform_tag: Optional[str] = None,
) -> Optional[Path]:
    for root in iter_candidate_model_roots(base_dir=base_dir, layout=layout, platform_tag=platform_tag):
        candidate = root / model_name
        if looks_like_model_dir(candidate):
            return candidate
    return None
