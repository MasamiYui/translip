"""Works (TV shows, movies, etc.) management routes.

These endpoints manage `~/.translip/works.json` — a structured registry of works
(作品) used to disambiguate personas across productions.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/config", tags=["config"])

CONFIG_DIR = Path.home() / ".translip"
CONFIG_PATH = CONFIG_DIR / "config.json"

_DEFAULT_CONFIG = {
    "device": "auto",
    "run_from_stage": "stage1",
    "run_to_stage": "task-g",
    "use_cache": True,
    "keep_intermediate": False,
    "separation_mode": "auto",
    "separation_quality": "balanced",
    "music_backend": "demucs",
    "dialogue_backend": "cdx23",
    "stage1_output_format": "mp3",
    "audio_stream_index": 0,
    "asr_model": "paraformer-zh",
    "asr_backend": "funasr",
    "diarizer_backend": "ecapa",
    "enable_diarization": True,
    "vad_filter": True,
    "vad_min_silence_duration_ms": 400,
    "beam_size": 5,
    "best_of": 5,
    "temperature": 0.0,
    "condition_on_previous_text": False,
    "generate_srt": True,
    "top_k": 3,
    "ocr_sample_interval": 0.25,
    "ocr_position_mode": "auto",
    "ocr_extraction_mode": "conservative",
    "translation_backend": "local-m2m100",
    "translation_batch_size": 4,
    "siliconflow_base_url": None,
    "siliconflow_model": None,
    "condense_mode": "off",
    "transcription_correction": {"enabled": True, "preset": "standard", "ocr_only_policy": "report_only", "llm_arbitration": "off"},
    "tts_backend": "moss-tts-nano-onnx",
    "dubbing_quality_check": "standard",
    "dubbing_workers": None,
    "dub_repair_enabled": False,
    "dub_repair_backend": [],
    "dub_repair_max_items": 12,
    "dub_repair_attempts_per_item": 3,
    "dub_repair_include_risk": False,
    "fit_policy": "conservative",
    "fit_backend": "atempo",
    "mix_profile": "preview",
    "ducking_mode": "static",
    "background_gain_db": -8.0,
    "window_ducking_db": -3.0,
    "max_compress_ratio": 1.45,
    "output_sample_rate": 24000,
    "preview_format": "wav",
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
    "bilingual_export_strategy": "auto_standard_bilingual",
}


def _load_config() -> dict[str, Any]:
    """Load config from ~/.translip/config.json."""
    if not CONFIG_PATH.exists():
        return {}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _save_config(config: dict[str, Any]) -> None:
    """Save config to ~/.translip/config.json."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    os.chmod(CONFIG_PATH, 0o600)


def _load_global_config() -> dict[str, Any]:
    config = _load_config()
    saved_global = config.get("global", {})
    if not isinstance(saved_global, dict):
        saved_global = {}
    return {**_DEFAULT_CONFIG, **saved_global}


@router.get("/defaults")
def get_defaults():
    return _load_global_config()


class GlobalConfigRequest(BaseModel):
    device: Optional[str] = None
    use_cache: Optional[bool] = None
    keep_intermediate: Optional[bool] = None
    separation_mode: Optional[str] = None
    separation_quality: Optional[str] = None
    stage1_output_format: Optional[str] = None
    audio_stream_index: Optional[int] = None
    asr_model: Optional[str] = None
    asr_backend: Optional[str] = None
    diarizer_backend: Optional[str] = None
    enable_diarization: Optional[bool] = None
    generate_srt: Optional[bool] = None
    vad_filter: Optional[bool] = None
    vad_min_silence_duration_ms: Optional[int] = None
    beam_size: Optional[int] = None
    best_of: Optional[int] = None
    temperature: Optional[float] = None
    condition_on_previous_text: Optional[bool] = None
    top_k: Optional[int] = None
    ocr_sample_interval: Optional[float] = None
    ocr_position_mode: Optional[str] = None
    ocr_extraction_mode: Optional[str] = None
    translation_backend: Optional[str] = None
    translation_batch_size: Optional[int] = None
    siliconflow_base_url: Optional[str] = None
    siliconflow_model: Optional[str] = None
    condense_mode: Optional[str] = None
    transcription_correction: Optional[dict] = None
    tts_backend: Optional[str] = None
    dubbing_quality_check: Optional[str] = None
    dubbing_workers: Optional[int] = None
    dub_repair_enabled: Optional[bool] = None
    dub_repair_backend: Optional[list[str]] = None
    dub_repair_max_items: Optional[int] = None
    dub_repair_attempts_per_item: Optional[int] = None
    dub_repair_include_risk: Optional[bool] = None
    fit_policy: Optional[str] = None
    fit_backend: Optional[str] = None
    mix_profile: Optional[str] = None
    ducking_mode: Optional[str] = None
    background_gain_db: Optional[float] = None
    window_ducking_db: Optional[float] = None
    max_compress_ratio: Optional[float] = None
    output_sample_rate: Optional[int] = None
    preview_format: Optional[str] = None
    export_preview: Optional[bool] = None
    export_dub: Optional[bool] = None
    delivery_container: Optional[str] = None
    delivery_video_codec: Optional[str] = None
    delivery_audio_codec: Optional[str] = None
    subtitle_mode: Optional[str] = None
    subtitle_render_source: Optional[str] = None
    subtitle_font: Optional[str] = None
    subtitle_font_size: Optional[int] = None
    subtitle_color: Optional[str] = None
    subtitle_outline_color: Optional[str] = None
    subtitle_outline_width: Optional[float] = None
    subtitle_position: Optional[str] = None
    subtitle_margin_v: Optional[int] = None
    subtitle_bold: Optional[bool] = None
    bilingual_chinese_position: Optional[str] = None
    bilingual_english_position: Optional[str] = None
    bilingual_export_strategy: Optional[str] = None


