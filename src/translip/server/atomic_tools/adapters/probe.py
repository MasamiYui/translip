from __future__ import annotations

from ....utils.ffmpeg import probe_media
from ..registry import ToolSpec, register_tool
from ..schemas import ProbeToolRequest
from . import ToolAdapter


class ProbeAdapter(ToolAdapter):
    def validate_params(self, params: dict) -> dict:
        return ProbeToolRequest(**params).model_dump()

    def run(self, params, input_dir, output_dir, on_progress):
        input_file = self.first_input(input_dir, "file")
        on_progress(50.0, "probing")
        info = probe_media(input_file)
        payload = {
            "path": input_file.name,
            "media_type": info.media_type,
            "format_name": info.format_name,
            "duration_sec": info.duration_sec,
            "has_video": info.media_type == "video",
            "has_audio": info.audio_stream_count > 0,
            "audio_streams": info.audio_stream_count,
            "sample_rate": info.sample_rate,
            "channels": info.channels,
        }
        self.write_json(output_dir / "probe.json", payload)
        return payload


register_tool(
    ToolSpec(
        tool_id="probe",
        name_zh="媒体信息探测",
        name_en="Media Probe",
        description_zh="检测音视频文件的格式、时长和编码信息",
        description_en="Inspect media format, duration, and stream metadata",
        category="video",
        icon="ScanSearch",
        accept_formats=[".mp4", ".mkv", ".avi", ".mov", ".wav", ".mp3", ".flac", ".m4a", ".ogg", ".webm", ".ts"],
        max_file_size_mb=2000,
        max_files=1,
    ),
    ProbeAdapter,
)
