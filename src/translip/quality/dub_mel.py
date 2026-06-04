from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Any

import numpy as np

TARGET_SAMPLE_RATE = 22050
N_MELS = 64
N_FFT = 1024
HOP_LENGTH = 256
FMIN_HZ = 50.0
FMAX_HZ = 8000.0
DB_MIN = -80.0
DB_MAX = 0.0
MAX_FRAMES_PER_SEGMENT = 200


def extract_mel_db(
    waveform: np.ndarray,
    sample_rate: int,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Compute a log-mel spectrogram quantized to uint8 [0, 255].

    Returns (mel_uint8, meta). `mel_uint8` has shape (N_MELS, n_frames),
    row 0 = lowest mel band, row -1 = highest. 0 maps to DB_MIN, 255 maps to DB_MAX.
    """
    import librosa

    if waveform.size == 0:
        return np.zeros((N_MELS, 0), dtype=np.uint8), {
            "n_mels": N_MELS,
            "n_frames": 0,
            "hop_sec": 0.0,
            "db_min": DB_MIN,
            "db_max": DB_MAX,
        }

    target_sr = TARGET_SAMPLE_RATE
    if sample_rate != target_sr:
        waveform = librosa.resample(waveform, orig_sr=sample_rate, target_sr=target_sr)
        sample_rate = target_sr

    mel = librosa.feature.melspectrogram(
        y=waveform.astype(np.float32),
        sr=sample_rate,
        n_fft=N_FFT,
        hop_length=HOP_LENGTH,
        n_mels=N_MELS,
        fmin=FMIN_HZ,
        fmax=FMAX_HZ,
        power=2.0,
    )
    db = librosa.power_to_db(mel, ref=np.max, top_db=-DB_MIN)
    # `db` ranges roughly in [DB_MIN, 0]. Clip & affine-map to [0, 255].
    clipped = np.clip(db, DB_MIN, DB_MAX)
    norm = (clipped - DB_MIN) / (DB_MAX - DB_MIN)
    mel_uint8 = np.clip(np.round(norm * 255.0), 0, 255).astype(np.uint8)

    return mel_uint8, {
        "n_mels": N_MELS,
        "n_frames": int(mel_uint8.shape[1]),
        "hop_sec": HOP_LENGTH / float(sample_rate),
        "db_min": DB_MIN,
        "db_max": DB_MAX,
    }


def _resample_indices(n_frames: int, max_points: int) -> list[int]:
    if n_frames <= max_points:
        return list(range(n_frames))
    step = n_frames / max_points
    return [min(int(round(i * step)), n_frames - 1) for i in range(max_points)]


def _downsample_time(mel: np.ndarray, max_frames: int) -> np.ndarray:
    if mel.shape[1] <= max_frames:
        return mel
    keep = _resample_indices(mel.shape[1], max_frames)
    return mel[:, keep]


def _serialize_mel(mel: np.ndarray) -> list[list[int]]:
    """Serialize a (n_mels, n_frames) uint8 matrix as row-major list-of-lists.

    JSON-friendly. For ~64x200 the payload is around 12 KB before gzip.
    """
    return [row.tolist() for row in mel]


def _slice_full_track(
    mel: np.ndarray,
    *,
    full_duration_sec: float | None,
    hop_sec: float,
    start: float,
    end: float,
) -> np.ndarray:
    if mel.shape[1] == 0 or end <= start:
        return np.zeros((mel.shape[0], 0), dtype=mel.dtype)
    start_idx = max(0, int(round(start / hop_sec)))
    end_idx = min(mel.shape[1], int(round(end / hop_sec)))
    if end_idx <= start_idx:
        return np.zeros((mel.shape[0], 0), dtype=mel.dtype)
    return mel[:, start_idx:end_idx]


def enrich_report_with_mel(
    report: dict[str, Any],
    *,
    pipeline_root: Path,
) -> dict[str, Any]:
    """Augment a dub-qa report with per-segment mel spectrograms.

    Adds:
      - segments[i].mel_spectrogram = {"original": {"data": [[...]], ...},
                                       "dub": {"data": [[...]], ...}}
      - report.mel_meta = {status, n_mels, db_min, db_max, fmin_hz, fmax_hz, ...}

    Idempotent. Failures fall through to `mel_meta.status` without raising.
    """
    started = time.perf_counter()
    meta: dict[str, Any] = {
        "status": "ok",
        "n_mels": N_MELS,
        "db_min": DB_MIN,
        "db_max": DB_MAX,
        "fmin_hz": FMIN_HZ,
        "fmax_hz": FMAX_HZ,
        "max_frames_per_segment": MAX_FRAMES_PER_SEGMENT,
        "enriched_count": 0,
        "skipped_count": 0,
    }

    segments = report.get("segments") or []
    if not segments:
        meta["status"] = "no_segments"
        report["mel_meta"] = meta
        return report

    try:
        from translip.speaker_embedding import read_audio_mono
    except Exception as exc:  # pragma: no cover
        report["mel_meta"] = {"status": "unavailable", "reason": str(exc)}
        return report

    original_voice_rel = (report.get("input") or {}).get("original_voice")
    original_full: np.ndarray | None = None
    original_meta: dict[str, Any] | None = None
    if original_voice_rel:
        original_path = (pipeline_root / original_voice_rel).resolve()
        if original_path.exists():
            try:
                waveform, sr = read_audio_mono(original_path)
                original_full, original_meta = extract_mel_db(waveform, sr)
            except Exception as exc:
                meta["original_error"] = str(exc)
                original_full = None

    enriched = 0
    skipped = 0
    for seg in segments:
        if seg.get("mel_spectrogram") is not None:
            skipped += 1
            continue
        start = seg.get("start")
        end = seg.get("end")
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            skipped += 1
            continue

        original_payload: dict[str, Any] | None = None
        if original_full is not None and original_meta is not None:
            slice_ = _slice_full_track(
                original_full,
                full_duration_sec=None,
                hop_sec=float(original_meta["hop_sec"]),
                start=float(start),
                end=float(end),
            )
            slice_ = _downsample_time(slice_, MAX_FRAMES_PER_SEGMENT)
            if slice_.shape[1] > 0:
                original_payload = {
                    "data": _serialize_mel(slice_),
                    "n_frames": int(slice_.shape[1]),
                    "duration_sec": round(float(end) - float(start), 3),
                }

        dub_payload: dict[str, Any] | None = None
        dub_rel = seg.get("dub_audio_path")
        if dub_rel:
            dub_path = (pipeline_root / dub_rel).resolve()
            if dub_path.exists():
                try:
                    dub_wave, dub_sr = read_audio_mono(dub_path)
                    dub_mel, dub_meta = extract_mel_db(dub_wave, dub_sr)
                    dub_mel = _downsample_time(dub_mel, MAX_FRAMES_PER_SEGMENT)
                    if dub_mel.shape[1] > 0:
                        dub_payload = {
                            "data": _serialize_mel(dub_mel),
                            "n_frames": int(dub_mel.shape[1]),
                            "duration_sec": round(
                                dub_mel.shape[1] * float(dub_meta["hop_sec"]), 3
                            ),
                        }
                except Exception as exc:
                    seg["mel_error"] = str(exc)

        if original_payload is None and dub_payload is None:
            skipped += 1
            continue

        seg["mel_spectrogram"] = {
            "original": original_payload,
            "dub": dub_payload,
        }
        enriched += 1

    meta["enriched_count"] = enriched
    meta["skipped_count"] = skipped
    if enriched == 0:
        meta["status"] = "empty"
    meta["elapsed_sec"] = round(time.perf_counter() - started, 3)
    report["mel_meta"] = meta
    return report


def enrich_report_path(
    report_path: Path,
    *,
    pipeline_root: Path,
    write: bool = True,
) -> dict[str, Any]:
    import json

    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    enrich_report_with_mel(report, pipeline_root=pipeline_root)
    if write:
        Path(report_path).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return report


def _main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Backfill mel spectrograms into an existing dub-qa report."
    )
    parser.add_argument("report_path", type=Path)
    parser.add_argument("pipeline_root", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    enrich_report_path(args.report_path, pipeline_root=args.pipeline_root, write=not args.dry_run)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
