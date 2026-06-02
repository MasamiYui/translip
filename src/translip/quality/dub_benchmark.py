from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..pipeline.manifest import now_iso
from ..translation.backend import output_tag_for_language
from ..utils.files import ensure_directory
from ..utils.io import read_json, write_json as _write_json_impl

# Post-fit pacing thresholds — shared with :mod:`translip.quality.dub_qa`, which
# imports them so the per-segment tags and the job-level score/gates agree.
# They read the renderer's *fitted* measurements (applied_tempo / trimmed_tail_sec /
# dead_air_sec / placed_duration_ratio), i.e. what the listener actually hears,
# not the raw-TTS ``duration_status`` that flagged every verbose-English line.
CUTOFF_TAIL_SEC = 0.30  # tail hard-cut by >= this many seconds → words lost
OVERCOMPRESS_TEMPO = 1.40  # atempo factor >= this → audibly rushed / chipmunk
DEADAIR_SEC = 0.40  # trailing silence >= this → dead air
DEADAIR_MAX_RATIO = 0.80  # ...only when the fitted dub fills < this share of the window
PLACED_RATIO_LOW = 0.80
PLACED_RATIO_HIGH = 1.25
# Timbre "review" band: ECAPA cosine here is audibly off but not catastrophic.
# Only < TIMBRE_REVIEW_LOW is a hard speaker_status='failed' upstream; the whole
# band in between was previously silent in the evaluation.
TIMBRE_REVIEW_LOW = 0.25
TIMBRE_REVIEW_HIGH = 0.45


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except (TypeError, ValueError):
        return default


# A placed dub sitting less than this many dB above the (ducked) background in its
# own window is "配上了却听不见" — buried. Env-overridable for calibration.
DUB_SNR_MIN_DB = _env_float("TRANSLIP_DUB_MIN_SNR_DB", 3.0)


@dataclass(slots=True)
class DubBenchmarkRequest:
    pipeline_root: Path | str
    output_dir: Path | str
    target_lang: str = "en"

    def normalized(self) -> "DubBenchmarkRequest":
        return DubBenchmarkRequest(
            pipeline_root=Path(self.pipeline_root).expanduser().resolve(),
            output_dir=Path(self.output_dir).expanduser().resolve(),
            target_lang=self.target_lang,
        )


@dataclass(slots=True)
class DubBenchmarkArtifacts:
    benchmark_path: Path
    report_path: Path
    manifest_path: Path


@dataclass(slots=True)
class DubBenchmarkResult:
    request: DubBenchmarkRequest
    artifacts: DubBenchmarkArtifacts
    benchmark: dict[str, Any]
    manifest: dict[str, Any]


def build_dub_benchmark(request: DubBenchmarkRequest) -> DubBenchmarkResult:
    normalized = request.normalized()
    started_at = now_iso()
    started_monotonic = time.monotonic()
    output_dir = ensure_directory(Path(normalized.output_dir))
    benchmark_path = output_dir / f"dub_benchmark.{normalized.target_lang}.json"
    report_path = output_dir / f"dub_benchmark_report.{normalized.target_lang}.md"
    manifest_path = output_dir / "dub-benchmark-manifest.json"

    paths = _input_paths(normalized.pipeline_root, normalized.target_lang)
    mix_report = _read_json(paths["mix_report"])
    character_ledger = _read_json(paths["character_ledger"])
    repair_manifest = _read_json(paths["repair_manifest"])
    repair_attempts = _read_json(paths["repair_attempts"])
    manual_review = _read_json(paths["manual_review"])
    translation_count = _translation_segment_count(
        normalized.pipeline_root, mix_report, normalized.target_lang
    )
    metrics = _metrics(
        mix_report=mix_report,
        character_ledger=character_ledger,
        repair_manifest=repair_manifest,
        repair_attempts=repair_attempts,
        manual_review=manual_review,
        translation_count=translation_count,
    )
    status, reasons = _status_and_reasons(metrics)
    benchmark = {
        "version": "dub-benchmark-v0",
        "created_at": now_iso(),
        "target_lang": normalized.target_lang,
        "status": status,
        "score": _score(metrics),
        "reasons": reasons,
        "metrics": metrics,
        "gates": _gates(metrics),
        "input": {
            key: str(path) if path is not None else None
            for key, path in paths.items()
        },
    }
    _write_json(benchmark_path, benchmark)
    report_path.write_text(_markdown_report(benchmark), encoding="utf-8")
    manifest = {
        "status": "succeeded",
        "target_lang": normalized.target_lang,
        "artifacts": {
            "benchmark": str(benchmark_path),
            "report": str(report_path),
        },
        "summary": {
            "status": status,
            "score": benchmark["score"],
            "reasons": reasons,
        },
        "timing": {
            "started_at": started_at,
            "finished_at": now_iso(),
            "elapsed_sec": round(time.monotonic() - started_monotonic, 3),
        },
        "error": None,
    }
    _write_json(manifest_path, manifest)
    return DubBenchmarkResult(
        request=normalized,
        artifacts=DubBenchmarkArtifacts(
            benchmark_path=benchmark_path,
            report_path=report_path,
            manifest_path=manifest_path,
        ),
        benchmark=benchmark,
        manifest=manifest,
    )


