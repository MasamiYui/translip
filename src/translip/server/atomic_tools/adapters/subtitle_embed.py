from __future__ import annotations

from ....utils.ffmpeg import embed_soft_subtitle
from ..registry import ToolSpec, register_tool
from ..schemas import SubtitleEmbedToolRequest
from . import ToolAdapter


class SubtitleEmbedAdapter(ToolAdapter):
    def validate_params(self, params: dict) -> dict:
        return SubtitleEmbedToolRequest(**params).model_dump()

    def run(self, params, input_dir, output_dir, on_progress):
        video_path = self.first_input(input_dir, "video_file")
        subtitle_path = self.first_input(input_dir, "subtitle_file")
        container = params.get("container", "mp4")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"output.{container}"

        on_progress(15.0, "embedding")
        embed_soft_subtitle(
            input_video_path=video_path,
            subtitle_path=subtitle_path,
            output_path=output_path,
            container=container,
            subtitle_language=params.get("subtitle_language", "und"),
        )
        on_progress(95.0, "finalizing")
        return {
            "output_file": output_path.name,
            "container": container,
        }


register_tool(
    ToolSpec(
        tool_id="subtitle-embed",
        name_zh="字幕封装（软字幕）",
        name_en="Embed Subtitles (Soft)",
        description_zh="将 SRT/ASS 字幕作为可开关的软字幕轨封装进视频，不重新编码画面",
        description_en="Embed an SRT/ASS subtitle as a toggleable soft track without re-encoding video",
        category="video",
        icon="Subtitles",
        accept_formats=[".mp4", ".mkv", ".mov", ".srt", ".ass"],
        max_file_size_mb=4096,
        max_files=2,
    ),
    SubtitleEmbedAdapter,
)
