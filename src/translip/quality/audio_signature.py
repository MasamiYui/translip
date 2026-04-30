from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

MIN_PITCH_HZ = 70.0
MAX_PITCH_HZ = 320.0
FRAME_SEC = 0.04
HOP_SEC = 0.02


@dataclass(slots=True)
class AudioSignature:
    path: str
    duration_sec: float
    rms: float
    pitch_hz: float | None
    pitch_class: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "duration_sec": round(self.duration_sec, 3),
            "rms": round(self.rms, 6),
            "pitch_hz": round(self.pitch_hz, 2) if self.pitch_hz is not None else None,
            "pitch_class": self.pitch_class,
        }


def voice_signature(audio_path: Path | str) -> AudioSignature:
    path = Path(audio_path).expanduser().resolve()
    waveform, sample_rate = sf.read(path, dtype="float32", always_2d=False)
    if waveform.ndim == 2:
        waveform = waveform.mean(axis=1)
    waveform = np.asarray(waveform, dtype=np.float32)
    duration_sec = float(len(waveform) / sample_rate) if sample_rate > 0 else 0.0
    rms = float(np.sqrt(np.mean(np.square(waveform)))) if waveform.size else 0.0
    pitch_hz = _median_pitch_hz(waveform, sample_rate)
    return AudioSignature(
        path=str(path),
        duration_sec=duration_sec,
        rms=rms,
        pitch_hz=pitch_hz,
        pitch_class=classify_pitch(pitch_hz),
    )


def classify_pitch(pitch_hz: float | None) -> str:
    if pitch_hz is None or pitch_hz <= 0.0:
        return "unknown"
    if pitch_hz < 145.0:
        return "low"
    if pitch_hz <= 215.0:
        return "mid"
    return "high"


def pitch_class_distance(left: str, right: str) -> int | None:
    order = {"low": 0, "mid": 1, "high": 2}
    if left not in order or right not in order:
        return None
    return abs(order[left] - order[right])


def _median_pitch_hz(waveform: np.ndarray, sample_rate: int) -> float | None:
    if sample_rate <= 0 or waveform.size < int(sample_rate * FRAME_SEC):
        return None
    frame_size = max(1, int(round(sample_rate * FRAME_SEC)))
    hop_size = max(1, int(round(sample_rate * HOP_SEC)))
    min_lag = max(1, int(round(sample_rate / MAX_PITCH_HZ)))
    max_lag = min(frame_size - 1, int(round(sample_rate / MIN_PITCH_HZ)))
    if max_lag <= min_lag:
        return None
    pitches: list[float] = []
    window = np.hanning(frame_size).astype(np.float32)
    for start in range(0, waveform.size - frame_size + 1, hop_size):
        frame = waveform[start : start + frame_size].astype(np.float32)
        frame = frame - float(np.mean(frame))
        energy = float(np.sqrt(np.mean(np.square(frame))))
        if energy < 1e-4:
            continue
        frame = frame * window
        corr = np.correlate(frame, frame, mode="full")[frame_size - 1 :]
        if corr[0] <= 1e-8:
            continue
        search = corr[min_lag : max_lag + 1]
        if search.size == 0:
            continue
        lag = int(np.argmax(search)) + min_lag
        confidence = float(corr[lag] / corr[0])
        if confidence < 0.25:
            continue
        pitches.append(float(sample_rate / lag))
    if not pitches:
        return None
    return float(np.median(np.asarray(pitches, dtype=np.float32)))


__all__ = ["AudioSignature", "classify_pitch", "pitch_class_distance", "voice_signature"]
