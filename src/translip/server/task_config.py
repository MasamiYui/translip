from __future__ import annotations

from typing import Any, Mapping

_ERASE_TEMPLATE_ID = "asr-dub+ocr-subs+erase"
_LEGACY_ERASE_DEFAULTS = {
    "run_to_stage": "task-e",
    "video_source": "original",
    "audio_source": "both",
    "subtitle_source": "asr",
}
_UPGRADED_ERASE_DEFAULTS = {
    "run_to_stage": "task-g",
    "video_source": "clean_if_available",
}


def normalize_task_config(config: Mapping[str, Any] | None) -> dict[str, Any]:
    normalized = dict(config or {})
    if _matches_legacy_erase_defaults(normalized):
        normalized.update(_UPGRADED_ERASE_DEFAULTS)
    return normalized


def _matches_legacy_erase_defaults(config: Mapping[str, Any]) -> bool:
    if config.get("template") != _ERASE_TEMPLATE_ID:
        return False
    return all(config.get(key) == value for key, value in _LEGACY_ERASE_DEFAULTS.items())


__all__ = ["normalize_task_config"]
