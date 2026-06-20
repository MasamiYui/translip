from __future__ import annotations

from ....orchestration.subprocess_runner import StageSubprocessError, run_stage_command
from ....utils.ffmpeg import (
    build_image_watermark_args,
    build_text_watermark_args,
    ffmpeg_binary,
    probe_media,
)
from ..cancellation import cancel_checker
from ..ffmpeg_progress import (
    describe_ffmpeg_failure,
    parse_out_time_seconds,
    progress_percent,
)
from ..registry import ToolSpec, register_tool
from ..schemas import WatermarkToolRequest
from . import ToolAdapter


class WatermarkAdapter(ToolAdapter):
    def validate_params(self, params: dict) -> dict:
        return WatermarkToolRequest(**params).model_dump()

    def run(self, params, input_dir, output_dir, on_progress):
        video_path = self.first_input(input_dir, "video_file")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "output.mp4"

        crf, preset = (18, "medium") if params.get("quality", "balanced") == "balanced" else (16, "slow")
        mode = params.get("mode", "image")
        position = params.get("position", "bottom-right")

        on_progress(3.0, "probing")
        total_duration = self._probe_duration(video_path)

        if mode == "image":
            wm_path = self.first_input(input_dir, "image_file")
            args = build_image_watermark_args(
                input_video_path=video_path,
                watermark_image_path=wm_path,
                output_path=output_path,
                position=position,
                margin=int(params.get("margin", 24)),
                opacity=float(params.get("opacity", 0.8)),
                scale=float(params.get("scale", 0.15)),
                crf=crf,
                preset=preset,
                progress=True,
            )
        else:
            args = build_text_watermark_args(
                input_video_path=video_path,
                output_path=output_path,
                text=str(params.get("text") or ""),
                position=position,
                margin=int(params.get("margin", 24)),
                font_size=int(params.get("font_size", 36)),
                font_color=str(params.get("font_color", "white")),
                stroke_color=str(params.get("stroke_color", "black@0.6")),
                stroke_width=int(params.get("stroke_width", 2)),
                opacity=float(params.get("opacity", 1.0)),
                crf=crf,
                preset=preset,
                progress=True,
            )

        command = [ffmpeg_binary(), "-hide_banner", "-loglevel", "error", "-nostdin", *args]
        on_progress(10.0, "watermarking")

        def _forward_progress(line: str) -> None:
            seconds = parse_out_time_seconds(line)
            if seconds is not None:
                on_progress(progress_percent(seconds, total_duration), "watermarking")

        try:
            run_stage_command(
                command,
                log_path=output_dir / "ffmpeg.log",
                on_stdout_line=_forward_progress,
                should_cancel=cancel_checker(on_progress),
            )
        except StageSubprocessError as exc:
            raise RuntimeError(describe_ffmpeg_failure(exc)) from exc

        if not output_path.exists() or output_path.stat().st_size == 0:
            raise RuntimeError("ffmpeg produced no output while applying the watermark")

        on_progress(97.0, "finalizing")
        return {
            "output_file": output_path.name,
            "mode": mode,
            "position": position,
        }

    @staticmethod
    def _probe_duration(path) -> float | None:
        """Best-effort source duration for a linear progress bar (None if unknown)."""
        try:
            duration = probe_media(path).duration_sec
        except Exception:
            return None
        return duration if duration and duration > 0 else None


register_tool(
    ToolSpec(
        tool_id="watermark",
        name_zh="水印压制",
        name_en="Watermark Overlay",
        description_zh="将图片或文字水印压制到视频画面中，输出新的 MP4",
        description_en="Burn an image or text watermark into the video frame, producing a new MP4",
        category="video",
        icon="Stamp",
        # Accepts both video and image file uploads — _validate_stored_file
        # checks every uploaded file's suffix against this list.
        accept_formats=[".mp4", ".mkv", ".mov", ".avi", ".png", ".jpg", ".jpeg", ".webp"],
        max_file_size_mb=4096,
        max_files=2,
    ),
    WatermarkAdapter,
)
