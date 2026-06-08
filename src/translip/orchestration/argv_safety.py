"""Lightweight whitelist validation for free-text values that flow into argv.

The orchestrator shells out with ``shell=False`` argv lists, so there is no
*shell* injection surface. Two real risks remain for un-vetted free-text values:

1. **Argument injection** — a value beginning with ``-`` can be swallowed by
   ``argparse`` in the child process as a flag instead of the intended value.
2. **Path traversal** — ``speaker_id`` is used directly as a directory component
   (``task_d_voice_dir / speaker_id``), so ``..`` / separators must be rejected.

These validators run *before* argv construction and raise a clear
:class:`ArgvValidationError` so malformed values fail fast with an actionable
message rather than producing a confusing downstream argparse error or a stray
path. They intentionally accept Unicode word characters (CJK persona names,
etc.) — the goal is to block the two attack shapes above, not to be a strict
allow-list of ASCII.
"""

from __future__ import annotations

import re

__all__ = [
    "ArgvValidationError",
    "validate_lang",
    "validate_url",
    "validate_model",
    "validate_path_identifier",
]


class ArgvValidationError(ValueError):
    """Raised when a value bound for argv fails whitelist validation."""


# en / zh / ja / yue / zh-CN / en_US / "auto" (ASR auto-detect)
_LANG_RE = re.compile(r"^(auto|[A-Za-z]{2,3}([-_][A-Za-z]{2,4})?)$")
# http(s) URL, no whitespace, bounded length
_URL_RE = re.compile(r"^https?://[^\s/$.?#]\S*$", re.IGNORECASE)
# model names: deepseek-v4-pro, gpt-4o, org/model, vendor:tag — no leading dash, no whitespace
_MODEL_RE = re.compile(r"^[A-Za-z0-9](?:[\w./:\-]*)$")
# path-safe identifier: SPEAKER_00, persona slugs, CJK names — \w covers Unicode word chars
_IDENT_RE = re.compile(r"^(?!-)[\w.\-]+$")


def validate_lang(value: str, *, field: str) -> str:
    if not _LANG_RE.match(value or ""):
        raise ArgvValidationError(
            f"{field}: invalid language code {value!r} (expected e.g. 'en', 'zh', 'zh-CN', or 'auto')"
        )
    return value


def validate_url(value: str, *, field: str) -> str:
    if not value or len(value) > 2048 or not _URL_RE.match(value):
        raise ArgvValidationError(
            f"{field}: invalid URL {value!r} (expected an http(s):// URL)"
        )
    return value


def validate_model(value: str, *, field: str) -> str:
    if not value or len(value) > 256 or not _MODEL_RE.match(value):
        raise ArgvValidationError(
            f"{field}: invalid model name {value!r} (letters/digits/._/:- only, no leading dash or spaces)"
        )
    return value


def validate_path_identifier(value: str, *, field: str) -> str:
    """Validate a value used both as an argv token and a path component."""
    if (
        not value
        or len(value) > 256
        or value in {".", ".."}
        or ".." in value
        or "/" in value
        or "\\" in value
        or not _IDENT_RE.match(value)
    ):
        raise ArgvValidationError(
            f"{field}: invalid identifier {value!r} "
            "(letters/digits/._- only, no leading dash, no path separators)"
        )
    return value
