"""Shared helpers for ffmpeg ``-progress pipe:1`` output across atomic-tool adapters.

Adapters that re-encode video (m3u8-to-mp4, watermark, …) run ffmpeg with
``-progress pipe:1`` and stream each ``key=value`` line through
``run_stage_command(on_stdout_line=...)``. These helpers parse the elapsed-time
metric, map it onto the adapter's working band, and turn a subprocess failure's
log tail into a user-actionable message — logic that previously lived only in
the m3u8 adapter.
"""

from __future__ import annotations

from ...orchestration.subprocess_runner import StageSubprocessError

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


def progress_percent(
    seconds: float, total: float | None, *, start: float = 10.0, span: float = 85.0
) -> float:
    """Map elapsed output seconds onto an adapter's ``start``–``start+span`` band.

    With a known total it is linear; for live / unknown-length inputs it eases
    asymptotically toward (but never reaching) the band ceiling so the bar still
    advances.
    """
    if total and total > 0:
        return start + span * min(1.0, seconds / total)
    return start + (span - 5.0) * (1.0 - 1.0 / (1.0 + seconds / 30.0))


def describe_ffmpeg_failure(exc: StageSubprocessError) -> str:
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