def classify_pacing(segment: dict[str, Any]) -> list[str]:
    """Classify a placed segment's *post-fit* pacing into actionable buckets.

    Returns any of ``cutoff`` (tail hard-cut → words lost), ``overcompressed``
    (atempo too aggressive → rushed), ``deadair`` (trailing silence), or the
    generic ``pacing`` (residual length mismatch the fit could not resolve).
    Falls back to the legacy pre-fit ``duration_status`` when the renderer didn't
    write post-fit fields (older mix reports / task-d-only fixtures).
    """
    trimmed = segment.get("trimmed_tail_sec")
    tempo = segment.get("applied_tempo")
    dead_air = segment.get("dead_air_sec")
    placed_ratio = segment.get("placed_duration_ratio")
    has_post_fit = any(isinstance(v, (int, float)) for v in (trimmed, tempo, dead_air, placed_ratio))
    if not has_post_fit:
        return ["pacing"] if segment.get("duration_status") == "failed" else []

    labels: list[str] = []
    if isinstance(trimmed, (int, float)) and trimmed >= CUTOFF_TAIL_SEC:
        labels.append("cutoff")
    elif isinstance(tempo, (int, float)) and tempo >= OVERCOMPRESS_TEMPO:
        labels.append("overcompressed")
    if (
        isinstance(dead_air, (int, float))
        and dead_air >= DEADAIR_SEC
        and (not isinstance(placed_ratio, (int, float)) or placed_ratio < DEADAIR_MAX_RATIO)
    ):
        labels.append("deadair")
    if not labels and isinstance(placed_ratio, (int, float)) and not (
        PLACED_RATIO_LOW <= placed_ratio <= PLACED_RATIO_HIGH
    ):
        labels.append("pacing")
    return labels


def _pacing_counts(mix_report: dict[str, Any]) -> dict[str, int]:
    placed = mix_report.get("placed_segments", [])
    counts = {"cutoff": 0, "overcompressed": 0, "deadair": 0, "affected": 0}
    if not isinstance(placed, list):
        return counts
    for segment in placed:
        if not isinstance(segment, dict):
            continue
        labels = classify_pacing(segment)
        if labels:
            counts["affected"] += 1
        for label in labels:
            if label in counts:
                counts[label] += 1
    return counts


def _audibility_counts(mix_report: dict[str, Any]) -> dict[str, Any]:
    placed = mix_report.get("placed_segments", [])
    buried_ids: list[str] = []
    snrs: list[float] = []
    if isinstance(placed, list):
        for segment in placed:
            if not isinstance(segment, dict):
                continue
            snr = segment.get("dub_snr_db")
            if not isinstance(snr, (int, float)):
                continue
            snrs.append(float(snr))
            if snr < DUB_SNR_MIN_DB:
                buried_ids.append(str(segment.get("segment_id") or ""))
    return {
        "buried_count": len(buried_ids),
        "buried_segment_ids": buried_ids,
        "min_snr_db": round(min(snrs), 2) if snrs else None,
    }


