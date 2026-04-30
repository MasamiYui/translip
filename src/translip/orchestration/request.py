from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..config import (
    DEFAULT_CONDENSE_MODE,
    DEFAULT_DEVICE,
    DEFAULT_DUBBING_BACKEND,
    DEFAULT_PIPELINE_OUTPUT_ROOT,
    DEFAULT_PIPELINE_RUN_FROM_STAGE,
    DEFAULT_PIPELINE_RUN_TO_STAGE,
    DEFAULT_PIPELINE_STATUS_UPDATE_INTERVAL_SEC,
    DEFAULT_PIPELINE_WRITE_STATUS,
    DEFAULT_RENDER_BACKGROUND_GAIN_DB,
    DEFAULT_RENDER_DUCKING_MODE,
    DEFAULT_RENDER_FIT_BACKEND,
    DEFAULT_RENDER_FIT_POLICY,
    DEFAULT_RENDER_MIX_PROFILE,
    DEFAULT_RENDER_OUTPUT_SAMPLE_RATE,
    DEFAULT_RENDER_PREVIEW_FORMAT,
    DEFAULT_RENDER_WINDOW_DUCKING_DB,
    DEFAULT_TRANSLATION_BACKEND,
    DEFAULT_TRANSLATION_BATCH_SIZE,
    DEFAULT_TRANSLATION_TARGET_LANG,
    DEFAULT_TRANSCRIPTION_ASR_MODEL,
    DEFAULT_TRANSCRIPTION_LANGUAGE,
)
from ..types import PipelineRequest


def _load_json_config(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    payload = json.loads(Path(path).expanduser().resolve().read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Pipeline config must be a JSON object")
    return payload


def _list_config(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item)]
    text = str(value).strip()
    return [text] if text else None


def build_pipeline_request(raw: dict[str, Any]) -> PipelineRequest:
    config_payload = _load_json_config(raw.get("config"))
    merged = dict(config_payload)
    for key, value in raw.items():
        if key in {"command", "verbose"}:
            continue
        if value is not None:
            merged[key] = value

    merged_policy = merged.get("delivery_policy")
    delivery_policy = merged_policy if isinstance(merged_policy, dict) else {}

    return PipelineRequest(
        input_path=merged["input"],
        output_root=merged.get("output_root", DEFAULT_PIPELINE_OUTPUT_ROOT),
        config_path=merged.get("config"),
        template_id=merged.get("template") or merged.get("template_id", "asr-dub-basic"),
        delivery_policy={
            "video_source": delivery_policy.get("video_source", merged.get("video_source", "original")),
            "audio_source": delivery_policy.get("audio_source", merged.get("audio_source", "both")),
            "subtitle_source": delivery_policy.get("subtitle_source", merged.get("subtitle_source", "asr")),
        },
        ocr_project_root=merged.get("ocr_project_root"),
        erase_project_root=merged.get("erase_project_root"),
        target_lang=merged.get("target_lang", DEFAULT_TRANSLATION_TARGET_LANG),
        translation_backend=merged.get("translation_backend", DEFAULT_TRANSLATION_BACKEND),
        translation_batch_size=int(merged.get("translation_batch_size", DEFAULT_TRANSLATION_BATCH_SIZE)),
        tts_backend=merged.get("tts_backend", DEFAULT_DUBBING_BACKEND),
        device=merged.get("device", DEFAULT_DEVICE),
        run_from_stage=merged.get("run_from_stage", DEFAULT_PIPELINE_RUN_FROM_STAGE),
        run_to_stage=merged.get("run_to_stage", DEFAULT_PIPELINE_RUN_TO_STAGE),
        resume=bool(merged.get("resume", False)),
        force_stages=merged.get("force_stages"),
        reuse_existing=bool(merged.get("reuse_existing", True)),
        keep_logs=bool(merged.get("keep_logs", True)),
        write_status=bool(merged.get("write_status", DEFAULT_PIPELINE_WRITE_STATUS)),
        status_update_interval_sec=float(
            merged.get("status_update_interval_sec", DEFAULT_PIPELINE_STATUS_UPDATE_INTERVAL_SEC)
        ),
        glossary_path=merged.get("glossary_path") or merged.get("glossary"),
        registry_path=merged.get("registry_path") or merged.get("registry"),
        api_model=merged.get("api_model"),
        api_base_url=merged.get("api_base_url"),
        condense_mode=merged.get("condense_mode", DEFAULT_CONDENSE_MODE),
        fit_policy=merged.get("fit_policy", DEFAULT_RENDER_FIT_POLICY),
        fit_backend=merged.get("fit_backend", DEFAULT_RENDER_FIT_BACKEND),
        mix_profile=merged.get("mix_profile", DEFAULT_RENDER_MIX_PROFILE),
        ducking_mode=merged.get("ducking_mode", DEFAULT_RENDER_DUCKING_MODE),
        preview_format=merged.get("preview_format", DEFAULT_RENDER_PREVIEW_FORMAT),
        output_sample_rate=int(merged.get("output_sample_rate", DEFAULT_RENDER_OUTPUT_SAMPLE_RATE)),
        background_gain_db=float(merged.get("background_gain_db", DEFAULT_RENDER_BACKGROUND_GAIN_DB)),
        window_ducking_db=float(merged.get("window_ducking_db", DEFAULT_RENDER_WINDOW_DUCKING_DB)),
        max_compress_ratio=float(merged.get("max_compress_ratio", 1.45)),
        dub_repair_enabled=bool(merged.get("dub_repair_enabled", False)),
        dub_repair_backends=_list_config(
            merged.get("dub_repair_backends")
            if merged.get("dub_repair_backends") is not None
            else merged.get("dub_repair_backend")
        ),
        dub_repair_max_items=int(merged.get("dub_repair_max_items", 12)),
        dub_repair_attempts_per_item=int(merged.get("dub_repair_attempts_per_item", 3)),
        dub_repair_include_risk=bool(merged.get("dub_repair_include_risk", False)),
        speaker_limit=int(merged.get("speaker_limit", 0)),
        segments_per_speaker=int(merged.get("segments_per_speaker", 0)),
        separation_mode=merged.get("separation_mode", "dialogue"),
        separation_quality=merged.get("separation_quality", "balanced"),
        stage1_output_format=merged.get("stage1_output_format", "mp3"),
        transcription_language=merged.get("transcription_language", DEFAULT_TRANSCRIPTION_LANGUAGE),
        asr_model=merged.get("asr_model", DEFAULT_TRANSCRIPTION_ASR_MODEL),
        audio_stream_index=int(merged.get("audio_stream_index", 0)),
        top_k=int(merged.get("top_k", 3)),
        update_registry=bool(merged.get("update_registry", True)),
        subtitle_mode=merged.get("subtitle_mode", "none"),
        subtitle_source=merged.get("subtitle_source", "ocr"),
        bilingual_chinese_position=merged.get("bilingual_chinese_position", "bottom"),
        bilingual_english_position=merged.get("bilingual_english_position", "top"),
        bilingual_export_strategy=merged.get(
            "bilingual_export_strategy",
            "auto_standard_bilingual",
        ),
    ).normalized()


__all__ = ["build_pipeline_request"]
