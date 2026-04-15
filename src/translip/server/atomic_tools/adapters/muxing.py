from __future__ import annotations

from ....utils.ffmpeg import mux_video_with_audio
from ..registry import ToolSpec, register_tool
from ..schemas import MuxingToolRequest
from . import ToolAdapter


class MuxingAdapter(ToolAdapter):
    def validate_params(self, params: dict) -> dict:
        return MuxingToolRequest(**params).model_dump()

    def run(self, params, input_dir, output_dir, on_progress):
        video_path = self.first_input(input_dir, "video_file")
        audio_path = self.first_input(input_dir, "audio_file")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "output.mp4"
        on_progress(10.0, "muxing")
        mux_video_with_audio(
            input_video_path=video_path,
            input_audio_path=audio_path,
            output_path=output_path,
            video_codec=params.get("video_codec", "copy"),
            audio_codec=params.get("audio_codec", "aac"),
            audio_bitrate=params.get("audio_bitrate", "192k"),
        )
        on_progress(95.0, "finalizing")
        return {
            "output_file": output_path.name,
            "video_codec": params.get("video_codec", "copy"),
            "audio_codec": params.get("audio_codec", "aac"),
            "audio_bitrate": params.get("audio_bitrate", "192k"),
        }


register_tool(
    ToolSpec(
        tool_id="muxing",
        name_zh="音视频合并",
        name_en="Video Audio Muxing",
        description_zh="将音频轨合并到视频中生成新的 MP4 文件",
        description_en="Mux an audio track into a video to produce a new MP4 file",
        category="video",
        icon="Clapperboard",
        accept_formats=[".mp4", ".mkv", ".mov", ".wav", ".mp3", ".m4a", ".aac"],
        max_file_size_mb=2000,
        max_files=2,
    ),
    MuxingAdapter,
)
