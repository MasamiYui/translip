from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path as PathParam
from pydantic import BaseModel, Field
from sqlmodel import Session

from ...delivery.runner import export_video
from ...subtitles.preview import SubtitlePreviewRequest, preview_subtitle
from ...types import ExportVideoRequest, SubtitleStyle
from ..database import get_session
from ..models import Task
from ..task_config import replace_task_delivery_config

router = APIRouter(prefix="/api/tasks", tags=["delivery"])


class SubtitlePreviewRequestPayload(BaseModel):
    input_video_path: str | None = Field(default=None, description="预览所用的原始视频路径；为空或文件不存在时回退到任务的输入视频")
    subtitle_path: str = Field(description="字幕文件路径，相对路径会按任务输出根目录解析，绝对路径直接使用")
    output_path: str | None = Field(default=None, description="预览输出视频路径；为空时默认写到任务输出根目录下的 preview/subtitle-preview.mp4")
    font_family: str = Field(default="Noto Sans", description="字幕字体族")
    font_size: int = Field(default=0, description="字幕字号，0 表示按视频分辨率自动取值")
    primary_color: str = Field(default="#FFFFFF", description="字幕主体颜色（十六进制）")
    outline_color: str = Field(default="#000000", description="字幕描边颜色（十六进制）")
    outline_width: float = Field(default=2.0, description="字幕描边宽度")
    position: Literal["top", "bottom"] = Field(default="bottom", description="字幕位置：顶部或底部")
    margin_v: int = Field(default=0, description="字幕垂直边距，0 表示使用默认值")
    bold: bool = Field(default=False, description="字幕是否加粗")
    start_sec: float | None = Field(default=None, description="预览片段起始秒数，为空表示从头开始")
    duration_sec: float = Field(default=10.0, description="预览片段时长（秒）")


class DeliveryComposeRequestPayload(BaseModel):
    subtitle_mode: Literal["none", "chinese_only", "english_only", "bilingual"] = Field(default="none", description="字幕烧录模式：不烧录、仅中文、仅英文或中英双语")
    subtitle_source: Literal["ocr", "asr"] = Field(default="ocr", description="字幕来源：OCR 识别的硬字幕或 ASR 转写结果")
    bilingual_export_strategy: Literal[
        "auto_standard_bilingual",
        "preserve_hard_subtitles_add_english",
        "clean_video_rebuild_bilingual",
    ] = Field(default="auto_standard_bilingual", description="双语导出策略：自动标准双语、保留硬字幕并叠加英文、或在擦除字幕的干净视频上重建双语")
    font_family: str = Field(default="Noto Sans", description="字幕字体族")
    font_size: int = Field(default=0, description="字幕字号，0 表示按视频分辨率自动取值")
    primary_color: str = Field(default="#FFFFFF", description="字幕主体颜色（十六进制）")
    outline_color: str = Field(default="#000000", description="字幕描边颜色（十六进制）")
    outline_width: float = Field(default=2.0, description="字幕描边宽度")
    position: Literal["top", "bottom"] = Field(default="bottom", description="单语字幕位置：顶部或底部")
    margin_v: int = Field(default=0, description="字幕垂直边距，0 表示使用默认值")
    bold: bool = Field(default=False, description="字幕是否加粗")
    bilingual_chinese_position: Literal["top", "bottom"] = Field(default="bottom", description="双语模式下中文字幕的位置")
    bilingual_english_position: Literal["top", "bottom"] = Field(default="top", description="双语模式下英文字幕的位置")
    export_preview: bool = Field(default=True, description="是否导出预览版（不含配音音轨）视频")
    export_dub: bool = Field(default=True, description="是否导出配音版（替换为配音音轨）视频")


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


@router.post("/{task_id}/subtitle-preview", summary="生成字幕预览")
def create_subtitle_preview(
    task_id: Annotated[str, PathParam(description="任务 ID")],
    payload: SubtitlePreviewRequestPayload,
    session: Session = Depends(get_session),
):
    """按给定字幕样式，将一小段字幕烧录到视频上生成预览片段，并返回预览文件路径与实际使用的样式。"""
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


@router.post("/{task_id}/delivery-compose", summary="合成导出视频")
def compose_delivery(
    task_id: Annotated[str, PathParam(description="任务 ID")],
    payload: DeliveryComposeRequestPayload,
    session: Session = Depends(get_session),
):
    """执行 task-g 导出：按所选字幕模式与来源混流生成预览版/配音版视频，并将本次交付配置写回任务记录，返回产物路径与导出报告。"""
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
            bilingual_export_strategy=payload.bilingual_export_strategy,
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
            "bilingual_export_strategy": payload.bilingual_export_strategy,
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
