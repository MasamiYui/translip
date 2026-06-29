#!/usr/bin/env python3
"""Generate the 6 bundled commentary BGM placeholder WAVs.

These placeholders are short, simple, **algorithmically synthesised** loops
(layered sine waves + amplitude envelopes) — they have **no third-party
copyright**, are intentionally low-fi, and are meant only to give the BGM
plumbing something to play with during local learning / testing. Replace the
WAVs under ``assets/bgm/`` with licensed tracks for any real-world work.

Usage::

    python scripts/build_bgm_placeholders.py

Re-running overwrites the files in-place; the output is deterministic.
"""

from __future__ import annotations

import math
import struct
import sys
import wave
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "assets" / "bgm"

SAMPLE_RATE = 44_100
DURATION_SEC = 30.0
AMPLITUDE = 0.18  # leave headroom — the renderer attenuates further before mixing


def _sin(t: float, freq: float) -> float:
    return math.sin(2.0 * math.pi * freq * t)


def _envelope(t: float, duration: float, attack: float = 0.5, release: float = 0.5) -> float:
    """Linear fade-in / fade-out envelope."""
    if t < attack:
        return t / max(attack, 1e-6)
    if t > duration - release:
        return max(0.0, (duration - t) / max(release, 1e-6))
    return 1.0


def _tremolo(t: float, rate_hz: float, depth: float) -> float:
    """LFO that swings between (1-depth) and 1.0."""
    return 1.0 - depth * 0.5 * (1.0 - _sin(t, rate_hz))


def _heartbeat(t: float, bpm: float) -> float:
    """Two short pulses per beat, decaying — gives the BGM a pulse-like motion."""
    beat_period = 60.0 / bpm
    phase = (t % beat_period) / beat_period
    if phase < 0.05:
        env = math.exp(-phase * 60.0)
    elif 0.12 < phase < 0.17:
        env = 0.7 * math.exp(-(phase - 0.12) * 60.0)
    else:
        env = 0.0
    return env


def _arpeggio(t: float, root_hz: float, intervals: list[float], rate_hz: float) -> float:
    """Sequential pluck across ``intervals`` (semitone offsets), one note per ``1/rate_hz``."""
    step_dur = 1.0 / rate_hz
    idx = int(t / step_dur) % len(intervals)
    freq = root_hz * (2.0 ** (intervals[idx] / 12.0))
    phase = (t % step_dur) / step_dur
    note_env = math.exp(-phase * 4.0)
    return note_env * _sin(t, freq)


def _sample_suspense(t: float) -> float:
    # Low drone (55 Hz + 110 Hz fifth) + a slow heartbeat pulse on 220 Hz.
    drone = 0.6 * _sin(t, 55.0) + 0.3 * _sin(t, 82.5)
    pulse = 0.5 * _heartbeat(t, 48.0) * _sin(t, 220.0)
    breath = _tremolo(t, 0.2, 0.4)
    return (drone * breath + pulse) * 0.5


def _sample_hype(t: float) -> float:
    # Rising tonic+fifth chord with a 4/4 kick pulse.
    fade_in = min(1.0, t / 8.0)
    chord = (
        0.4 * _sin(t, 110.0)
        + 0.3 * _sin(t, 165.0)
        + 0.2 * _sin(t, 220.0)
        + 0.15 * _sin(t, 330.0)
    )
    kick_phase = (t % 0.5) / 0.5
    kick = 0.4 * math.exp(-kick_phase * 12.0) * _sin(t, 65.0)
    return (chord * fade_in + kick) * 0.55


def _sample_warm(t: float) -> float:
    # Major triad pad (C4 / E4 / G4) with gentle 0.15 Hz LFO.
    pad = 0.35 * _sin(t, 261.6) + 0.30 * _sin(t, 329.6) + 0.25 * _sin(t, 392.0)
    sub = 0.2 * _sin(t, 130.8)
    return (pad + sub) * _tremolo(t, 0.15, 0.25) * 0.6


def _sample_documentary(t: float) -> float:
    # Very restrained: single low pad + airy fifth, no rhythm.
    pad = 0.3 * _sin(t, 196.0) + 0.2 * _sin(t, 293.7)
    air = 0.08 * _sin(t, 587.3) * _tremolo(t, 0.07, 0.5)
    return (pad + air) * 0.4


def _sample_comedy(t: float) -> float:
    # Major arpeggio bouncing through 1-3-5-3 at 6 notes/sec.
    notes = _arpeggio(t, 261.6, [0.0, 4.0, 7.0, 4.0], 6.0)
    bass_phase = (t % 0.5) / 0.5
    bass = 0.25 * math.exp(-bass_phase * 6.0) * _sin(t, 65.4)
    return (notes * 0.45 + bass) * 0.6


def _sample_action(t: float) -> float:
    # Driving 16th-note pulse on a minor root + offbeat snap.
    pulse_phase = (t % 0.125) / 0.125
    pulse = 0.5 * math.exp(-pulse_phase * 8.0) * _sin(t, 110.0)
    snare_phase = ((t + 0.25) % 0.5) / 0.5
    snare = 0.3 * math.exp(-snare_phase * 12.0) * (_sin(t, 1500.0) - _sin(t, 2400.0))
    drone = 0.2 * _sin(t, 55.0)
    return (pulse + snare * 0.4 + drone) * 0.55


SAMPLERS = {
    "bgm-suspense-dark.wav": _sample_suspense,
    "bgm-epic-hype.wav": _sample_hype,
    "bgm-emotional-warm.wav": _sample_warm,
    "bgm-documentary-neutral.wav": _sample_documentary,
    "bgm-comedy-quirky.wav": _sample_comedy,
    "bgm-action-chase.wav": _sample_action,
}


def _render(sampler, out_path: Path) -> None:
    total = int(SAMPLE_RATE * DURATION_SEC)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        frames = bytearray()
        for n in range(total):
            t = n / SAMPLE_RATE
            sample = sampler(t) * _envelope(t, DURATION_SEC) * AMPLITUDE
            sample = max(-1.0, min(1.0, sample))
            frames += struct.pack("<h", int(sample * 32767))
        wav.writeframes(bytes(frames))


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for filename, sampler in SAMPLERS.items():
        out_path = OUT_DIR / filename
        _render(sampler, out_path)
        print(f"wrote {out_path.relative_to(REPO_ROOT)} ({out_path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
