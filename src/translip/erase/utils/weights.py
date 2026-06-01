"""Resolve / fetch the neural inpainting model weights to a local cache.

Weights are not vendored in the repo (they are ~63-196 MB). On first use they
are downloaded from the upstream video-subtitle-remover git tree (Apache-2.0)
over GitHub raw and verified by sha256, then cached under
``SUBTITLE_ERASE_MODELS_DIR`` (default ``<TRANSLIP_CACHE_DIR>/erase_models``).
Subsequent runs are an offline cache hit. Set ``SUBTITLE_ERASE_LOCAL_MODELS_ONLY``
to forbid downloads (then the file must already be present).

The big-LaMa weight is committed upstream as five 50 MB shards; we stream and
concatenate them in order, then verify the merged sha256 — equivalent to the
upstream ``filesplit`` merge but with no extra dependency.
"""
from __future__ import annotations

import hashlib
import shutil
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

_RAW = "https://raw.githubusercontent.com/YaoFANGUK/video-subtitle-remover/main/backend/models"


@dataclass(frozen=True, slots=True)
class WeightSpec:
    key: str
    filename: str
    sha256: str
    size: int
    parts: tuple[str, ...]  # one or more URLs concatenated in order


WEIGHTS: dict[str, WeightSpec] = {
    "sttn": WeightSpec(
        key="sttn",
        filename="sttn.pth",
        sha256="25b0c2c30042d82efd1893bd42ec726764262d94115393a1718f8d65d2a7817b",
        size=66252587,
        parts=(f"{_RAW}/sttn-det/sttn.pth",),
    ),
    "lama": WeightSpec(
        key="lama",
        filename="big-lama.pt",
        sha256="7ba7aa7ac37a4d41fdbbeba3a2af7ead18058552997e3a3cd1a3b2210c9e6b4c",
        size=205803670,
        parts=tuple(f"{_RAW}/big-lama/big-lama_{i}.pt" for i in range(1, 6)),
    ),
}

ProgressCallback = Callable[[str], None]


def ensure_weight(
    key: str,
    *,
    models_dir: Path,
    local_only: bool = False,
    on_progress: ProgressCallback | None = None,
) -> Path:
    """Return a verified local path to weight ``key``, downloading if needed."""
    spec = WEIGHTS[key]
    dst = models_dir / spec.filename
    if dst.exists() and _sha256(dst) == spec.sha256:
        return dst
    if local_only:
        raise FileNotFoundError(
            f"Subtitle-erase weight '{spec.filename}' for backend '{key}' not found in {models_dir} "
            f"and SUBTITLE_ERASE_LOCAL_MODELS_ONLY is set. Place the file there or allow downloads."
        )

    models_dir.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".part")
    try:
        with tmp.open("wb") as out:
            for index, url in enumerate(spec.parts, start=1):
                if on_progress is not None:
                    label = spec.filename if len(spec.parts) == 1 else f"{spec.filename} ({index}/{len(spec.parts)})"
                    on_progress(f"downloading {label}")
                _download_into(url, out)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise

    digest = _sha256(tmp)
    if digest != spec.sha256:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(
            f"Downloaded weight '{spec.filename}' sha256 mismatch (got {digest}, expected {spec.sha256})."
        )
    tmp.replace(dst)
    return dst


def _download_into(url: str, out) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "translip-erase"})
    with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310 (trusted upstream)
        if getattr(response, "status", 200) not in (200, None):
            raise RuntimeError(f"Failed to download {url}: HTTP {response.status}")
        shutil.copyfileobj(response, out, length=1024 * 1024)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = ["WeightSpec", "WEIGHTS", "ensure_weight"]
