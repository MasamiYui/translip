from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from ....orchestration.subprocess_runner import StageSubprocessError, run_stage_command
from ....utils.ffmpeg import ffmpeg_binary, ffprobe_binary
from ..cancellation import cancel_checker
from ..registry import ToolSpec, register_tool
from ..schemas import M3u8ToMp4ToolRequest
from . import ToolAdapter

# Protocol whitelists. A remote playlist must NOT be allowed to reach `file:`
# (a hostile/compromised playlist could otherwise exfiltrate local files via a
# file:// segment URI), whereas a saved local .m3u8 legitimately needs `file`
# alongside the http/crypto protocols to resolve its segments and AES keys.
_REMOTE_PROTOCOLS = "crypto,data,http,https,tcp,tls,httpproxy"
_LOCAL_PROTOCOLS = "file,crypto,data,http,https,tcp,tls,httpproxy"

# ffmpeg -progress writes one key=value per line; these are the metric keys (as
# opposed to a real error line) we strip when summarising a failure's log tail.
_PROGRESS_LINE_PREFIXES = (
    "frame=",
    "fps=",
    "stream_",
    "bitrate=",
    "total_size=",
    "out_time",
    "dup_frames=",
    "drop_frames=",
    "speed=",
    "progress=",
)


def _format_seconds(value: float) -> str:
    """ffmpeg accepts plain fractional seconds for -ss / -t."""
    return f"{float(value):.3f}"


def _build_header_block(referer: str | None, headers: str | None) -> str | None:
    """Assemble ffmpeg's ``-headers`` value (CRLF-terminated lines) or None."""
    lines: list[str] = []
    if referer and referer.strip():
        lines.append(f"Referer: {referer.strip()}")
    for raw in (headers or "").splitlines():
        line = raw.strip()
        if line:
            lines.append(line)
    if not lines:
        return None
    return "".join(f"{line}\r\n" for line in lines)


def build_input_options(
    *,
    is_local: bool,
    start_sec: float | None = None,
    user_agent: str | None = None,
    referer: str | None = None,
    headers: str | None = None,
) -> list[str]:
    """ffmpeg/ffprobe *input* options (everything that must precede ``-i``)."""
    opts: list[str] = [
        "-protocol_whitelist",
        _LOCAL_PROTOCOLS if is_local else _REMOTE_PROTOCOLS,
    ]
    if is_local:
        # A saved .m3u8 may reference segments with non-standard extensions.
        opts += ["-allowed_extensions", "ALL"]
    if user_agent and user_agent.strip():
        opts += ["-user_agent", user_agent.strip()]
    header_block = _build_header_block(referer, headers)
    if header_block is not None:
        opts += ["-headers", header_block]
    # Input seeking (before -i) keeps remuxing fast even on long VODs.
    if start_sec is not None and start_sec > 0:
        opts += ["-ss", _format_seconds(start_sec)]
    return opts


def build_ffmpeg_command(
    *,
    ffmpeg: str,
    input_arg: str,
    is_local: bool,
    params: dict[str, Any],
    output_path: Path,
) -> list[str]:
    """Full ffmpeg argv to fetch the HLS stream and write a single MP4/MKV."""
    mode = params.get("mode", "copy")
    container = params.get("output_format", "mp4")
    cmd: list[str] = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
    cmd += build_input_options(
        is_local=is_local,
        start_sec=params.get("start_sec"),
        user_agent=params.get("user_agent"),
        referer=params.get("referer"),
        headers=params.get("headers"),
    )
    cmd += ["-i", input_arg]
    duration = params.get("duration_limit_sec")
    if duration is not None and float(duration) > 0:
        cmd += ["-t", _format_seconds(float(duration))]
    if mode == "transcode":
        cmd += [
            "-c:v",
            "libx264",
            "-preset",
            str(params.get("preset", "veryfast")),
            "-crf",
            str(int(params.get("crf", 20))),
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            str(params.get("audio_bitrate", "192k")),
        ]
    else:
        # Remux: copy the auto-selected streams untouched (fast, lossless). The
        # mp4 muxer auto-inserts the aac_adtstoasc bitstream filter for AAC.
        cmd += ["-c", "copy"]
    if container == "mp4":
        cmd += ["-movflags", "+faststart"]
    cmd += ["-progress", "pipe:1", "-nostats", str(output_path)]
    return cmd


