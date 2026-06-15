"""Stage invocation — shell out to the translip CLI / modules, parse key=val stdout.

This is the *only* runtime coupling to translip: the lab runs the same CLI the
orchestrator uses (``uv run translip <stage> …`` and ``uv run python -m
translip.ocr.extract …``) in isolated subprocesses and reads the ``key=value``
lines each stage prints (e.g. ``segments=/path``, ``manifest=/path``). The
``Invoker`` protocol lets tests inject a fake so the engine is exercised without
running any ML.
"""
from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from ..config import LabConfig, load_config


def parse_kv(stdout: str) -> dict[str, str]:
    """Extract ``key=value`` lines (translip's machine-readable stage output)."""
    out: dict[str, str] = {}
    for line in stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key and all(c.isalnum() or c in "_-" for c in key):
            out[key] = value.strip()
    return out


@dataclass(slots=True)
class StageResult:
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str
    duration_sec: float
    outputs: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def stderr_tail(self, n: int = 600) -> str:
        return self.stderr[-n:] if self.stderr else ""


@runtime_checkable
class Invoker(Protocol):
    def translip(self, subcommand: str, args: list[str], *, timeout: float | None = None,
                 log_path: Path | None = None) -> StageResult: ...

    def module(self, module: str, args: list[str], *, timeout: float | None = None,
               log_path: Path | None = None) -> StageResult: ...


class SubprocessInvoker:
    """Real invoker: runs the configured translip / python commands."""

    def __init__(self, config: LabConfig | None = None) -> None:
        self.config = config or load_config()

    def _run(self, cmd: list[str], timeout: float | None, log_path: Path | None) -> StageResult:
        start = time.time()
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            rc, so, se = proc.returncode, proc.stdout or "", proc.stderr or ""
        except subprocess.TimeoutExpired as exc:
            so = exc.stdout or ""
            se = (exc.stderr or "")
            if isinstance(so, bytes):
                so = so.decode("utf-8", "replace")
            if isinstance(se, bytes):
                se = se.decode("utf-8", "replace")
            se += f"\n[lab] timeout after {timeout}s"
            rc = 124
        duration = time.time() - start
        if log_path is not None:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(
                f"$ {' '.join(cmd)}\n\n[exit] {rc} in {duration:.1f}s\n\n[stdout]\n{so}\n\n[stderr]\n{se}\n",
                encoding="utf-8",
            )
        return StageResult(argv=list(cmd), returncode=rc, stdout=so, stderr=se,
                           duration_sec=duration, outputs=parse_kv(so))

    def translip(self, subcommand, args, *, timeout=None, log_path=None) -> StageResult:
        # top-level flags (--no-banner) must precede the subcommand for argparse.
        cmd = [*self.config.translip_cmd, "--no-banner", subcommand, *args]
        return self._run(cmd, timeout, log_path)

    def module(self, module, args, *, timeout=None, log_path=None) -> StageResult:
        cmd = [*self.config.python_cmd, "-m", module, *args]
        return self._run(cmd, timeout, log_path)
