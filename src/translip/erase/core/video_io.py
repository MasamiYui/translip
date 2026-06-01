"""Video frame reading/writing for the eraser.

Reading overlaps decode with inference via a background prefetch thread; writing
pipes raw BGR frames into an ffmpeg ``libx264`` encoder. Audio is copied from the
source and re-muxed onto the cleaned video without re-encoding. Ported and
trimmed from video-subtitle-remover's ``tools/video_io.py`` + ``merge_audio``.
"""
from __future__ import annotations

import queue
import shutil
import subprocess
import threading
import tempfile
from pathlib import Path

import cv2
import numpy as np

from ...utils.ffmpeg import ffmpeg_binary, ffprobe_binary


class FramePrefetcher:
    """Background-thread reader wrapping ``cv2.VideoCapture`` (read/release)."""

    def __init__(self, capture: cv2.VideoCapture, buffer_size: int = 12) -> None:
        self._cap = capture
        self._buffer: queue.Queue = queue.Queue(maxsize=buffer_size)
        self._stopped = False
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def _read_loop(self) -> None:
        while not self._stopped:
            ok, frame = self._cap.read()
            self._buffer.put((ok, frame))
            if not ok:
                break

    def read(self) -> tuple[bool, np.ndarray | None]:
        return self._buffer.get()

    def stop(self) -> None:
        self._stopped = True
        try:
            while not self._buffer.empty():
                self._buffer.get_nowait()
        except queue.Empty:
            pass
        self._thread.join(timeout=5)

    def release(self) -> None:
        self.stop()
        self._cap.release()


class FFmpegVideoWriter:
    """Write BGR frames to ``output_path`` via an ffmpeg libx264 raw pipe.

    ``release()`` raises if the encoder exited non-zero or the pipe broke
    mid-stream, so a failed/truncated encode surfaces as an error (with the
    captured ffmpeg stderr) instead of a silently-corrupt "succeeded" output.
    """

    def __init__(self, output_path: Path, fps: float, size: tuple[int, int], *, crf: int = 18, preset: str = "fast") -> None:
        width, height = size
        command = [
            ffmpeg_binary(),
            "-y",
            "-f", "rawvideo",
            "-vcodec", "rawvideo",
            "-s", f"{width}x{height}",
            "-pix_fmt", "bgr24",
            "-r", str(fps),
            "-i", "-",
            "-an",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-crf", str(crf),
            "-preset", preset,
            "-loglevel", "error",
            str(output_path),
        ]
        # Capture stderr to a temp file (not DEVNULL) so an encode failure is
        # explainable, and not a PIPE (which could deadlock as it fills).
        self._stderr = tempfile.TemporaryFile()
        self._pipe_broken = False
        self._process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=self._stderr)

    def write(self, frame: np.ndarray) -> None:
        if frame.dtype != np.uint8:
            frame = np.clip(frame, 0, 255).astype(np.uint8)
        try:
            assert self._process.stdin is not None
            self._process.stdin.write(frame.tobytes())
        except (BrokenPipeError, ValueError):
            # ffmpeg died early: stop trying to write and flag it for release().
            self._pipe_broken = True

    def release(self) -> None:
        try:
            if self._process.stdin is not None:
                self._process.stdin.close()
        except BrokenPipeError:
            self._pipe_broken = True
        try:
            self._process.wait(timeout=600)
        except subprocess.TimeoutExpired:
            self._process.terminate()
            self._process.wait(timeout=5)
        returncode = self._process.returncode
        self._stderr.seek(0)
        stderr_text = self._stderr.read().decode("utf-8", "replace").strip()
        self._stderr.close()
        if returncode != 0 or self._pipe_broken:
            detail = stderr_text[-2000:] if stderr_text else "(no stderr captured)"
            raise RuntimeError(f"ffmpeg video encoding failed (exit {returncode}): {detail}")


def has_audio_stream(path: Path) -> bool:
    """Whether ``path`` has at least one audio stream (best-effort via ffprobe)."""
    try:
        result = subprocess.run(
            [ffprobe_binary(), "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", str(path)],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return bool(result.stdout.strip())
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return True  # can't probe -> attempt the mux anyway


def stream_copy(source_path: Path, output_path: Path) -> None:
    """Container-copy ``source_path`` to ``output_path`` (no re-encode)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [ffmpeg_binary(), "-y", "-i", str(source_path), "-c", "copy", "-loglevel", "error", str(output_path)],
        check=True,
        stdin=subprocess.DEVNULL,
        timeout=600,
    )


def remux_audio(video_only_path: Path, source_path: Path, output_path: Path) -> bool:
    """Copy the source audio track onto the cleaned (video-only) file.

    Returns True if audio was muxed, False otherwise (the video-only file is
    copied through). A source with no audio is a normal, quiet case; a *failure*
    to mux audio that does exist is logged to stdout (captured into the stage
    log) so it is not silently mistaken for a silent source.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not has_audio_stream(source_path):
        shutil.copy2(video_only_path, output_path)
        return False

    ffmpeg = ffmpeg_binary()
    audio_tmp = Path(tempfile.mkstemp(suffix=".aac")[1])
    try:
        subprocess.run(
            [ffmpeg, "-y", "-i", str(source_path), "-vn", "-acodec", "copy", "-loglevel", "error", str(audio_tmp)],
            check=True,
            stdin=subprocess.DEVNULL,
            timeout=600,
        )
        subprocess.run(
            [
                ffmpeg, "-y",
                "-i", str(video_only_path),
                "-i", str(audio_tmp),
                "-c:v", "copy", "-c:a", "copy",
                "-loglevel", "error",
                str(output_path),
            ],
            check=True,
            stdin=subprocess.DEVNULL,
            timeout=600,
        )
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        print(f"[erase] WARNING: source has audio but re-mux failed ({exc}); delivering video without audio", flush=True)
        shutil.copy2(video_only_path, output_path)
        return False
    finally:
        audio_tmp.unlink(missing_ok=True)


__all__ = ["FramePrefetcher", "FFmpegVideoWriter", "remux_audio", "has_audio_stream", "stream_copy"]