def _translation_segment_count(root: Path, mix_report: dict[str, Any], target_lang: str) -> int:
    """Count translated segments — the honest 'should be dubbed' universe.

    Mirrors the renderer-recorded path first, then discovers under ``task-c``.
    Returns 0 when task-c isn't on disk so callers fall back to the renderer
    denominator instead of falsely reading 0% coverage.
    """
    candidates: list[Path] = []
    recorded = mix_report.get("input", {}).get("translation_path") if isinstance(mix_report.get("input"), dict) else None
    if recorded:
        candidates.append(Path(recorded))
    tag = output_tag_for_language(target_lang)
    task_c = root / "task-c"
    if task_c.exists():
        candidates.extend(sorted(task_c.rglob(f"translation.{tag}.json")))
    for candidate in candidates:
        payload = _read_json(candidate)
        segments = payload.get("segments")
        if isinstance(segments, list) and segments:
            return sum(1 for seg in segments if isinstance(seg, dict) and seg.get("segment_id"))
    return 0


def _input_paths(root: Path, target_lang: str) -> dict[str, Path]:
    return {
        "mix_report": root / "task-e" / "voice" / f"mix_report.{target_lang}.json",
        "character_ledger": root / "task-d" / "voice" / "character-ledger" / f"character_ledger.{target_lang}.json",
        "repair_manifest": root / "task-d" / "voice" / "repair-run" / "repair-run-manifest.json",
        "repair_attempts": root / "task-d" / "voice" / "repair-run" / f"repair_attempts.{target_lang}.json",
        "manual_review": root / "task-d" / "voice" / "repair-run" / f"manual_review.{target_lang}.json",
    }


