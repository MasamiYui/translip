"""Environment self-check (`translip doctor`) + the cheap startup summary.

Two layers live here on purpose:

* ``environment_summary_lines`` / ``print_environment_summary`` — a **cheap**,
  TTY-gated few-liner shown right under the startup banner (bare ``translip`` and
  the server boot). It must never import torch or any heavy ML stack: it only
  does ``shutil.which`` + ``importlib.util.find_spec`` + a filesystem scan of the
  model cache, so it adds no measurable latency and works before anything is
  installed.
* ``collect_report`` / ``run_doctor`` — the **full** check behind the ``doctor``
  subcommand. This one is allowed to be slow (it imports torch to detect the
  inference device, walks the cache for its size, and probes saved API keys).

Both reuse the same registry the server's ``/api/system/*`` routes use
(``server.cache_manager``) so the CLI and the UI never drift.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import IO

# ANSI ----------------------------------------------------------------------
_RESET = "\033[0m"
_DIM = "\033[2m"
_BOLD = "\033[1m"
_GREEN = "\033[38;5;42m"
_YELLOW = "\033[38;5;220m"
_RED = "\033[38;5;203m"
_CYAN = "\033[38;5;45m"

_OK = "✓"
_WARN = "⚠"
_BAD = "✗"
_DOT = "·"

# Python import names that signal each optional extra is installed.
_EXTRAS = {
    "ocr": "paddleocr",
    "erase": "cv2",
    "vision": "mlx_vlm",
    "dev": "pytest",
}


def _paint(text: str, color_code: str, *, color: bool) -> str:
    return f"{color_code}{text}{_RESET}" if color else text


def _has_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


# --- cheap signals (banner-safe) -------------------------------------------


def _ffmpeg_path() -> str | None:
    return shutil.which("ffmpeg")


def _cache_root() -> Path:
    from ..server import cache_manager

    return cache_manager.resolve_active_cache_root()


def _missing_models() -> list[str]:
    from ..server import cache_manager

    try:
        return cache_manager.list_missing_model_keys()
    except Exception:  # never let a cache hiccup break startup
        return []


def _extras_state() -> dict[str, bool]:
    return {name: _has_module(mod) for name, mod in _EXTRAS.items()}


def environment_summary_lines(*, color: bool = False) -> list[str]:
    """Return the cheap startup summary lines (no heavy imports)."""
    lines: list[str] = []
    lines.append("  " + _paint("environment", _DIM, color=color))

    ffmpeg = _ffmpeg_path()
    if ffmpeg:
        lines.append(
            f"  {_paint(_OK, _GREEN, color=color)} "
            f"{_paint('ffmpeg ', _DIM, color=color)}  {ffmpeg}"
        )
    else:
        lines.append(
            f"  {_paint(_BAD, _RED, color=color)} "
            f"{_paint('ffmpeg ', _DIM, color=color)}  "
            "not found — required; install it and put it on PATH"
        )

    lines.append(
        f"  {_paint(_OK, _GREEN, color=color)} "
        f"{_paint('cache  ', _DIM, color=color)}  {_cache_root()}"
    )

    missing = _missing_models()
    if missing:
        lines.append(
            f"  {_paint(_WARN, _YELLOW, color=color)} "
            f"{_paint('models ', _DIM, color=color)}  "
            f"{len(missing)} missing "
            + _paint("· run `translip doctor`", _DIM, color=color)
        )
    else:
        lines.append(
            f"  {_paint(_OK, _GREEN, color=color)} "
            f"{_paint('models ', _DIM, color=color)}  all present"
        )

    extras = _extras_state()
    parts = []
    for name in ("ocr", "erase", "vision"):
        mark = _OK if extras[name] else _BAD
        col = _GREEN if extras[name] else _DIM
        parts.append(_paint(f"{name} {mark}", col, color=color))
    lines.append(
        f"  {_paint(_DOT, _DIM, color=color)} "
        f"{_paint('extras ', _DIM, color=color)}  " + "  ".join(parts)
    )
    return lines


def print_environment_summary(stream: IO[str] | None = None, *, enabled: bool = True) -> None:
    """Print the cheap env summary to ``stream`` for interactive runs only.

    Same gating as the banner: no-op unless the stream is a TTY and neither
    ``enabled`` is False nor ``TRANSLIP_NO_BANNER`` is set. Writing to stderr
    keeps stdout (where ``probe``/``analyze-video`` emit JSON) clean.
    """
    if stream is None:
        stream = sys.stderr
    if not enabled or os.environ.get("TRANSLIP_NO_BANNER"):
        return
    if not stream.isatty():
        return
    color = not os.environ.get("NO_COLOR")
    try:
        stream.write("\n".join(environment_summary_lines(color=color)) + "\n")
        stream.flush()
    except OSError:
        pass


# --- full report (doctor) --------------------------------------------------


def _ffmpeg_version(binary: str) -> str | None:
    try:
        out = subprocess.run(
            [binary, "-version"], capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return None
    first = (out.stdout or "").splitlines()
    return first[0].strip() if first else None


def _detect_device() -> str:
    try:
        import torch
    except Exception as exc:  # torch missing or broken
        return f"unknown (torch unavailable: {type(exc).__name__})"
    try:
        if torch.cuda.is_available():
            return "CUDA"
        if torch.backends.mps.is_available():
            return "MPS (Apple Silicon)"
    except Exception:
        pass
    return "CPU"


def _moss_cli() -> str | None:
    """Resolve the MOSS-TTS-Nano CLI exactly as the dub backend would."""
    try:
        from ..dubbing.moss_tts_nano_backend import _resolve_cli_path
    except Exception:
        # Fall back to the same resolution order without importing the backend.
        if env := os.environ.get("MOSS_TTS_NANO_CLI"):
            return env if Path(env).exists() else None
        return shutil.which("moss-tts-nano")
    resolved = _resolve_cli_path()
    # _resolve_cli_path returns the bare name as a last resort; treat a
    # non-existent / non-on-PATH result as "not installed".
    if os.path.sep in resolved or os.path.altsep and (os.path.altsep in resolved):
        return resolved if Path(resolved).exists() else None
    return shutil.which(resolved)


def _human_bytes(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def collect_report() -> dict:
    """Gather the full environment report (allowed to be slow)."""
    from ..server import cache_manager

    cache_root = cache_manager.resolve_active_cache_root()

    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    moss = _moss_cli()

    deepseek_set = cache_manager.llm_key_is_set("deepseek")
    hf_set = bool(cache_manager._resolve_hf_token())

    try:
        cache_size = cache_manager.dir_size(cache_root)
    except Exception:
        cache_size = 0

    return {
        "system": {
            "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "platform": __import__("platform").platform(),
            "device": _detect_device(),
        },
        "tools": {
            "ffmpeg": ffmpeg,
            "ffmpeg_version": _ffmpeg_version(ffmpeg) if ffmpeg else None,
            "ffprobe": ffprobe,
            "moss_tts_nano": moss,
        },
        "extras": _extras_state(),
        "api_keys": {
            "deepseek": deepseek_set,
            "huggingface": hf_set,
        },
        "cache": {
            "dir": str(cache_root),
            "size_bytes": cache_size,
        },
        "models": cache_manager.collect_model_statuses(),
        "missing_models": cache_manager.list_missing_model_keys(),
    }


def _status_mark(present: bool, color: bool, *, warn: bool = False) -> str:
    if present:
        return _paint(_OK, _GREEN, color=color)
    return _paint(_WARN if warn else _BAD, _YELLOW if warn else _RED, color=color)


def render_report(report: dict, *, color: bool = False) -> str:
    def head(text: str) -> str:
        return _paint(text, _BOLD + _CYAN, color=color)

    def label(text: str) -> str:
        return _paint(f"{text:<14}", _DIM, color=color)

    lines: list[str] = []
    sysd = report["system"]
    lines.append(head("System"))
    lines.append(f"  {label('python')}{sysd['python']}")
    lines.append(f"  {label('platform')}{sysd['platform']}")
    lines.append(f"  {label('device')}{sysd['device']}")

    tools = report["tools"]
    lines.append("")
    lines.append(head("Tools"))
    ff = tools["ffmpeg"]
    lines.append(
        f"  {_status_mark(bool(ff), color)} {label('ffmpeg')}"
        + (f"{ff}" if ff else _paint("not found — required", _RED, color=color))
    )
    if tools.get("ffmpeg_version"):
        lines.append(f"    {_paint(tools['ffmpeg_version'], _DIM, color=color)}")
    fp = tools["ffprobe"]
    lines.append(
        f"  {_status_mark(bool(fp), color)} {label('ffprobe')}"
        + (f"{fp}" if fp else _paint("not found — required", _RED, color=color))
    )
    moss = tools["moss_tts_nano"]
    lines.append(
        f"  {_status_mark(bool(moss), color, warn=True)} {label('moss-tts-nano')}"
        + (
            f"{moss}"
            if moss
            else _paint("not found — default TTS backend (set MOSS_TTS_NANO_CLI)", _YELLOW, color=color)
        )
    )

    extras = report["extras"]
    lines.append("")
    lines.append(head("Python extras"))
    extra_hint = {
        "ocr": "uv sync --extra ocr",
        "erase": "uv sync --extra erase",
        "vision": "uv sync --extra vision",
        "dev": "uv sync --extra dev",
    }
    for name, present in extras.items():
        suffix = "" if present else _paint(f"— {extra_hint[name]}", _DIM, color=color)
        lines.append(f"  {_status_mark(present, color, warn=True)} {label(name)}{suffix}")

    keys = report["api_keys"]
    lines.append("")
    lines.append(head("API keys"))
    lines.append(
        f"  {_status_mark(keys['deepseek'], color, warn=True)} {label('deepseek')}"
        + ("configured" if keys["deepseek"] else _paint("not set — deepseek translation/arbitration", _DIM, color=color))
    )
    lines.append(
        f"  {_status_mark(keys['huggingface'], color, warn=True)} {label('huggingface')}"
        + ("configured" if keys["huggingface"] else _paint("not set — gated models (pyannote)", _DIM, color=color))
    )

    cache = report["cache"]
    lines.append("")
    lines.append(head("Cache"))
    lines.append(f"  {label('dir')}{cache['dir']}")
    lines.append(f"  {label('size')}{_human_bytes(cache['size_bytes'])}")

    models = report["models"]
    lines.append("")
    lines.append(head("Models"))
    for m in models:
        status = m.get("status", "missing")
        present = status == "available"
        warn = status == "needs_extra"
        mark = _status_mark(present, color, warn=warn)
        detail = ""
        if status == "needs_extra":
            detail = _paint("  (needs `ocr` extra)", _DIM, color=color)
        elif not present:
            detail = _paint(f"  ({status})", _DIM, color=color)
        lines.append(f"  {mark} {m['name']}{detail}")

    missing = report["missing_models"]
    lines.append("")
    if missing:
        lines.append(
            _paint(
                f"  {_WARN} {len(missing)} model(s) missing — download with:",
                _YELLOW,
                color=color,
            )
        )
        lines.append(_paint(f"      uv run translip download-models --backend {missing[0]}", _DIM, color=color))
    else:
        lines.append(_paint(f"  {_OK} all registered model weights present", _GREEN, color=color))

    return "\n".join(lines)


def run_doctor(*, as_json: bool = False) -> int:
    """Print the environment report. Returns 1 if a hard dependency is missing."""
    report = collect_report()
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        color = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
        print(render_report(report, color=color))
    # ffmpeg/ffprobe are the only true hard dependencies of the base install.
    hard_ok = bool(report["tools"]["ffmpeg"]) and bool(report["tools"]["ffprobe"])
    return 0 if hard_ok else 1
