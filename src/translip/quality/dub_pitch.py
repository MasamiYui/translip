from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Any

import numpy as np

PITCH_FMIN_HZ = 65.0
PITCH_FMAX_HZ = 1000.0
PITCH_FRAME_LENGTH = 2048
PITCH_HOP_LENGTH = 256
TARGET_SAMPLE_RATE = 22050
MAX_POINTS_PER_SEGMENT = 200
ROUND_DECIMALS = 2

PitchPoint = tuple[float, float | None]


def _round_or_none(value: float | None) -> float | None:
    if value is None:
        return None
    if not math.isfinite(value):
        return None
    return round(float(value), ROUND_DECIMALS)


def _resample_indices(n_frames: int, max_points: int) -> list[int]:
    if n_frames <= max_points:
        return list(range(n_frames))
    step = n_frames / max_points
    return [min(int(round(i * step)), n_frames - 1) for i in range(max_points)]


def extract_pitch_contour(
    waveform: np.ndarray,
    sample_rate: int,
    *,
    start: float = 0.0,
    fmin: float = PITCH_FMIN_HZ,
    fmax: float = PITCH_FMAX_HZ,
) -> list[PitchPoint]:
    """Return [(time_sec, hz_or_None), ...] using librosa.pyin.

    `waveform` is a 1-D float32 mono array; `start` is the wall-clock time
    offset that the first sample corresponds to (used so callers can request
    contours in absolute timeline coordinates).
    """
    import librosa  # local import keeps module importable on minimal envs

    if waveform.size == 0:
        return []

    target_sr = TARGET_SAMPLE_RATE
    if sample_rate != target_sr:
        waveform = librosa.resample(waveform, orig_sr=sample_rate, target_sr=target_sr)
        sample_rate = target_sr

    f0, _voiced_flag, _voiced_prob = librosa.pyin(
        waveform.astype(np.float32),
        fmin=fmin,
        fmax=fmax,
        sr=sample_rate,
        frame_length=PITCH_FRAME_LENGTH,
        hop_length=PITCH_HOP_LENGTH,
    )

    times = librosa.times_like(f0, sr=sample_rate, hop_length=PITCH_HOP_LENGTH)

    contour: list[PitchPoint] = []
    for hz, t in zip(f0.tolist(), times.tolist()):
        rel_t = float(t) + float(start)
        if hz is None or (isinstance(hz, float) and math.isnan(hz)):
            contour.append((round(rel_t, 3), None))
        else:
            contour.append((round(rel_t, 3), _round_or_none(float(hz))))
    return contour


def _downsample(contour: list[PitchPoint], max_points: int) -> list[PitchPoint]:
    if len(contour) <= max_points:
        return contour
    keep = _resample_indices(len(contour), max_points)
    return [contour[i] for i in keep]


def _split_contour(contour: list[PitchPoint]) -> dict[str, list[Any]]:
    times = [round(t, 3) for t, _ in contour]
    hz = [hz for _, hz in contour]
    return {"times": times, "hz": hz}


def _slice_full_track(
    full: list[PitchPoint],
    start: float,
    end: float,
) -> list[PitchPoint]:
    if not full or end <= start:
        return []
    return [(t, hz) for t, hz in full if start <= t <= end]


def enrich_report_with_pitch(
    report: dict[str, Any],
    *,
    pipeline_root: Path,
) -> dict[str, Any]:
    """Augment a dub-qa report with per-segment F0 contours.

    Adds:
      - segments[i].pitch_contour = {"original": {times, hz}, "dub": {times, hz}}
      - report.pitch_meta = {status, segment_count, ...}

    Idempotent: segments that already carry a pitch_contour are skipped.
    On failure, sets pitch_meta.status to one of:
      ok | unavailable | empty | error.
    """
    started = time.perf_counter()
    meta: dict[str, Any] = {
        "status": "ok",
        "fmin_hz": PITCH_FMIN_HZ,
        "fmax_hz": PITCH_FMAX_HZ,
        "hop_length": PITCH_HOP_LENGTH,
        "frame_length": PITCH_FRAME_LENGTH,
        "max_points_per_segment": MAX_POINTS_PER_SEGMENT,
        "enriched_count": 0,
        "skipped_count": 0,
    }

    segments = report.get("segments") or []
    if not segments:
        meta["status"] = "no_segments"
        report["pitch_meta"] = meta
        return report

    try:
        from translip.speaker_embedding import read_audio_mono
    except Exception as exc:  # pragma: no cover
        report["pitch_meta"] = {"status": "unavailable", "reason": str(exc)}
        return report

    original_voice_rel = (report.get("input") or {}).get("original_voice")
    original_full: list[PitchPoint] = []
    if original_voice_rel:
        original_path = (pipeline_root / original_voice_rel).resolve()
        if original_path.exists():
            try:
                waveform, sr = read_audio_mono(original_path)
                original_full = extract_pitch_contour(waveform, sr)
            except Exception as exc:
                meta["original_error"] = str(exc)
                original_full = []

    enriched = 0
    skipped = 0
    for seg in segments:
        if seg.get("pitch_contour") is not None:
            skipped += 1
            continue
        start = seg.get("start")
        end = seg.get("end")
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            skipped += 1
            continue

        original_slice = _slice_full_track(original_full, float(start), float(end))
        # Re-base original times to be relative to the segment (0..duration)
        original_relative = [
            (round(t - float(start), 3), hz) for t, hz in original_slice
        ]
        original_relative = _downsample(original_relative, MAX_POINTS_PER_SEGMENT)

        dub_relative: list[PitchPoint] = []
        dub_rel = seg.get("dub_audio_path")
        if dub_rel:
            dub_path = (pipeline_root / dub_rel).resolve()
            if dub_path.exists():
                try:
                    dub_wave, dub_sr = read_audio_mono(dub_path)
                    dub_relative = extract_pitch_contour(dub_wave, dub_sr)
                    dub_relative = _downsample(dub_relative, MAX_POINTS_PER_SEGMENT)
                except Exception as exc:
                    seg["pitch_error"] = str(exc)

        if not original_relative and not dub_relative:
            skipped += 1
            continue

        seg["pitch_contour"] = {
            "original": _split_contour(original_relative),
            "dub": _split_contour(dub_relative),
        }
        enriched += 1

    meta["enriched_count"] = enriched
    meta["skipped_count"] = skipped
    if enriched == 0:
        meta["status"] = "empty"
    meta["elapsed_sec"] = round(time.perf_counter() - started, 3)
    report["pitch_meta"] = meta
    return report


def enrich_report_path(
    report_path: Path,
    *,
    pipeline_root: Path,
    write: bool = True,
) -> dict[str, Any]:
    import json

    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    enrich_report_with_pitch(report, pipeline_root=pipeline_root)
    if write:
        Path(report_path).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return report


def _main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Backfill pitch contours into an existing dub-qa report.")
    parser.add_argument("report_path", type=Path)
    parser.add_argument("pipeline_root", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    enrich_report_path(args.report_path, pipeline_root=args.pipeline_root, write=not args.dry_run)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
