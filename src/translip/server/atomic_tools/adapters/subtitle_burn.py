from __future__ import annotations

import re

from ....subtitles.burn import recommend_style, srt_to_ass
from ....utils.ffmpeg import burn_subtitle, probe_video_resolution
from ..registry import ToolSpec, register_tool
from ..schemas import SubtitleBurnToolRequest
from . import ToolAdapter

_CJK_RE = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯]")


def _detect_lang(subtitle_text: str) -> str:
    return "zh" if _CJK_RE.search(subtitle_text) else "en"


class SubtitleBurnAdapter(ToolAdapter):
    def validate_params(self, params: dict) -> dict:
        return SubtitleBurnToolRequest(**params).model_dump()

    def run(self, params, input_dir, output_dir, on_progress):
        video_path = self.first_input(input_dir, "video_file")
        subtitle_path = self.first_input(input_dir, "subtitle_file")
        output_dir.mkdir(parents=True, exist_ok=True)

        on_progress(5.0, "probing")
        width, height = probe_video_resolution(video_path)

        # An ASS upload already carries its own styling; only SRT needs a style
        # pass (font/size/position) before libass can burn it.
        if subtitle_path.suffix.lower() == ".ass":
            ass_path = subtitle_path
        else:
            lang = params.get("lang", "auto")
            if lang == "auto":
                lang = _detect_lang(subtitle_path.read_text(encoding="utf-8", errors="ignore"))
            elif lang == "cjk":
                lang = "zh"
            else:
                lang = "en"
            style = recommend_style(width, height, lang=lang, position=params.get("position", "bottom"))
            ass_path = output_dir / "subtitle.ass"
            srt_to_ass(subtitle_path, style, ass_path, play_res=(width, height))

        on_progress(15.0, "burning")
        crf, preset = (18, "medium") if params.get("quality", "balanced") == "balanced" else (16, "slow")
        output_path = output_dir / "output.mp4"
        burn_subtitle(
            input_video_path=video_path,
            subtitle_path=ass_path,
            output_path=output_path,
            crf=crf,
            preset=preset,
        )
        on_progress(95.0, "finalizing")
        return {
            "output_file": output_path.name,
            "width": width,
            "height": height,
        }


register_tool(
    ToolSpec(
        tool_id="subtitle-burn",
        name_zh="字幕烧录（硬字幕）",
        name_en="Burn Subtitles (Hardsub)",
        description_zh="将 SRT/ASS 字幕烧录进视频画面，输出带硬字幕的 MP4",
        description_en="Burn an SRT/ASS subtitle into the video frame, producing a hardsubbed MP4",
        category="video",
        icon="Captions",
        accept_formats=[".mp4", ".mkv", ".mov", ".srt", ".ass"],
        max_file_size_mb=4096,
        max_files=2,
    ),
    SubtitleBurnAdapter,
)
