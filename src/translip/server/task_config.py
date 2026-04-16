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
_DELIVERY_DEFAULTS = {
    "export_preview": True,
    "export_dub": True,
    "delivery_container": "mp4",
    "delivery_video_codec": "copy",
    "delivery_audio_codec": "aac",
    "subtitle_mode": "none",
    "subtitle_render_source": "ocr",
    "subtitle_font": None,
    "subtitle_font_size": 0,
    "subtitle_color": "#FFFFFF",
    "subtitle_outline_color": "#000000",
    "subtitle_outline_width": 2.0,
    "subtitle_position": "bottom",
    "subtitle_margin_v": 0,
    "subtitle_bold": False,
    "bilingual_chinese_position": "bottom",
    "bilingual_english_position": "top",
    "subtitle_preview_duration_sec": 10.0,
}
_DELIVERY_KEYS = set(_DELIVERY_DEFAULTS)


def normalize_task_config(config: Mapping[str, Any] | None) -> dict[str, Any]:
    return dict(normalize_task_storage(config)["pipeline"])


def normalize_task_delivery_config(config: Mapping[str, Any] | None) -> dict[str, Any]:
    return dict(normalize_task_storage(config)["delivery"])


def normalize_task_storage(config: Mapping[str, Any] | None) -> dict[str, Any]:
    raw = dict(config or {})
    nested_pipeline = raw.get("pipeline")
    nested_delivery = raw.get("delivery")
    pipeline = dict(nested_pipeline) if isinstance(nested_pipeline, Mapping) else {}
    delivery = dict(nested_delivery) if isinstance(nested_delivery, Mapping) else {}

    for key, value in raw.items():
        if key in {"pipeline", "delivery"}:
            continue
        if key in _DELIVERY_KEYS:
            delivery.setdefault(key, value)
        else:
            pipeline.setdefault(key, value)

    if _matches_legacy_erase_defaults(pipeline):
        pipeline.update(_UPGRADED_ERASE_DEFAULTS)

    normalized_delivery = dict(_DELIVERY_DEFAULTS)
    normalized_delivery.update(delivery)
    return {
        "pipeline": pipeline,
        "delivery": normalized_delivery,
    }


def replace_task_delivery_config(
    config: Mapping[str, Any] | None,
    delivery_config: Mapping[str, Any],
) -> dict[str, Any]:
    normalized = normalize_task_storage(config)
    normalized["delivery"] = {
        **normalized["delivery"],
        **dict(delivery_config),
    }
    return normalized


def _matches_legacy_erase_defaults(config: Mapping[str, Any]) -> bool:
    if config.get("template") != _ERASE_TEMPLATE_ID:
        return False
    return all(config.get(key) == value for key, value in _LEGACY_ERASE_DEFAULTS.items())


__all__ = [
    "normalize_task_config",
    "normalize_task_delivery_config",
    "normalize_task_storage",
    "replace_task_delivery_config",
]