def _metrics(
    *,
    mix_report: dict[str, Any],
    character_ledger: dict[str, Any],
    repair_manifest: dict[str, Any],
    repair_attempts: dict[str, Any],
    manual_review: dict[str, Any],
    translation_count: int = 0,
) -> dict[str, Any]:
    stats = mix_report.get("stats", {}) if isinstance(mix_report.get("stats"), dict) else {}
    quality = stats.get("quality_summary", {}) if isinstance(stats.get("quality_summary"), dict) else {}
    audible = stats.get("audible_coverage", {}) if isinstance(stats.get("audible_coverage"), dict) else {}
    medians = quality.get("medians", {}) if isinstance(quality.get("medians"), dict) else {}
    ledger_stats = character_ledger.get("stats", {}) if isinstance(character_ledger.get("stats"), dict) else {}
    repair_stats = repair_manifest.get("stats", {}) if isinstance(repair_manifest.get("stats"), dict) else {}
    if not repair_stats:
        repair_stats = repair_attempts.get("stats", {}) if isinstance(repair_attempts.get("stats"), dict) else {}
    if manual_review.get("stats"):
        manual_stats = manual_review.get("stats", {})
        repair_stats = {
            **repair_stats,
            "manual_required_count": manual_stats.get("manual_required_count", repair_stats.get("manual_required_count")),
        }

    total_count = _int(quality.get("total_count"))
    placed_count = _int(stats.get("placed_count"))
    skipped_count = _int(stats.get("skipped_count"))
    # Anchor coverage on the *translation* universe when known: a line that was
    # translated but never reached task-d (its speaker was dropped pre-synthesis)
    # is absent from total_count, so the renderer's own denominator silently shrinks
    # and reads ~100% — exactly the "成片漏配" the operator hits. Fall back to the
    # renderer denominator when task-c isn't on disk (keeps standalone runs honest).
    translated_count = translation_count if translation_count > 0 else total_count
    coverage_denominator = max(translated_count, placed_count, 1)
    coverage_ratio = placed_count / coverage_denominator
    undubbed_count = max(0, translated_count - placed_count)
    skip_reason_counts = stats.get("skip_reason_counts", {}) if isinstance(stats.get("skip_reason_counts"), dict) else {}
    speaker_failed_count = _status_count(quality, "speaker_status_counts", "failed")
    speaker_review_count = _status_count(quality, "speaker_status_counts", "review")
    # Centroid (prototype) opinion — independent of the one reference clip cloned.
    speaker_centroid_failed_count = _status_count(quality, "speaker_status_centroid_counts", "failed")
    speaker_centroid_review_count = _status_count(quality, "speaker_status_centroid_counts", "review")
    intelligibility_failed_count = _status_count(quality, "intelligibility_status_counts", "failed")
    overall_failed_count = _status_count(quality, "overall_status_counts", "failed")
    pacing = _pacing_counts(mix_report)
    audibility = _audibility_counts(mix_report)
    return {
        "total_segment_count": total_count,
        "translated_count": translated_count,
        "placed_count": placed_count,
        "skipped_count": skipped_count,
        "undubbed_count": undubbed_count,
        "undubbed_ratio": round(undubbed_count / max(translated_count, 1), 4),
        "skip_reason_counts": skip_reason_counts,
        "coverage_ratio": round(coverage_ratio, 4),
        "speaker_review_count": speaker_review_count,
        "speaker_review_ratio": round(speaker_review_count / max(total_count, 1), 4),
        "speaker_median_similarity": _number(medians.get("speaker_similarity")),
        "speaker_centroid_failed_count": speaker_centroid_failed_count,
        "speaker_centroid_review_count": speaker_centroid_review_count,
        "speaker_centroid_review_ratio": round(speaker_centroid_review_count / max(total_count, 1), 4),
        "speaker_centroid_failed_ratio": round(speaker_centroid_failed_count / max(total_count, 1), 4),
        "speaker_centroid_median_similarity": _number(medians.get("speaker_similarity_centroid")),
        # Worst-of the two timbre opinions — drives the gate + score so either signal
        # (matches a bad reference clip, or drifts from the character centroid) counts,
        # both for the audibly-off review band AND for outright mismatch (failed).
        "timbre_review_ratio": round(
            max(speaker_review_count, speaker_centroid_review_count) / max(total_count, 1), 4
        ),
        "timbre_failed_ratio": round(
            max(speaker_failed_count, speaker_centroid_failed_count) / max(total_count, 1), 4
        ),
        "pacing_cutoff_count": pacing["cutoff"],
        "pacing_overcompressed_count": pacing["overcompressed"],
        "pacing_deadair_count": pacing["deadair"],
        "pacing_affected_count": pacing["affected"],
        "pacing_affected_ratio": round(pacing["affected"] / max(placed_count, 1), 4),
        "buried_count": audibility["buried_count"],
        "buried_segment_ids": audibility["buried_segment_ids"],
        "min_dub_snr_db": audibility["min_snr_db"],
        "audible_failed_count": _int(audible.get("failed_count")),
        "audible_failed_segment_ids": audible.get("failed_segment_ids") if isinstance(audible.get("failed_segment_ids"), list) else [],
        "audible_min_coverage_ratio": _number(audible.get("min_coverage_ratio")),
        "audible_average_coverage_ratio": _number(audible.get("average_coverage_ratio")),
        "overall_failed_count": overall_failed_count,
        "overall_failed_ratio": round(overall_failed_count / max(total_count, 1), 4),
        "speaker_failed_count": speaker_failed_count,
        "speaker_failed_ratio": round(speaker_failed_count / max(total_count, 1), 4),
        "intelligibility_failed_count": intelligibility_failed_count,
        "intelligibility_failed_ratio": round(intelligibility_failed_count / max(total_count, 1), 4),
        "character_count": _int(ledger_stats.get("character_count")),
        "character_review_count": _int(ledger_stats.get("review_count")),
        "character_blocked_count": _int(ledger_stats.get("blocked_count")),
        "voice_mismatch_count": _int(ledger_stats.get("voice_mismatch_count")),
        "repair_attempt_count": _int(repair_stats.get("attempt_count")),
        "repair_selected_count": _int(repair_stats.get("selected_count")),
        "repair_manual_required_count": _int(repair_stats.get("manual_required_count")),
    }


