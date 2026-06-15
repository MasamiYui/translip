"""Lab configuration — paths and the translip invocation command, from env.

Stdlib only (mirrors translip's own ``vision/config.py`` philosophy): the lab
must import cleanly without any optional extra. Datasets and run artifacts live
on the external disk by default (``/Volumes/EXT/translip-lab``) so multi-GB
corpora and outputs stay off the internal SSD.

Env overrides (all optional):
  TRANSLIP_LAB_HOME          base dir            (default /Volumes/EXT/translip-lab)
  TRANSLIP_LAB_DATASETS_DIR  datasets root       (default <home>/datasets)
  TRANSLIP_LAB_RUNS_DIR      run outputs         (default <home>/runs)
  TRANSLIP_LAB_CACHE_DIR     scratch/synthetic   (default <home>/cache)
  TRANSLIP_LAB_TRANSLIP_CMD  how to call the CLI (default "uv run translip")
  TRANSLIP_LAB_PYTHON_CMD    how to call python  (default "uv run python")
"""
from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
from pathlib import Path

_DEFAULT_HOME = "/Volumes/EXT/translip-lab"


@dataclass(frozen=True, slots=True)
class LabConfig:
    home: Path
    datasets_dir: Path
    runs_dir: Path
    cache_dir: Path
    translip_cmd: tuple[str, ...]
    python_cmd: tuple[str, ...]

    def ensure_dirs(self) -> "LabConfig":
        """Create the runs/cache dirs (datasets are user-provided, left alone)."""
        for d in (self.runs_dir, self.cache_dir):
            d.mkdir(parents=True, exist_ok=True)
        return self


def _env_path(key: str, default: Path) -> Path:
    raw = os.environ.get(key)
    return Path(raw).expanduser() if raw else default


def load_config() -> LabConfig:
    """Re-read the environment on every call (no module-level caching)."""
    home = Path(os.environ.get("TRANSLIP_LAB_HOME", _DEFAULT_HOME)).expanduser()
    return LabConfig(
        home=home,
        datasets_dir=_env_path("TRANSLIP_LAB_DATASETS_DIR", home / "datasets"),
        runs_dir=_env_path("TRANSLIP_LAB_RUNS_DIR", home / "runs"),
        cache_dir=_env_path("TRANSLIP_LAB_CACHE_DIR", home / "cache"),
        translip_cmd=tuple(shlex.split(os.environ.get("TRANSLIP_LAB_TRANSLIP_CMD", "uv run translip"))),
        python_cmd=tuple(shlex.split(os.environ.get("TRANSLIP_LAB_PYTHON_CMD", "uv run python"))),
    )
