"""Thin, standalone lab dashboard server (own port; read/visualize + trigger runs)."""
from __future__ import annotations

from .app import app, run_server

__all__ = ["app", "run_server"]
