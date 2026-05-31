"""JSON and timestamp I/O helpers for translip.

Consolidates the JSON read/write and ISO-timestamp helpers that were
previously redefined across many stage modules with inconsistent atomicity.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional, Union

PathLike = Union[str, Path]


def read_json(path: PathLike) -> Any:
    """Read and parse a UTF-8 JSON file."""
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(
    payload: Any,
    path: PathLike,
    *,
    atomic: bool = True,
    indent: int = 2,
    ensure_ascii: bool = False,
    sort_keys: bool = False,
    default: Optional[Callable[[Any], Any]] = None,
    trailing_newline: bool = False,
) -> Path:
    """Serialize ``payload`` as JSON to ``path``.

    The parent directory is always created. When ``atomic`` is true the data is
    written to a temporary file in the same directory and then atomically moved
    into place via :func:`os.replace`. Pass ``trailing_newline=True`` to append a
    final newline (matching writers that historically did so).
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(
        payload,
        ensure_ascii=ensure_ascii,
        indent=indent,
        sort_keys=sort_keys,
        default=default,
    )
    if trailing_newline:
        text += "\n"
    if atomic:
        tmp = target.with_name(f"{target.name}.{os.getpid()}.tmp")
        try:
            with tmp.open("w", encoding="utf-8") as handle:
                handle.write(text)
            os.replace(tmp, target)
        finally:
            if tmp.exists():
                tmp.unlink()
    else:
        with target.open("w", encoding="utf-8") as handle:
            handle.write(text)
    return target


def now_iso() -> str:
    """Return the current local time as an ISO-8601 string (seconds precision).

    Format matches the historical ``pipeline.manifest.now_iso`` exactly so that
    emitted manifests remain byte-for-byte identical.
    """
    return datetime.now().astimezone().isoformat(timespec="seconds")


def append_jsonl(record: Any, path: PathLike, *, ensure_ascii: bool = False) -> Path:
    """Append a single JSON record as a line to a JSONL file."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=ensure_ascii))
        handle.write("\n")
    return target