def _status_and_reasons(metrics: dict[str, Any]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if metrics["total_segment_count"] <= 0:
        reasons.append("no_rendered_segments")
    if metrics["coverage_ratio"] < 0.98:
        reasons.append("coverage_below_deliverable_threshold")
    if metrics["audible_failed_count"] > 0:
        reasons.append("audible_coverage_failed")
    if metrics["overall_failed_ratio"] > 0.05:
        reasons.append("upstream_failed_segments")
    if metrics.get("timbre_failed_ratio", metrics["speaker_failed_ratio"]) > 0.15:
        reasons.append("speaker_similarity_failed")
    if metrics["intelligibility_failed_ratio"] > 0.10:
        reasons.append("intelligibility_failed")
    if metrics["character_blocked_count"] > 0:
        reasons.append("character_voice_blocked")
    if metrics["character_review_count"] > 0 or metrics["voice_mismatch_count"] > 0:
        reasons.append("character_voice_review_required")
    if metrics["repair_manual_required_count"] > 0:
        reasons.append("repair_manual_required")
    if metrics.get("pacing_cutoff_count", 0) > 0:
        reasons.append("dub_tail_cut_off")
    if metrics.get("timbre_review_ratio", metrics.get("speaker_review_ratio", 0.0)) > 0.30:
        reasons.append("timbre_review_band_high")
    if metrics.get("buried_count", 0) > 0:
        reasons.append("dub_buried_under_background")

    if (
        metrics["total_segment_count"] <= 0
        or metrics["coverage_ratio"] < 0.98
        or metrics["audible_failed_count"] > 0
        or metrics["character_blocked_count"] > 0
        or metrics.get("buried_count", 0) > 0
    ):
        return "blocked", reasons
    if reasons:
        return "review_required", reasons
    return "deliverable_candidate", []


def _score(metrics: dict[str, Any]) -> float:
    penalty = 0.0
    penalty += max(0.0, 1.0 - float(metrics["coverage_ratio"])) * 60.0
    penalty += min(30.0, float(metrics["audible_failed_count"]) * 10.0)
    penalty += float(metrics["overall_failed_ratio"]) * 20.0
    penalty += float(metrics.get("timbre_failed_ratio", metrics["speaker_failed_ratio"])) * 25.0
    penalty += float(metrics["intelligibility_failed_ratio"]) * 25.0
    penalty += min(20.0, float(metrics["character_review_count"]) * 4.0)
    penalty += min(25.0, float(metrics["character_blocked_count"]) * 10.0)
    penalty += min(20.0, float(metrics["voice_mismatch_count"]) * 5.0)
    penalty += min(15.0, float(metrics["repair_manual_required_count"]) * 3.0)
    # Timbre that is audibly off but not catastrophic (the 0.25-0.45 review band)
    # used to contribute nothing; a job whose median similarity sits below the
    # pass line should not score ~95.
    penalty += min(
        15.0,
        float(metrics.get("timbre_review_ratio", metrics.get("speaker_review_ratio", 0.0))) * 25.0,
    )
    # Post-fit pacing: cut-off tails (lost words) weigh heaviest, then rushed /
    # dead-air. Previously the score had no pacing term at all.
    penalty += min(
        20.0,
        float(metrics.get("pacing_cutoff_count", 0)) * 3.0
        + float(metrics.get("pacing_overcompressed_count", 0)) * 1.0
        + float(metrics.get("pacing_deadair_count", 0)) * 1.0,
    )
    # Placed-but-buried dubs are effectively undubbed to the listener.
    penalty += min(20.0, float(metrics.get("buried_count", 0)) * 5.0)
    return round(max(0.0, min(100.0, 100.0 - penalty)), 2)


def _gates(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": "coverage",
            "label": "Subtitle window audible coverage",
            "status": "passed" if metrics["coverage_ratio"] >= 0.98 and metrics["audible_failed_count"] == 0 else "failed",
            "value": metrics["coverage_ratio"],
            "threshold": ">=0.98 and audible_failed_count == 0",
        },
        {
            "id": "speaker_consistency",
            "label": "Speaker / timbre consistency",
            "status": (
                "failed"
                if metrics.get("timbre_failed_ratio", metrics["speaker_failed_ratio"]) > 0.15
                else "review"
                if (
                    metrics.get("timbre_review_ratio", 0.0) > 0.30
                    or _below(metrics.get("speaker_median_similarity"), TIMBRE_REVIEW_HIGH)
                    or _below(metrics.get("speaker_centroid_median_similarity"), TIMBRE_REVIEW_HIGH)
                )
                else "passed"
            ),
            "value": {
                "speaker_failed_ratio": metrics["speaker_failed_ratio"],
                "timbre_review_ratio": metrics.get("timbre_review_ratio", 0.0),
                "median_similarity": metrics.get("speaker_median_similarity"),
                "centroid_median_similarity": metrics.get("speaker_centroid_median_similarity"),
            },
            "threshold": "failed_ratio<=0.15 and timbre_review_ratio<=0.30 and medians>=0.45",
        },
        {
            "id": "pacing",
            "label": "Dub pacing (cut-off / rushed / dead air)",
            "status": (
                "failed"
                if metrics.get("pacing_cutoff_count", 0) > 0
                else "review"
                if (metrics.get("pacing_overcompressed_count", 0) + metrics.get("pacing_deadair_count", 0)) > 0
                else "passed"
            ),
            "value": {
                "cutoff_count": metrics.get("pacing_cutoff_count", 0),
                "overcompressed_count": metrics.get("pacing_overcompressed_count", 0),
                "deadair_count": metrics.get("pacing_deadair_count", 0),
            },
            "threshold": "cutoff_count == 0 (review if any rushed / dead air)",
        },
        {
            "id": "audibility",
            "label": "Dub audible over background (SNR)",
            "status": "failed" if metrics.get("buried_count", 0) > 0 else "passed",
            "value": {
                "buried_count": metrics.get("buried_count", 0),
                "buried_segment_ids": metrics.get("buried_segment_ids", []),
                "min_snr_db": metrics.get("min_dub_snr_db"),
            },
            "threshold": f"no placed dub below {DUB_SNR_MIN_DB:g} dB over background",
        },
        {
            "id": "character_voice",
            "label": "Character ledger voice risk",
            "status": "failed" if metrics["character_blocked_count"] > 0 else ("review" if metrics["character_review_count"] > 0 else "passed"),
            "value": {
                "review_count": metrics["character_review_count"],
                "blocked_count": metrics["character_blocked_count"],
                "voice_mismatch_count": metrics["voice_mismatch_count"],
            },
            "threshold": "blocked_count == 0 and review_count == 0",
        },
        {
            "id": "repair_tournament",
            "label": "Repair tournament unresolved items",
            "status": "review" if metrics["repair_manual_required_count"] > 0 else "passed",
            "value": metrics["repair_manual_required_count"],
            "threshold": "manual_required_count == 0",
        },
        {
            "id": "undubbed_coverage",
            "label": "Segments left undubbed in the final mix",
            "status": "passed" if metrics.get("undubbed_count", 0) == 0 else "failed",
            "value": {
                "undubbed_count": metrics.get("undubbed_count", 0),
                "undubbed_ratio": metrics.get("undubbed_ratio", 0.0),
                "skip_reason_counts": metrics.get("skip_reason_counts", {}),
            },
            "threshold": "undubbed_count == 0",
        },
    ]


