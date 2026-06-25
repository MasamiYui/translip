from __future__ import annotations

from pathlib import Path
from typing import Any

from ....orchestration.subprocess_runner import StageSubprocessError, run_stage_command
from ....utils.ffmpeg import ffmpeg_binary, probe_media, probe_video_resolution
from ..cancellation import cancel_checker
from ..ffmpeg_progress import (
    describe_ffmpeg_failure,
    parse_out_time_seconds,
    progress_percent,
)
from ..registry import ToolSpec, register_tool
from ..schemas import VideoTrimToolRequest
from . import ToolAdapter

# Re-encode quality presets for the accurate path (crf, x264 preset), mirroring
# the watermark tool's balanced/high split.
_QUALITY_PRESETS: dict[str, tuple[int, str]] = {
    "balanced": (18, "medium"),
    "high": (16, "slow"),
}


def _format_seconds(value: float) -> str:
    """ffmpeg accepts plain fractional seconds for -ss / -t."""
    return f"{float(value):.3f}"


def compute_effective_duration(
    start_sec: float, end_sec: float | None, duration_sec: float | None
) -> float | None:
    """Resolve the output window length (seconds) from start + end/duration.

    Returns ``None`` when neither bound is given (the trim then runs to the end of
    the file). ``end_sec`` and ``duration_sec`` are mutually exclusive — the schema
    enforces it — so at most one branch contributes here.
    """
    if duration_sec is not None:
        return float(duration_sec)
    if end_sec is not None:
        return max(0.0, float(end_sec) - float(start_sec))
    return None


def build_trim_command(
    *,
    ffmpeg: str,
    input_path: Path,
    output_path: Path,
    mode: str,
    start_sec: float,
    duration_sec: float | None,
    container: str,
    crf: int,
    preset: str,
) -> list[str]:
    """Full ffmpeg argv for cutting ``[start, start+duration)`` into one file.

    ``-ss`` sits *before* ``-i`` (fast input seek — even the accurate path then
    only decodes from the preceding keyframe, not from 0), and the window length
    is always expressed as an output-side ``-t`` duration, never ``-to``: ``-to``
    combined with input seeking is interpreted inconsistently across ffmpeg
    versions, whereas ``-t`` is unambiguously the output duration.
    """
    cmd: list[str] = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
    if start_sec > 0:
        cmd += ["-ss", _format_seconds(start_sec)]
    cmd += ["-i", str(input_path)]
    if duration_sec is not None and duration_sec > 0:
        cmd += ["-t", _format_seconds(duration_sec)]
    if mode == "fast":
        # Stream copy: lossless and near-instant, but a copied cut can only begin
        # on a keyframe, so the real start snaps to the keyframe at/just before
        # ``start_sec``. Keep every stream and rebase timestamps to zero.
        cmd += ["-map", "0", "-c", "copy", "-avoid_negative_ts", "make_zero"]
    else:
        # Re-encode the primary video (+ first audio if present — the ``?`` makes
        # the audio map optional so silent/video-only sources don't error) for a
        # frame-accurate cut.
        cmd += [
            "-map", "0:v:0",
            "-map", "0:a:0?",
            "-c:v", "libx264",
            "-preset", preset,
            "-crf", str(crf),
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
        ]
    if container == "mp4":
        cmd += ["-movflags", "+faststart"]
    cmd += ["-progress", "pipe:1", "-nostats", str(output_path)]
    return cmd


class VideoTrimAdapter(ToolAdapter):
    def validate_params(self, params: dict) -> dict:
        return VideoTrimToolRequest(**params).model_dump()

    def run(self, params, input_dir, output_dir, on_progress):
        video_path = self.first_input(input_dir, "file")
        output_dir.mkdir(parents=True, exist_ok=True)
        container = params.get("output_format", "mp4")
        output_path = output_dir / f"clip.{container}"

        start_sec = float(params.get("start_sec", 0.0) or 0.0)
        effective_duration = compute_effective_duration(
            start_sec, params.get("end_sec"), params.get("duration_sec")
        )
        mode = params.get("mode", "accurate")
        crf, preset = _QUALITY_PRESETS.get(
            params.get("quality", "balanced"), _QUALITY_PRESETS["balanced"]
        )

        on_progress(3.0, "probing")
        # Progress is measured against the OUTPUT length: the clip duration when
        # bounded, otherwise whatever remains of the source after the start.
        progress_total = effective_duration
        if progress_total is None:
            source_duration = self._probe_duration(video_path)
            if source_duration is not None:
                progress_total = max(0.0, source_duration - start_sec)

        command = build_trim_command(
            ffmpeg=ffmpeg_binary(),
            input_path=video_path,
            output_path=output_path,
            mode=mode,
            start_sec=start_sec,
            duration_sec=effective_duration,
            container=container,
            crf=crf,
            preset=preset,
        )
        running_step = "trimming" if mode == "fast" else "encoding"
        on_progress(10.0, running_step)

        def _forward_progress(line: str) -> None:
            seconds = parse_out_time_seconds(line)
            if seconds is not None:
                on_progress(progress_percent(seconds, progress_total), running_step)

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
            # ffmpeg exited 0 but produced nothing. By far the most common cause
            # is a trim window that falls outside the source duration; we surface
            # the log path so the rarer causes (disk/codec/IO) can be diagnosed.
            log_path = output_dir / "ffmpeg.log"
            raise RuntimeError(
                "ffmpeg exited successfully but produced no output file. The most "
                "likely cause is a trim window outside the source duration — verify "
                f"start/end against the video length. See {log_path} for details."
            )

        on_progress(97.0, "finalizing")
        result: dict[str, Any] = {
            "output_file": output_path.name,
            "mode": mode,
            "output_format": container,
            "start_sec": round(start_sec, 3),
            "size_bytes": output_path.stat().st_size,
        }
        if params.get("end_sec") is not None:
            result["end_sec"] = round(float(params["end_sec"]), 3)
        if effective_duration is not None:
            result["requested_duration_sec"] = round(effective_duration, 3)
        result.update(self._probe_output(output_path))
        return result

    @staticmethod
    def _probe_duration(path: Path) -> float | None:
        """Best-effort source duration for a linear progress bar (None if unknown)."""
        try:
            duration = probe_media(path).duration_sec
        except Exception:
            return None
        return duration if duration and duration > 0 else None

    @staticmethod
    def _probe_output(path: Path) -> dict[str, Any]:
        """Summarise the produced clip (actual duration / resolution)."""
        summary: dict[str, Any] = {}
        duration = VideoTrimAdapter._probe_duration(path)
        if duration is not None:
            summary["duration_sec"] = round(duration, 3)
        try:
            width, height = probe_video_resolution(path)
        except Exception:
            return summary
        summary["width"] = width
        summary["height"] = height
        return summary


register_tool(
    ToolSpec(
        tool_id="video-trim",
        name_zh="视频裁剪",
        name_en="Video Trim",
        description_zh="按时间区间截取视频片段，输出新的 MP4/MKV（流复制极速无损，或重新编码精确到帧）",
        description_en="Cut a time range out of a video into a new MP4/MKV — fast lossless stream-copy or frame-accurate re-encode",
        category="video",
        icon="Scissors",
        accept_formats=[".mp4", ".mkv", ".mov", ".avi", ".webm"],
        max_file_size_mb=4096,
        max_files=1,
    ),
    VideoTrimAdapter,
)
