from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..utils.io import write_json as _write_json_impl


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().replace(microsecond=0).isoformat()


def write_json(payload: dict[str, Any], output_path: Path) -> Path:
    return _write_json_impl(payload, output_path, atomic=False, trailing_newline=True)


__all__ = ["now_iso", "write_json"]