def build_ffprobe_command(
    *, ffprobe: str, input_arg: str, input_options: list[str]
) -> list[str]:
    return [
        ffprobe,
        "-hide_banner",
        "-loglevel",
        "error",
        *input_options,
        "-show_entries",
        "format=duration",
        "-show_entries",
        "stream=codec_type,codec_name,width,height",
        "-of",
        "json",
        input_arg,
    ]


def parse_out_time_seconds(line: str) -> float | None:
    """Pull elapsed output seconds from an ffmpeg ``out_time_us=`` progress line."""
    if not line.startswith("out_time_us="):
        return None
    value = line.split("=", 1)[1].strip()
    if not value or value == "N/A":
        return None
    try:
        return int(value) / 1_000_000.0
    except ValueError:
        return None


def progress_percent(seconds: float, total: float | None) -> float:
    """Map elapsed output seconds onto the adapter's 10–95% working band.

    With a known total it is linear; for live / unknown-length streams it eases
    asymptotically toward (but never reaching) 95% so the bar still advances.
    """
    if total and total > 0:
        return 10.0 + 85.0 * min(1.0, seconds / total)
    return 10.0 + 80.0 * (1.0 - 1.0 / (1.0 + seconds / 30.0))


def _describe_ffmpeg_failure(exc: StageSubprocessError) -> str:
    """Turn the raw subprocess error into something a user can act on.

    StageSubprocessError.__str__ only echoes the command; the real reason (403,
    404, "Invalid data", unsupported codec…) lives in the captured log tail, so
    surface that — minus the -progress metric spam — as the job error message.
    """
    meaningful = [
        line
        for line in (exc.tail or [])
        if line and not line.startswith(_PROGRESS_LINE_PREFIXES)
    ]
    detail = (meaningful or list(exc.tail or []))[-4:]
    message = "; ".join(detail).strip()
    if message:
        return f"ffmpeg failed (exit {exc.returncode}): {message}"
    return f"ffmpeg failed with exit code {exc.returncode}"


def _find_playlist(input_dir: Path) -> Path:
    """Locate the uploaded .m3u8 inside its materialised slot directory."""
    playlist_dir = input_dir / "playlist_file"
    base = playlist_dir if playlist_dir.exists() else input_dir
    candidates = sorted(p for p in base.rglob("*.m3u8") if p.is_file())
    if not candidates:
        candidates = sorted(p for p in base.rglob("*") if p.is_file())
    if not candidates:
        raise RuntimeError("No uploaded .m3u8 playlist was found")
    return candidates[0]


def _safe_output_name(name: str | None, source_label: str, container: str) -> str:
    """Derive a filesystem-safe ``<stem>.<container>`` output filename."""
    stem = (name or "").strip()
    if not stem:
        base = source_label.split("?", 1)[0].rstrip("/")
        base = base.rsplit("/", 1)[-1]
        stem = Path(base).stem or "output"
    stem = Path(stem).name  # strip any directory component
    stem = "".join(ch for ch in stem if ch.isalnum() or ch in (" ", "-", "_", ".")).strip()
    stem = stem or "output"
    if stem.lower().endswith(f".{container}"):
        stem = stem[: -(len(container) + 1)] or "output"
    return f"{stem}.{container}"


def _probe_duration(input_arg: str, input_options: list[str]) -> float | None:
    """Best-effort total duration for progress; None for live/unknown streams."""
    cmd = build_ffprobe_command(
        ffprobe=ffprobe_binary(), input_arg=input_arg, input_options=input_options
    )
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if proc.returncode != 0:
            return None
        data = json.loads(proc.stdout or "{}")
        raw = (data.get("format") or {}).get("duration")
        if raw in (None, "", "N/A"):
            return None
        value = float(raw)
        return value if value > 0 else None
    except Exception:
        return None


