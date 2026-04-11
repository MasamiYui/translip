from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def slugify_filename(path: Path) -> str:
    cleaned = re.sub(r"[^\w.-]+", "_", path.stem.strip(), flags=re.UNICODE).strip("_")
    return cleaned or "media"


def bundle_directory(output_root: Path, input_path: Path) -> Path:
    return ensure_directory(output_root / slugify_filename(input_path))


def work_directory(output_root: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return ensure_directory(output_root / ".work" / f"job-{timestamp}")


def remove_tree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def copy_if_exists(src: Path, dst: Path) -> Path:
    ensure_directory(dst.parent)
    shutil.copy2(src, dst)
    return dst

