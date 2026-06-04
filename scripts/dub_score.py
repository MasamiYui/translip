#!/usr/bin/env python3
"""Branch-independent honest dub scorer.

Reads a pipeline output root (or an explicit task-e dir + translation path) and
computes the acoustic signals that actually correlate with bad dubbing, so we can
compare optimization rounds objectively:

  * timbre   — speaker_similarity distribution incl. the 0.25-0.45 "gray band"
  * pacing   — applied tempo (speed-up), tail trim (cut-off words), dead air
  * audible  — post-mix SNR of the dub over the (configured-duck) background
  * speech   — intelligibility (read-back text_similarity)
  * coverage — placed vs the task-c translation universe (undubbed lines)

Usage:
  python scripts/dub_score.py <pipeline_root> [--json out.json] [--label NAME]
  python scripts/dub_score.py --task-e <dir> --translation <t.json> \
      --background <bg.wav> [--json out.json]

It is intentionally standalone (numpy + soundfile only) so the same yardstick
works regardless of which dub_qa/benchmark generation is checked out.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

import numpy as np

try:
    import soundfile as sf
except Exception as exc:  # pragma: no cover
    print(f"soundfile required: {exc}", file=sys.stderr)
    raise

# Thresholds — kept in sync with the honest-signals constants.
TIMBRE_GOOD = 0.45
TIMBRE_BAD = 0.25
TEXT_GOOD = 0.90
TEXT_BAD = 0.70
OVERCOMPRESS_TEMPO = 1.40
CUTOFF_TAIL_SEC = 0.30
DEADAIR_SEC = 0.40
DEADAIR_MAX_RATIO = 0.80
SNR_MIN_DB = 3.0


def _load_json(path: Path):
    with open(path) as fh:
        return json.load(fh)


def _rms(x: np.ndarray) -> float:
    if x.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(x, dtype=np.float64))))


def _db(x: float) -> float:
    return 20.0 * math.log10(max(x, 1e-12))


def _to_mono(wav: np.ndarray) -> np.ndarray:
    if wav.ndim == 2:
        return wav.mean(axis=1)
    return wav


def _resample_to(wav: np.ndarray, sr: int, target_sr: int) -> np.ndarray:
    if sr == target_sr or wav.size == 0:
        return wav
    try:
        import soxr

        return soxr.resample(wav, sr, target_sr)
    except Exception:
        n = int(round(wav.size * target_sr / sr))
        return np.interp(
            np.linspace(0, wav.size - 1, n), np.arange(wav.size), wav
        ).astype(np.float32)


@dataclass
class Scorecard:
    label: str = ""
    translated: int = 0
    placed: int = 0
    undubbed: int = 0
    # timbre
    timbre_good: int = 0
    timbre_review: int = 0
    timbre_bad: int = 0
    timbre_median: float = 0.0
    # pacing
    overcompressed: int = 0
    cutoff: int = 0
    deadair: int = 0
    tempo_median: float = 0.0
    tempo_p90: float = 0.0
    trimmed_total_sec: float = 0.0
    direct_count: int = 0
    # intelligibility
    intel_good: int = 0
    intel_review: int = 0
    intel_bad: int = 0
    intel_median: float = 0.0
    # audibility — "actual" = measured from the final mix stems (any mix algo);
    # "cfg" = background attenuated by the configured static duck (fallback).
    buried: int = 0
    snr_median_db: float = 0.0
    snr_min_db: float = 0.0
    snr_cfg_median_db: float = 0.0
    dub_loudness_dbfs: float = 0.0
    dub_level_spread_db: float = 0.0
    # composite
    honest_score: float = 0.0
    problem_segments: int = 0

    def print(self) -> None:
        n = max(self.placed, 1)
        print(f"\n{'='*64}\n  DUB SCORECARD — {self.label or '(unlabeled)'}\n{'='*64}")
        print(f"  HONEST SCORE         {self.honest_score:5.1f} / 100      "
              f"problem segments: {self.problem_segments}/{self.placed}")
        print(f"  coverage             placed {self.placed} / translated "
              f"{self.translated}   undubbed: {self.undubbed}")
        print(f"  ── timbre (speaker similarity) ──")
        print(f"     good>={TIMBRE_GOOD}: {self.timbre_good:2d}   "
              f"GRAY {TIMBRE_BAD}-{TIMBRE_GOOD}: {self.timbre_review:2d}   "
              f"bad<{TIMBRE_BAD}: {self.timbre_bad:2d}   median: {self.timbre_median:.3f}")
        print(f"  ── pacing (post-fit) ──")
        print(f"     overcompressed(>={OVERCOMPRESS_TEMPO}x): {self.overcompressed:2d}   "
              f"cutoff(tail>={CUTOFF_TAIL_SEC}s): {self.cutoff:2d}   "
              f"deadair: {self.deadair:2d}   direct(untouched): {self.direct_count}")
        print(f"     tempo median: {self.tempo_median:.3f}  p90: {self.tempo_p90:.3f}  "
              f"trimmed total: {self.trimmed_total_sec:.2f}s")
        print(f"  ── intelligibility (read-back) ──")
        print(f"     good>={TEXT_GOOD}: {self.intel_good:2d}   review: {self.intel_review:2d}   "
              f"bad<{TEXT_BAD}: {self.intel_bad:2d}   median: {self.intel_median:.3f}")
        print(f"  ── audibility (actual post-mix SNR, dub vs residual bg) ──")
        print(f"     buried(<{SNR_MIN_DB}dB): {self.buried:2d}   median SNR: "
              f"{self.snr_median_db:5.1f}dB   min SNR: {self.snr_min_db:5.1f}dB   "
              f"(cfg-duck SNR: {self.snr_cfg_median_db:4.1f}dB)")
        print(f"     dub loudness: {self.dub_loudness_dbfs:5.1f} dBFS   "
              f"per-clip level spread (std): {self.dub_level_spread_db:4.1f} dB  (lower=more even)")
        print("=" * 64)


def compute(task_e_dir: Path, translation_path: Path | None,
            background_path: Path | None, label: str) -> Scorecard:
    mix_report = _load_json(task_e_dir / next(
        p.name for p in task_e_dir.glob("mix_report.*.json")))
    cfg = mix_report.get("config", {})
    max_cap = float(cfg.get("max_compress_ratio", 1.45))
    bg_gain_db = float(cfg.get("background_gain_db", -8.0))
    duck_db = float(cfg.get("window_ducking_db", -3.0))
    placed = mix_report.get("placed_segments", [])

    sc = Scorecard(label=label, placed=len(placed))

    # coverage vs translation universe
    if translation_path and translation_path.exists():
        tj = _load_json(translation_path)
        rows = tj.get("segments") if isinstance(tj, dict) else tj
        sc.translated = len(rows or [])
    sc.undubbed = max(0, sc.translated - sc.placed)

    # load mix stems for SNR
    dub = bg = mix = residual = None
    sr_out = int(cfg.get("output_sample_rate", 24000))
    try:
        dvp = next(task_e_dir.glob("dub_voice.*.wav"))
        d, dsr = sf.read(dvp, dtype="float32")
        dub = _to_mono(d)
        sr_out = dsr
    except StopIteration:
        pass
    try:
        mvp = next(task_e_dir.glob("preview_mix.*.wav"))
        m, msr = sf.read(mvp, dtype="float32")
        mix = _resample_to(_to_mono(m), msr, sr_out)
    except StopIteration:
        pass
    # actual background-in-mix = final mix minus the dub stem (mix = bg' + dub
    # before the global peak-limit; the peak-limit factor is ~1 when unclipped,
    # so the residual reflects whatever ducking the mix algorithm actually did).
    if dub is not None and mix is not None:
        n = min(dub.size, mix.size)
        residual = mix[:n] - dub[:n]
    if background_path and Path(background_path).exists():
        b, bsr = sf.read(background_path, dtype="float32")
        bg = _resample_to(_to_mono(b), bsr, sr_out)
    if dub is not None:
        sc.dub_loudness_dbfs = _db(_rms(dub[np.abs(dub) > 1e-4]) if np.any(np.abs(dub) > 1e-4) else _rms(dub))

    sims, texts, tempos, snrs, snrs_cfg, dub_levels = [], [], [], [], [], []
    for seg in placed:
        # timbre
        ss = seg.get("speaker_similarity")
        if ss is not None:
            sims.append(float(ss))
            if ss >= TIMBRE_GOOD: sc.timbre_good += 1
            elif ss >= TIMBRE_BAD: sc.timbre_review += 1
            else: sc.timbre_bad += 1
        # intelligibility
        ts = seg.get("text_similarity")
        if ts is not None:
            texts.append(float(ts))
            if ts >= TEXT_GOOD: sc.intel_good += 1
            elif ts >= TEXT_BAD: sc.intel_review += 1
            else: sc.intel_bad += 1
        # pacing
        gen = float(seg.get("generated_duration_sec") or 0.0)
        fit = float(seg.get("fitted_duration_sec") or 0.0)
        src = float(seg.get("source_duration_sec") or 0.0)
        strat = seg.get("fit_strategy", "")
        notes = " ".join(seg.get("notes", []) or [])
        if strat == "direct":
            sc.direct_count += 1
        rec_tempo = seg.get("applied_tempo")
        rec_trim = seg.get("trimmed_tail_sec")
        if rec_tempo is not None:  # exact, recorded by the renderer
            tempo = float(rec_tempo)
            tail = float(rec_trim or 0.0)
        else:  # estimate from durations (legacy mix reports)
            trimmed = ("overflow_trimmed" in notes) or (strat == "overflow_unfitted")
            if trimmed and gen > 0:
                tempo = max_cap
                tail = max(0.0, gen / tempo - fit)
            else:
                tempo = (gen / fit) if (gen > 0 and fit > 0) else 1.0
                tail = 0.0
        tempos.append(tempo)
        if tempo >= OVERCOMPRESS_TEMPO:
            sc.overcompressed += 1
        if tail >= CUTOFF_TAIL_SEC:
            sc.cutoff += 1
            sc.trimmed_total_sec += tail
        placed_ratio = (fit / src) if src > 0 else 1.0
        dead = max(0.0, src - fit)
        if dead >= DEADAIR_SEC and placed_ratio < DEADAIR_MAX_RATIO:
            sc.deadair += 1
        # audibility in placement window
        a = int(float(seg.get("placement_start", 0.0)) * sr_out)
        z = int(float(seg.get("placement_end", 0.0)) * sr_out)
        if dub is not None and z > a:
            dub_rms = _rms(dub[a:z])
            if dub_rms > 10 ** (-45.0 / 20.0):
                dub_levels.append(_db(dub_rms))
            # actual: dub vs the background as it survives in the final mix
            if residual is not None and z <= residual.size:
                snr_a = max(-60.0, min(60.0, _db(dub_rms) - _db(_rms(residual[a:z]))))
                snrs.append(snr_a)
                if snr_a < SNR_MIN_DB:
                    sc.buried += 1
            # cfg fallback: dub vs background attenuated by the static duck
            if bg is not None and z <= bg.size:
                bg_win = bg[a:z] * (10 ** ((bg_gain_db + duck_db) / 20.0))
                snr_c = max(-60.0, min(60.0, _db(dub_rms) - _db(_rms(bg_win))))
                snrs_cfg.append(snr_c)
                if residual is None and snr_c < SNR_MIN_DB:
                    sc.buried += 1

    def med(xs): return float(np.median(xs)) if xs else 0.0
    sc.timbre_median = med(sims)
    sc.intel_median = med(texts)
    sc.tempo_median = med(tempos)
    sc.tempo_p90 = float(np.percentile(tempos, 90)) if tempos else 0.0
    sc.snr_median_db = med(snrs) if snrs else med(snrs_cfg)
    sc.snr_min_db = float(min(snrs)) if snrs else (float(min(snrs_cfg)) if snrs_cfg else 0.0)
    sc.snr_cfg_median_db = med(snrs_cfg)
    sc.dub_level_spread_db = float(np.std(dub_levels)) if len(dub_levels) > 1 else 0.0

    # composite honest score: 100 minus weighted, per-segment penalties.
    n = max(sc.placed, 1)
    pen = 0.0
    pen += 30 * (sc.undubbed / max(sc.translated, 1))
    pen += 22 * ((sc.timbre_bad + 0.6 * sc.timbre_review) / n)
    pen += 18 * ((sc.cutoff + 0.5 * sc.overcompressed) / n)
    pen += 14 * (sc.buried / n)
    pen += 10 * ((sc.intel_bad + 0.5 * sc.intel_review) / n)
    pen += 6 * (sc.deadair / n)
    sc.honest_score = round(max(0.0, 100.0 - pen), 1)
    sc.problem_segments = len({
        i for i, seg in enumerate(placed)
        if (seg.get("speaker_similarity") or 1) < TIMBRE_GOOD
        or (seg.get("text_similarity") or 1) < TEXT_GOOD
        or (seg.get("fit_strategy") in ("overflow_unfitted",))
        or "overflow_trimmed" in " ".join(seg.get("notes", []) or [])
    }) + sc.undubbed
    return sc


def _autolocate(root: Path):
    task_e = root / "task-e" / "voice"
    if not task_e.exists():
        cand = list(root.glob("**/mix_report.*.json"))
        if cand:
            task_e = cand[0].parent
    translation = None
    tc = list(root.glob("task-c/**/translation.*.json"))
    if tc:
        translation = tc[0]
    bg = None
    bgc = list(root.glob("stage1/**/background.wav")) or list(root.glob("stage1/**/background.*"))
    if bgc:
        bg = bgc[0]
    return task_e, translation, bg


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", nargs="?", help="pipeline output root")
    ap.add_argument("--task-e", dest="task_e")
    ap.add_argument("--translation")
    ap.add_argument("--background")
    ap.add_argument("--json", dest="json_out")
    ap.add_argument("--label", default="")
    args = ap.parse_args()

    if args.task_e:
        task_e = Path(args.task_e)
        translation = Path(args.translation) if args.translation else None
        bg = Path(args.background) if args.background else None
        label = args.label or task_e.as_posix()
    elif args.root:
        root = Path(args.root)
        task_e, translation, bg = _autolocate(root)
        if args.translation: translation = Path(args.translation)
        if args.background: bg = Path(args.background)
        label = args.label or root.name
    else:
        ap.error("provide a pipeline root or --task-e")

    sc = compute(task_e, translation, bg, label)
    sc.print()
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(asdict(sc), indent=2))
        print(f"  -> wrote {args.json_out}")


if __name__ == "__main__":
    main()
