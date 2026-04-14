from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..database import get_session
from ..models import ConfigPreset
from ..schemas import ConfigPresetRead, CreatePresetRequest

router = APIRouter(prefix="/api/config", tags=["config"])

_DEFAULT_CONFIG = {
    "device": "auto",
    "run_from_stage": "stage1",
    "run_to_stage": "task-e",
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
    "tts_backend": "qwen3tts",
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


@router.get("/defaults")
def get_defaults():
    return _DEFAULT_CONFIG


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
