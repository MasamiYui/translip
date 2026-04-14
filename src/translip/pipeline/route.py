from __future__ import annotations

import math
from pathlib import Path

import librosa
import numpy as np

from ..types import RouteDecision, SeparationRequest


def _safe_ratio(numerator: float, denominator: float) -> float:
    if math.isclose(denominator, 0.0):
        return 0.0
    return numerator / denominator


def auto_route(wav_path: Path) -> RouteDecision:
    signal, sample_rate = librosa.load(wav_path, sr=22_050, mono=True, duration=90.0)
    if signal.size == 0:
        return RouteDecision(route="dialogue", reason="empty-signal", metrics={})

    harmonic, _ = librosa.effects.hpss(signal)
    chroma = librosa.feature.chroma_stft(y=signal, sr=sample_rate)
    onset_strength = librosa.onset.onset_strength(y=signal, sr=sample_rate)
    tempo = float(librosa.feature.tempo(y=signal, sr=sample_rate, aggregate=np.median)[0])
    rms = float(np.sqrt(np.mean(signal**2)))
    harmonic_rms = float(np.sqrt(np.mean(harmonic**2)))
    chroma_peak = float(np.mean(np.max(chroma, axis=0)))
    onset_std = float(np.std(onset_strength))
    harmonic_ratio = float(_safe_ratio(harmonic_rms, rms))

    score = 0
    if tempo >= 72.0:
        score += 1
    if chroma_peak >= 0.60:
        score += 1
    if harmonic_ratio >= 0.50:
        score += 1
    if onset_std >= 7.5:
        score += 1

    route = "music" if score >= 2 else "dialogue"
    return RouteDecision(
        route=route,
        reason="heuristic-auto-router",
        metrics={
            "tempo": round(tempo, 3),
            "chroma_peak": round(chroma_peak, 3),
            "harmonic_ratio": round(harmonic_ratio, 3),
            "onset_std": round(onset_std, 3),
            "score": float(score),
        },
    )


def resolve_route(request: SeparationRequest, wav_path: Path) -> RouteDecision:
    if request.mode in {"music", "dialogue"}:
        return RouteDecision(route=request.mode, reason="manual-mode", metrics={})
    return auto_route(wav_path)

