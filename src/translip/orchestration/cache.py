from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class StageCacheSpec:
    stage_name: str
    manifest_path: Path
    artifact_paths: list[Path]
    cache_key: str
    previous_cache_key: str | None = None


def compute_cache_key(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def is_stage_cache_hit(spec: StageCacheSpec) -> bool:
    if not spec.manifest_path.exists():
        return False
    if not all(path.exists() for path in spec.artifact_paths):
        return False
    payload = json.loads(spec.manifest_path.read_text(encoding="utf-8"))
    if payload.get("status") != "succeeded":
        return False
    if spec.previous_cache_key is None:
        return True
    return spec.previous_cache_key == spec.cache_key


__all__ = ["StageCacheSpec", "compute_cache_key", "is_stage_cache_hit"]
