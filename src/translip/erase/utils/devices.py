"""Torch device resolution for the neural inpainting backends.

Mirrors translip's other ML stages: prefer an accelerator, fall back to CPU.
On Apple Silicon ``mps`` is used; weights are always loaded with
``map_location="cpu"`` then moved to the device (the safe MPS pattern), and
half precision is never used (the STTN/LaMa graphs are float32 only).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import torch


def resolve_device(preference: str = "auto") -> "torch.device":
    import torch

    pref = (preference or "auto").strip().lower()
    if pref == "cpu":
        return torch.device("cpu")
    if pref == "cuda":
        if torch.cuda.is_available():
            return torch.device("cuda")
        return torch.device("cpu")
    if pref == "mps":
        if torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")
    # auto
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def empty_cache(device: "torch.device") -> None:
    """Release cached accelerator memory between chunks (best-effort)."""
    import torch

    if device.type == "cuda" and torch.cuda.is_available():
        torch.cuda.empty_cache()
    elif device.type == "mps" and hasattr(torch, "mps"):
        try:
            torch.mps.empty_cache()
        except Exception:
            pass


__all__ = ["resolve_device", "empty_cache"]
