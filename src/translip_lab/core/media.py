"""Thin ffmpeg/ffprobe + soundfile helpers (dependency-free media I/O).

Frames are pulled as rawvideo rgb24 straight into numpy (no PIL/opencv needed),
matching the OCR/erase box coordinate space (pixels, top-left origin). Audio is
read mono float64 via soundfile. ffmpeg/ffprobe are expected on PATH (they are a
hard requirement of translip itself).
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(slots=True)
class VideoInfo:
    width: int
    height: int
    fps: float
    duration_sec: float
    nb_frames: int


def _run(cmd: list[str]) -> bytes:
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(cmd[:6])}…\n{proc.stderr.decode('utf-8', 'replace')[:500]}")
    return proc.stdout


def probe_video(path: str | Path) -> VideoInfo:
    out = _run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,avg_frame_rate,nb_frames",
        "-show_entries", "format=duration", "-of", "json", str(path),
    ])
    data = json.loads(out or b"{}")
    stream = (data.get("streams") or [{}])[0]
    width = int(stream.get("width") or 0)
    height = int(stream.get("height") or 0)
    fr = str(stream.get("avg_frame_rate") or "0/1")
    num, _, den = fr.partition("/")
    fps = (float(num) / float(den)) if den and float(den) != 0 else 0.0
    duration = float((data.get("format") or {}).get("duration") or 0.0)
    nb = stream.get("nb_frames")
    nb_frames = int(nb) if nb and str(nb).isdigit() else (int(round(fps * duration)) if fps else 0)
    return VideoInfo(width=width, height=height, fps=fps, duration_sec=duration, nb_frames=nb_frames)


def extract_frame(path: str | Path, t_sec: float, *, width: int | None = None, height: int | None = None) -> np.ndarray:
    """Return one RGB frame (H, W, 3) uint8 at ``t_sec`` seconds."""
    if width is None or height is None:
        info = probe_video(path)
        width, height = info.width, info.height
    if not width or not height:
        raise RuntimeError(f"could not determine video dimensions for {path}")
    out = _run([
        "ffmpeg", "-v", "error", "-ss", f"{max(t_sec, 0.0):.3f}", "-i", str(path),
        "-frames:v", "1", "-pix_fmt", "rgb24", "-f", "rawvideo", "-",
    ])
    expected = width * height * 3
    if len(out) < expected:
        raise RuntimeError(f"short frame read for {path} @ {t_sec}s: {len(out)} < {expected}")
    return np.frombuffer(out[:expected], dtype=np.uint8).reshape(height, width, 3)


def extract_frames(path: str | Path, times: list[float]) -> list[np.ndarray]:
    info = probe_video(path)
    return [extract_frame(path, t, width=info.width, height=info.height) for t in times]


def load_audio(path: str | Path, *, target_sr: int | None = None) -> tuple[np.ndarray, int]:
    """Return (mono float64 samples, sample_rate). Optionally resample."""
    import soundfile as sf

    data, sr = sf.read(str(path), dtype="float64", always_2d=False)
    if data.ndim == 2:
        data = data.mean(axis=1)
    if target_sr is not None and target_sr != sr:
        import librosa

        data = librosa.resample(data, orig_sr=sr, target_sr=target_sr)
        sr = target_sr
    return np.ascontiguousarray(data), sr
