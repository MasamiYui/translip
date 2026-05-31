from __future__ import annotations

import logging
from typing import Optional


def resolve_torch_device(requested: str, *, logger: Optional[logging.Logger] = None) -> str:
    """Resolve a requested torch device alias to a concrete device string.

    Standard ladder shared across backends:

    - ``"cuda"`` -> ``"cuda"`` if available else ``"cpu"`` (warns when unavailable).
    - ``"mps"``  -> ``"mps"`` if available (guarded) else ``"cpu"`` (warns when unavailable).
    - ``"auto"`` -> ``"cuda"``, else ``"mps"`` (guarded), else ``"cpu"``.
    - anything else (including ``"cpu"``) -> ``"cpu"``.

    The ``mps`` checks use the safest guard variant
    (``getattr(torch.backends, "mps", None) is not None and
    torch.backends.mps.is_available()``) so torch builds without an MPS backend
    never raise.

    torch is imported lazily so importing this module stays cheap.
    """
    import torch

    def _cuda_available() -> bool:
        return bool(torch.cuda.is_available())

    def _mps_available() -> bool:
        mps = getattr(torch.backends, "mps", None)
        return bool(mps is not None and mps.is_available())

    if requested == "cuda":
        if _cuda_available():
            return "cuda"
        if logger is not None:
            logger.warning("CUDA requested but unavailable; falling back to CPU.")
        return "cpu"
    if requested == "mps":
        if _mps_available():
            return "mps"
        if logger is not None:
            logger.warning("MPS requested but unavailable; falling back to CPU.")
        return "cpu"
    if requested == "auto":
        if _cuda_available():
            return "cuda"
        if _mps_available():
            return "mps"
        return "cpu"
    return "cpu"