def _validate_global_update(update: dict[str, Any]) -> None:
    for field in (
        "vad_min_silence_duration_ms",
        "beam_size",
        "best_of",
        "top_k",
        "translation_batch_size",
        "dubbing_workers",
        "dub_repair_max_items",
        "dub_repair_attempts_per_item",
        "output_sample_rate",
    ):
        if field in update and update[field] is not None and int(update[field]) <= 0:
            raise HTTPException(status_code=400, detail=f"{field} must be greater than 0")
    for field in ("audio_stream_index", "subtitle_font_size", "subtitle_margin_v"):
        if field in update and update[field] is not None and int(update[field]) < 0:
            raise HTTPException(status_code=400, detail=f"{field} must be greater than or equal to 0")
    if "max_compress_ratio" in update and update["max_compress_ratio"] is not None and float(update["max_compress_ratio"]) <= 0:
        raise HTTPException(status_code=400, detail="max_compress_ratio must be greater than 0")
    for field in ("subtitle_outline_width",):
        if field in update and update[field] is not None and float(update[field]) < 0:
            raise HTTPException(status_code=400, detail=f"{field} must be greater than or equal to 0")
    if "temperature" in update and update["temperature"] is not None and float(update["temperature"]) < 0:
        raise HTTPException(status_code=400, detail="temperature must be greater than or equal to 0")


@router.get("/global")
def get_global_config() -> dict[str, Any]:
    return _load_global_config()


@router.put("/global")
def update_global_config(req: GlobalConfigRequest) -> dict[str, Any]:
    update = req.model_dump(exclude_unset=True)
    _validate_global_update(update)
    config = _load_config()
    saved_global = config.get("global", {})
    if not isinstance(saved_global, dict):
        saved_global = {}
    for key, value in update.items():
        if value is None:
            saved_global.pop(key, None)
        else:
            saved_global[key] = value
    config["global"] = saved_global
    _save_config(config)
    return {"ok": True, "config": _load_global_config()}


@router.get("/tmdb")
def get_tmdb_config() -> dict[str, Any]:
    """Get current TMDb API configuration."""
    config = _load_config()
    tmdb = config.get("tmdb", {})
    return {
        "ok": True,
        "api_key_v3_set": bool(tmdb.get("api_key_v3")),
        "api_key_v4_set": bool(tmdb.get("api_key_v4")),
        "default_language": tmdb.get("default_language", "zh-CN"),
    }


class TMDbConfigRequest(BaseModel):
    api_key_v3: Optional[str] = None
    api_key_v4: Optional[str] = None
    default_language: Optional[str] = None


@router.post("/tmdb")
def save_tmdb_config(req: TMDbConfigRequest) -> dict[str, Any]:
    """Save TMDb API configuration."""
    config = _load_config()
    
    if "tmdb" not in config:
        config["tmdb"] = {}
    
    if req.api_key_v3 is not None:
        config["tmdb"]["api_key_v3"] = req.api_key_v3
    if req.api_key_v4 is not None:
        config["tmdb"]["api_key_v4"] = req.api_key_v4
    if req.default_language is not None:
        config["tmdb"]["default_language"] = req.default_language
    
    _save_config(config)
    
    return {
        "ok": True,
        "message": "TMDb configuration saved",
    }


# ---- Presets ----

from datetime import datetime

from fastapi import Depends
from sqlmodel import Session, select

from ..database import get_session
from ..models import ConfigPreset
from ..schemas import ConfigPresetRead, CreatePresetRequest

presets_router = APIRouter(prefix="/api/config/presets", tags=["config-presets"])


@router.get("/presets", response_model=list[ConfigPresetRead])
def list_presets(session: Session = Depends(get_session)):
    return list(session.exec(select(ConfigPreset)).all())


@router.post("/presets", response_model=ConfigPresetRead)
def create_preset(req: CreatePresetRequest, session: Session = Depends(get_session)):
    existing = session.exec(select(ConfigPreset).where(ConfigPreset.name == req.name)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Preset with this name already exists")
    preset = ConfigPreset(
        name=req.name,
        description=req.description,
        source_lang=req.source_lang,
        target_lang=req.target_lang,
        config=req.config,
    )
    session.add(preset)
    session.commit()
    session.refresh(preset)
    return preset


@router.delete("/presets/{preset_id}")
def delete_preset(preset_id: int, session: Session = Depends(get_session)):
    preset = session.get(ConfigPreset, preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="Preset not found")
    session.delete(preset)
    session.commit()
    return {"ok": True}
