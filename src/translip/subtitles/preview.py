from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import DEFAULT_SUBTITLE_PREVIEW_DURATION_SEC
from ..types import SubtitleStyle
from ..utils.ffmpeg import burn_subtitle_preview, probe_video_resolution
from ..utils.files import ensure_directory
from .burn import first_subtitle_time, recommend_style, srt_to_ass


@dataclass(frozen=True, slots=True)
class SubtitlePreviewRequest:
    input_video_path: Path | str
    subtitle_path: Path | str
    output_path: Path | str | None = None
    style: SubtitleStyle | None = None
    start_sec: float | None = None
    duration_sec: float = DEFAULT_SUBTITLE_PREVIEW_DURATION_SEC


@dataclass(frozen=True, slots=True)
class SubtitlePreviewResult:
    preview_path: Path
    style_used: SubtitleStyle
    start_sec: float
    duration_sec: float


def preview_subtitle(request: SubtitlePreviewRequest) -> SubtitlePreviewResult:
    video_path = Path(request.input_video_path).expanduser().resolve()
    srt_path = Path(request.subtitle_path).expanduser().resolve()

    width, height = probe_video_resolution(video_path)
    style = request.style or recommend_style(width, height)
    if style.font_size == 0 or style.margin_v == 0:
        auto = recommend_style(width, height, position=style.position)
        if style.font_size == 0:
            style = SubtitleStyle(
                font_family=style.font_family,
                font_size=auto.font_size,
                primary_color=style.primary_color,
                outline_color=style.outline_color,
                outline_width=style.outline_width,
                shadow_depth=style.shadow_depth,
                bold=style.bold,
                position=style.position,
                margin_v=style.margin_v if style.margin_v != 0 else auto.margin_v,
                margin_h=style.margin_h,
                alignment=style.alignment,
            )
        if style.margin_v == 0:
            style = SubtitleStyle(
                font_family=style.font_family,
                font_size=style.font_size,
                primary_color=style.primary_color,
                outline_color=style.outline_color,
                outline_width=style.outline_width,
                shadow_depth=style.shadow_depth,
                bold=style.bold,
                position=style.position,
                margin_v=auto.margin_v,
                margin_h=style.margin_h,
                alignment=style.alignment,
            )

    start_sec = request.start_sec
    if start_sec is None:
        start_sec = first_subtitle_time(srt_path)

    output_path = (
        Path(request.output_path).expanduser().resolve()
        if request.output_path
        else video_path.parent / "subtitle_preview.mp4"
    )
    ensure_directory(output_path.parent)

    work_dir = output_path.parent / ".subtitle-preview-work"
    ensure_directory(work_dir)
    ass_path = work_dir / "preview.ass"
    srt_to_ass(srt_path, style, ass_path, play_res=(width, height))

    burn_subtitle_preview(
        input_video_path=video_path,
        subtitle_path=ass_path,
        output_path=output_path,
        start_sec=start_sec,
        duration_sec=request.duration_sec,
    )

    return SubtitlePreviewResult(
        preview_path=output_path,
        style_used=style,
        start_sec=start_sec,
        duration_sec=request.duration_sec,
    )


__all__ = ["SubtitlePreviewRequest", "SubtitlePreviewResult", "preview_subtitle"]