def _markdown_report(benchmark: dict[str, Any]) -> str:
    metrics = benchmark.get("metrics", {})
    lines = [
        "# Dub Benchmark Report",
        "",
        f"- status: `{benchmark.get('status')}`",
        f"- score: `{benchmark.get('score')}`",
        f"- reasons: `{', '.join(benchmark.get('reasons', [])) or '-'}`",
        "",
        "## Core Metrics",
        "",
        "| metric | value |",
        "| --- | --- |",
    ]
    for key in [
        "total_segment_count",
        "translated_count",
        "coverage_ratio",
        "undubbed_count",
        "audible_failed_count",
        "speaker_failed_ratio",
        "speaker_review_ratio",
        "speaker_median_similarity",
        "pacing_cutoff_count",
        "pacing_overcompressed_count",
        "pacing_deadair_count",
        "intelligibility_failed_ratio",
        "character_review_count",
        "character_blocked_count",
        "voice_mismatch_count",
        "repair_manual_required_count",
    ]:
        lines.append(f"| {key} | {metrics.get(key)} |")
    return "\n".join(lines) + "\n"


def _status_count(quality: dict[str, Any], key: str, status: str) -> int:
    counts = quality.get(key, {})
    if not isinstance(counts, dict):
        return 0
    return _int(counts.get(status))


def _below(value: Any, threshold: float) -> bool:
    return isinstance(value, (int, float)) and value < threshold


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        payload = read_json(path)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _write_json_impl(payload, path, atomic=False, trailing_newline=True)


__all__ = [
    "DubBenchmarkArtifacts",
    "DubBenchmarkRequest",
    "DubBenchmarkResult",
    "build_dub_benchmark",
    "classify_pacing",
]
