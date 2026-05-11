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
    "asr_model": "small",
    "generate_srt": True,
    "top_k": 3,
    "translation_backend": "local-m2m100",
    "translation_batch_size": 4,
    "condense_mode": "off",
    "tts_backend": "moss-tts-nano-onnx",
    "fit_policy": "conservative",
    "fit_backend": "atempo",
    "mix_profile": "preview",
    "ducking_mode": "static",
    "background_gain_db": -8.0,
    "export_preview": True,
    "export_dub": True,
    "delivery_container": "mp4",
    "delivery_video_codec": "copy",
    "delivery_audio_codec": "aac",
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


@router.get("/defaults")
def get_defaults():
    return _DEFAULT_CONFIG


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
