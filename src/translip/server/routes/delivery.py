from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from ...delivery.runner import export_video
from ...subtitles.preview import SubtitlePreviewRequest, preview_subtitle
from ...types import ExportVideoRequest, SubtitleStyle
from ..database import get_session
from ..models import Task
from ..task_config import replace_task_delivery_config

router = APIRouter(prefix="/api/tasks", tags=["delivery"])


class SubtitlePreviewRequestPayload(BaseModel):
    input_video_path: str | None = None
    subtitle_path: str
    output_path: str | None = None
    font_family: str = "Noto Sans"
    font_size: int = 0
    primary_color: str = "#FFFFFF"
    outline_color: str = "#000000"
    outline_width: float = 2.0
    position: Literal["top", "bottom"] = "bottom"
    margin_v: int = 0
    bold: bool = False
    start_sec: float | None = None
    duration_sec: float = 10.0


class DeliveryComposeRequestPayload(BaseModel):
    subtitle_mode: Literal["none", "chinese_only", "english_only", "bilingual"] = "none"
    subtitle_source: Literal["ocr", "asr"] = "ocr"
    font_family: str = "Noto Sans"
    font_size: int = 0
    primary_color: str = "#FFFFFF"
    outline_color: str = "#000000"
    outline_width: float = 2.0
    position: Literal["top", "bottom"] = "bottom"
    margin_v: int = 0
    bold: bool = False
    bilingual_chinese_position: Literal["top", "bottom"] = "bottom"
    bilingual_english_position: Literal["top", "bottom"] = "top"
    export_preview: bool = True
    export_dub: bool = True


def _build_style(
    *,
    font_family: str,
    font_size: int,
    primary_color: str,
    outline_color: str,
    outline_width: float,
    position: str,
    margin_v: int,
    bold: bool,
) -> SubtitleStyle:
    return SubtitleStyle(
        font_family=font_family,
        font_size=font_size,
        primary_color=primary_color,
        outline_color=outline_color,
        outline_width=outline_width,
        shadow_depth=1.0,
        bold=bold,
        position=position,
        margin_v=margin_v,
        margin_h=20,
        alignment=8 if position == "top" else 2,
    )


@router.post("/{task_id}/subtitle-preview")
def create_subtitle_preview(
    task_id: str,
    payload: SubtitlePreviewRequestPayload,
    session: Session = Depends(get_session),
):
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    output_root = Path(task.output_root)
    output_path = (
        Path(payload.output_path).expanduser().resolve()
        if payload.output_path
        else output_root / "preview" / "subtitle-preview.mp4"
    )
    input_video = Path(payload.input_video_path) if payload.input_video_path else None
    if not input_video or not input_video.exists():
        input_video = Path(task.input_path)
    result = preview_subtitle(
        SubtitlePreviewRequest(
            input_video_path=input_video,
            subtitle_path=str((output_root / payload.subtitle_path).resolve()) if not Path(payload.subtitle_path).is_absolute() else payload.subtitle_path,
            output_path=output_path,
            style=_build_style(
                font_family=payload.font_family,
                font_size=payload.font_size,
                primary_color=payload.primary_color,
                outline_color=payload.outline_color,
                outline_width=payload.outline_width,
                position=payload.position,
                margin_v=payload.margin_v,
                bold=payload.bold,
            ),
            start_sec=payload.start_sec,
            duration_sec=payload.duration_sec,
        )
    )
    return {
        "preview_path": str(result.preview_path),
        "start_sec": result.start_sec,
        "duration_sec": result.duration_sec,
        "style_used": asdict(result.style_used),
    }


@router.post("/{task_id}/delivery-compose")
def compose_delivery(
    task_id: str,
    payload: DeliveryComposeRequestPayload,
    session: Session = Depends(get_session),
):
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    output_root = Path(task.output_root)
    result = export_video(
        ExportVideoRequest(
            input_video_path=Path(task.input_path),
            pipeline_root=output_root,
            task_e_dir=output_root / "task-e" / "voice",
            output_dir=output_root / "task-g",
            target_lang=task.target_lang,
            export_preview=payload.export_preview,
            export_dub=payload.export_dub,
            subtitle_mode=payload.subtitle_mode,
            subtitle_source=payload.subtitle_source,
            subtitle_style=_build_style(
                font_family=payload.font_family,
                font_size=payload.font_size,
                primary_color=payload.primary_color,
                outline_color=payload.outline_color,
                outline_width=payload.outline_width,
                position=payload.position,
                margin_v=payload.margin_v,
                bold=payload.bold,
            ),
            bilingual_chinese_position=payload.bilingual_chinese_position,
            bilingual_english_position=payload.bilingual_english_position,
        )
    )

    task.config = replace_task_delivery_config(
        task.config,
        {
            "export_preview": payload.export_preview,
            "export_dub": payload.export_dub,
            "subtitle_mode": payload.subtitle_mode,
            "subtitle_render_source": payload.subtitle_source,
            "subtitle_font": payload.font_family,
            "subtitle_font_size": payload.font_size,
            "subtitle_color": payload.primary_color,
            "subtitle_outline_color": payload.outline_color,
            "subtitle_outline_width": payload.outline_width,
            "subtitle_position": payload.position,
            "subtitle_margin_v": payload.margin_v,
            "subtitle_bold": payload.bold,
            "bilingual_chinese_position": payload.bilingual_chinese_position,
            "bilingual_english_position": payload.bilingual_english_position,
        },
    )
    session.add(task)
    session.commit()

    report = json.loads(result.artifacts.report_path.read_text(encoding="utf-8"))
    return {
        "preview_video_path": str(result.artifacts.preview_video_path) if result.artifacts.preview_video_path else None,
        "dub_video_path": str(result.artifacts.dub_video_path) if result.artifacts.dub_video_path else None,
        "manifest_path": str(result.artifacts.manifest_path),
        "report_path": str(result.artifacts.report_path),
        "report": report,
    }


__all__ = ["router"]
