from __future__ import annotations

import os
import subprocess
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..utils.files import ensure_directory


class StageSubprocessError(RuntimeError):
    def __init__(self, *, command: list[str], returncode: int, log_path: Path, tail: list[str]) -> None:
        self.command = command
        self.returncode = returncode
        self.log_path = log_path
        self.tail = tail
        super().__init__(
            f"Stage command failed with exit code {returncode}: {' '.join(command)}"
        )


def _default_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault("HF_HUB_DISABLE_XET", "1")
    env.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "0")
    return env


def _iter_stdout_segments(stream):
    buffer: list[str] = []
    while True:
        ch = stream.read(1)
        if not ch:
            if buffer:
                yield "".join(buffer)
            return
        buffer.append(ch)
        if ch == "\n" or ch == "\r":
            yield "".join(buffer)
            buffer = []


def run_stage_command(
    command: list[str],
    *,
    log_path: Path,
    env_overrides: dict[str, str] | None = None,
    on_stdout_line: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    ensure_directory(log_path.parent)
    outputs: dict[str, str] = {}
    tail: deque[str] = deque(maxlen=20)
    env = _default_env()
    if env_overrides:
        env.update(env_overrides)
    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            env=env,
        )
        assert process.stdout is not None
        for segment in _iter_stdout_segments(process.stdout):
            log_file.write(segment)
            log_file.flush()
            stripped = segment.strip()
            if not stripped:
                continue
            tail.append(stripped)
            if "=" in stripped and not stripped.startswith("["):
                key, value = stripped.split("=", 1)
                outputs[key] = value
            if on_stdout_line is not None:
                try:
                    on_stdout_line(stripped)
                except Exception:
                    pass
        returncode = process.wait()
    if returncode != 0:
        raise StageSubprocessError(
            command=command,
            returncode=returncode,
            log_path=log_path,
            tail=list(tail),
        )
    return {
        "command": command,
        "log_path": log_path,
        "outputs": outputs,
        "tail": list(tail),
    }


__all__ = ["StageSubprocessError", "run_stage_command"]