def _probe_output(path: Path) -> dict[str, Any]:
    """Summarise the produced file (duration / resolution / codecs)."""
    try:
        proc = subprocess.run(
            [
                ffprobe_binary(),
                "-hide_banner",
                "-loglevel",
                "error",
                "-show_entries",
                "format=duration",
                "-show_entries",
                "stream=codec_type,codec_name,width,height",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if proc.returncode != 0:
            return {}
        data = json.loads(proc.stdout or "{}")
    except Exception:
        return {}

    summary: dict[str, Any] = {}
    raw = (data.get("format") or {}).get("duration")
    if raw not in (None, "", "N/A"):
        try:
            summary["duration_sec"] = round(float(raw), 3)
        except ValueError:
            pass
    for stream in data.get("streams", []):
        kind = stream.get("codec_type")
        if kind == "video" and "video_codec" not in summary:
            summary["video_codec"] = stream.get("codec_name")
            if stream.get("width"):
                summary["width"] = int(stream["width"])
            if stream.get("height"):
                summary["height"] = int(stream["height"])
        elif kind == "audio" and "audio_codec" not in summary:
            summary["audio_codec"] = stream.get("codec_name")
    return summary


class M3u8ToMp4Adapter(ToolAdapter):
    def validate_params(self, params: dict) -> dict:
        return M3u8ToMp4ToolRequest(**params).model_dump()

    def run(self, params, input_dir, output_dir, on_progress):
        output_dir.mkdir(parents=True, exist_ok=True)

        if params.get("playlist_file_id"):
            input_path = _find_playlist(input_dir)
            input_arg = str(input_path)
            is_local = True
            source_label = input_path.name
            source_type = "file"
        else:
            input_arg = str(params.get("url") or "").strip()
            if not input_arg:
                raise RuntimeError("No m3u8 URL or uploaded playlist provided")
            is_local = False
            source_label = input_arg
            source_type = "url"

        on_progress(3.0, "probing")
        probe_options = build_input_options(
            is_local=is_local,
            user_agent=params.get("user_agent"),
            referer=params.get("referer"),
            headers=params.get("headers"),
        )
        total_duration = _probe_duration(input_arg, probe_options)

        container = params.get("output_format", "mp4")
        output_path = output_dir / _safe_output_name(
            params.get("output_name"), source_label, container
        )

        command = build_ffmpeg_command(
            ffmpeg=ffmpeg_binary(),
            input_arg=input_arg,
            is_local=is_local,
            params=params,
            output_path=output_path,
        )
        running_step = "transcoding" if params.get("mode") == "transcode" else "downloading"
        on_progress(10.0, running_step)

        def _forward_progress(line: str) -> None:
            seconds = parse_out_time_seconds(line)
            if seconds is None:
                return
            on_progress(progress_percent(seconds, total_duration), running_step)

        try:
            run_stage_command(
                command,
                log_path=output_dir / "ffmpeg.log",
                on_stdout_line=_forward_progress,
                should_cancel=cancel_checker(on_progress),
            )
        except StageSubprocessError as exc:
            raise RuntimeError(_describe_ffmpeg_failure(exc)) from exc

        if not output_path.exists() or output_path.stat().st_size == 0:
            raise RuntimeError(
                "ffmpeg produced no output. The stream may be empty, geo-blocked, "
                "or require headers/cookies — set User-Agent / Referer / headers and retry."
            )

        on_progress(97.0, "finalizing")
        result: dict[str, Any] = {
            "output_file": output_path.name,
            "source_type": source_type,
            "source": source_label,
            "mode": params.get("mode", "copy"),
            "output_format": container,
            "size_bytes": output_path.stat().st_size,
        }
        result.update(_probe_output(output_path))
        return result


register_tool(
    ToolSpec(
        tool_id="m3u8-to-mp4",
        name_zh="M3U8 转 MP4",
        name_en="M3U8 to MP4",
        description_zh="下载并转换 HLS（.m3u8）直播/点播流为单个 MP4，支持加密流、自定义请求头与转码",
        description_en="Download an HLS (.m3u8) stream into a single MP4 — encrypted streams, custom headers, optional transcode",
        category="video",
        icon="FileDown",
        accept_formats=[".m3u8"],
        max_file_size_mb=20,
        max_files=1,
    ),
    M3u8ToMp4Adapter,
)
