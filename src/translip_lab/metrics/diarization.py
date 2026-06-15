"""Diarization Error Rate (DER), frame-based with optimal speaker mapping.

DER = (missed + false_alarm + confusion) / total_reference_speech, where the
reference↔hypothesis speaker mapping is the assignment that maximizes overlap
(Hungarian, ``scipy.optimize.linear_sum_assignment``). This is the standard
NIST md-eval decomposition; overlap is handled (a frame may carry N speakers).

``collar`` (seconds) excludes frames within ±collar of any reference boundary
from scoring (both numerator and denominator), matching common DER reporting.
``ignore_overlap`` additionally scores only single-speaker reference frames.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np


def parse_rttm(path: str | Path) -> list[tuple[float, float, str]]:
    """Parse an RTTM file → [(start, end, speaker), ...]."""
    segs: list[tuple[float, float, str]] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith(";;"):
            continue
        parts = line.split()
        if len(parts) < 8 or parts[0].upper() != "SPEAKER":
            continue
        try:
            start = float(parts[3])
            dur = float(parts[4])
        except ValueError:
            continue
        spk = parts[7]
        if dur > 0:
            segs.append((start, start + dur, spk))
    return segs


def _grid(segs: list[tuple[float, float, str]], speakers: list[str], n: int, step: float) -> np.ndarray:
    """(n_speakers, n_frames) bool activity grid."""
    idx = {s: i for i, s in enumerate(speakers)}
    grid = np.zeros((len(speakers), n), dtype=bool)
    for st, en, spk in segs:
        i0 = max(0, int(round(st / step)))
        i1 = min(n, int(round(en / step)))
        if i1 > i0:
            grid[idx[spk], i0:i1] = True
    return grid


def der(
    ref_segs: list[tuple[float, float, str]],
    hyp_segs: list[tuple[float, float, str]],
    *,
    step: float = 0.01,
    collar: float = 0.0,
    ignore_overlap: bool = False,
) -> dict:
    """Compute DER and its components. Returns a dict with der/miss/fa/confusion."""
    from scipy.optimize import linear_sum_assignment

    if not ref_segs:
        return {"der": float("nan"), "miss": 0.0, "false_alarm": 0.0, "confusion": 0.0,
                "ref_speech_sec": 0.0, "step": step, "collar": collar, "note": "empty reference"}

    max_t = max(e for _, e, _ in ref_segs)
    if hyp_segs:
        max_t = max(max_t, max(e for _, e, _ in hyp_segs))
    n = int(np.ceil(max_t / step)) + 1

    ref_spk = sorted({s for _, _, s in ref_segs})
    hyp_spk = sorted({s for _, _, s in hyp_segs})
    R = _grid(ref_segs, ref_spk, n, step)
    H = _grid(hyp_segs, hyp_spk, n, step) if hyp_spk else np.zeros((0, n), dtype=bool)
    n_ref = R.sum(axis=0)
    n_hyp = H.sum(axis=0)

    scored = np.ones(n, dtype=bool)
    if collar > 0:
        cf = int(round(collar / step))
        for st, en, _ in ref_segs:
            for b in (st, en):
                i = int(round(b / step))
                scored[max(0, i - cf):min(n, i + cf + 1)] = False
    if ignore_overlap:
        scored &= n_ref <= 1

    # Optimal mapping maximizes total overlap over the scored region.
    n_correct = np.zeros(n, dtype=int)
    if R.shape[0] and H.shape[0]:
        overlap = (R[:, scored].astype(int)) @ (H[:, scored].astype(int).T)  # (n_ref_spk, n_hyp_spk)
        ri, ci = linear_sum_assignment(-overlap)
        for i, j in zip(ri, ci):
            n_correct += (R[i] & H[j]).astype(int)

    nr = n_ref[scored]
    nh = n_hyp[scored]
    nc = n_correct[scored]
    miss = float(np.maximum(0, nr - nh).sum()) * step
    fa = float(np.maximum(0, nh - nr).sum()) * step
    conf = float((np.minimum(nr, nh) - nc).sum()) * step
    total = float(nr.sum()) * step
    der_val = (miss + fa + conf) / total if total > 0 else float("nan")
    return {
        "der": der_val,
        "miss": miss,
        "false_alarm": fa,
        "confusion": conf,
        "miss_rate": miss / total if total else float("nan"),
        "false_alarm_rate": fa / total if total else float("nan"),
        "confusion_rate": conf / total if total else float("nan"),
        "ref_speech_sec": total,
        "ref_speaker_count": len(ref_spk),
        "hyp_speaker_count": len(hyp_spk),
        "step": step,
        "collar": collar,
        "ignore_overlap": ignore_overlap,
    }
