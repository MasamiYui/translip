"""ASCII startup banner for the ``translip`` CLI / server.

Single source of truth for the wordmark. The art is assembled from a small
box-drawing glyph map (so columns always line up) and rendered with optional
ANSI colour. Callers gate display on a TTY + ``TRANSLIP_NO_BANNER`` so the
banner never pollutes machine-readable stdout (e.g. ``probe`` JSON) or the
per-stage subprocess logs the orchestrator captures.
"""

from __future__ import annotations

import os
import sys
from importlib import metadata
from typing import IO

# "Calvin S" box-drawing font (3 rows tall, compact) — reliable in modern terminals.
_GLYPHS: dict[str, tuple[str, str, str]] = {
    "T": ("╔╦╗", " ║ ", " ╩ "),
    "R": ("╦═╗", "╠╦╝", "╩╚═"),
    "A": ("╔═╗", "╠═╣", "╩ ╩"),
    "N": ("╔╗╔", "║║║", "╝╚╝"),
    "S": ("╔═╗", "╚═╗", "╚═╝"),
    "L": ("╦  ", "║  ", "╩═╝"),
    "I": ("╦", "║", "╩"),
    "P": ("╔═╗", "╠═╝", "╩  "),
}
_WORD = "TRANSLIP"
_TAGLINE = "local-first · multi-speaker video dubbing"

# ANSI: cyan→blue vertical gradient on the wordmark, dim tagline, dim wave.
_RESET = "\033[0m"
_DIM = "\033[2m"
_GRAD = ("\033[38;5;51m", "\033[38;5;45m", "\033[38;5;39m")
_WAVE_COLOR = "\033[38;5;31m"
_VER_COLOR = "\033[38;5;45m"


def _version() -> str:
    try:
        return metadata.version("translip")
    except metadata.PackageNotFoundError:
        return "0.1.0"


def _wordmark_rows() -> list[str]:
    rows = ["", "", ""]
    for ch in _WORD:
        glyph = _GLYPHS[ch]
        for i in range(3):
            rows[i] += glyph[i] + " "
    return [row.rstrip() for row in rows]


def banner_text(*, color: bool = False) -> str:
    """Return the full multi-line banner. ``color=True`` adds ANSI escapes."""
    rows = _wordmark_rows()
    width = max(len(row) for row in rows)
    wave = ("▁▂▃▅▇▆▄▃▂▁" * ((width // 10) + 1))[:width]
    version = f"v{_version()}"

    if not color:
        lines = ["", "  " + wave, *(f"  {row}" for row in rows)]
        lines.append(f"  {_TAGLINE}  {version}")
        lines.append("  " + wave)
        return "\n".join(lines)

    lines = ["", f"  {_WAVE_COLOR}{wave}{_RESET}"]
    lines += [f"  {_GRAD[i]}{row}{_RESET}" for i, row in enumerate(rows)]
    lines.append(f"  {_DIM}{_TAGLINE}{_RESET}  {_VER_COLOR}{version}{_RESET}")
    lines.append(f"  {_WAVE_COLOR}{wave}{_RESET}")
    return "\n".join(lines)


def print_startup_banner(stream: IO[str] | None = None, *, enabled: bool = True) -> None:
    """Print the banner to ``stream`` (default stderr) for interactive runs only.

    No-op unless the stream is a TTY and neither ``enabled`` is False nor
    ``TRANSLIP_NO_BANNER`` is set. Colour is additionally suppressed by
    ``NO_COLOR`` (https://no-color.org). Writing to stderr keeps stdout — where
    commands like ``probe``/``analyze-video`` emit JSON — clean.
    """
    if stream is None:
        stream = sys.stderr
    if not enabled or os.environ.get("TRANSLIP_NO_BANNER"):
        return
    if not stream.isatty():
        return
    color = not os.environ.get("NO_COLOR")
    try:
        stream.write(banner_text(color=color) + "\n")
        stream.flush()
    except OSError:
        pass
