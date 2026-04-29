from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

from ..pipeline.manifest import now_iso
from ..types import RenderDubRequest


def write_json(payload: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output_path


def build_timeline_payload(
    *,
    request: RenderDubRequest,
    target_lang: str,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "input": {
            "segments_path": str(request.segments_path),
            "translation_path": str(request.translation_path),
            "background_path": str(request.background_path),
            "task_d_report_paths": [str(path) for path in request.task_d_report_paths],
            "selected_segments_path": str(request.selected_segments_path) if request.selected_segments_path else None,
        },
        "config": {
            "target_lang": target_lang,
            "fit_policy": request.fit_policy,
            "fit_backend": request.fit_backend,
            "mix_profile": request.mix_profile,
            "ducking_mode": request.ducking_mode,
            "output_sample_rate": request.output_sample_rate,
            "quality_gate": request.quality_gate,
        },
        "items": items,
    }


def build_mix_report(
    *,
    request: RenderDubRequest,
    target_lang: str,
    placed_items: list[dict[str, Any]],
    skipped_items: list[dict[str, Any]],
    total_duration_sec: float,
) -> dict[str, Any]:
    fit_counts: dict[str, int] = {}
    skip_counts: dict[str, int] = {}
    for item in placed_items:
        strategy = str(item.get("fit_strategy") or "unknown")
        fit_counts[strategy] = fit_counts.get(strategy, 0) + 1
    for item in skipped_items:
        reason = str(item.get("mix_status") or "skipped")
        skip_counts[reason] = skip_counts.get(reason, 0) + 1
    quality_summary = _build_quality_summary(items=[*placed_items, *skipped_items])
    audible_coverage = _build_audible_coverage(items=[*placed_items, *skipped_items])
    content_quality = _build_content_quality(
        placed_count=len(placed_items),
        skipped_count=len(skipped_items),
        quality_summary=quality_summary,
        audible_coverage=audible_coverage,
    )
    return {
        "input": {
            "segments_path": str(request.segments_path),
            "translation_path": str(request.translation_path),
            "background_path": str(request.background_path),
            "task_d_report_paths": [str(path) for path in request.task_d_report_paths],
            "selected_segments_path": str(request.selected_segments_path) if request.selected_segments_path else None,
        },
        "config": {
            "target_lang": target_lang,
            "fit_policy": request.fit_policy,
            "fit_backend": request.fit_backend,
            "mix_profile": request.mix_profile,
            "ducking_mode": request.ducking_mode,
            "max_compress_ratio": request.max_compress_ratio,
            "background_gain_db": request.background_gain_db,
            "window_ducking_db": request.window_ducking_db,
            "output_sample_rate": request.output_sample_rate,
            "quality_gate": request.quality_gate,
        },
        "stats": {
            "placed_count": len(placed_items),
            "skipped_count": len(skipped_items),
            "fit_strategy_counts": fit_counts,
            "skip_reason_counts": skip_counts,
            "total_duration_sec": round(total_duration_sec, 3),
            "quality_summary": quality_summary,
            "audible_coverage": audible_coverage,
            "content_quality": content_quality,
        },
        "placed_segments": placed_items,
        "skipped_segments": skipped_items,
    }


def build_render_manifest(
    *,
    request: RenderDubRequest,
    target_lang: str,
    dub_voice_path: Path,
    preview_mix_wav_path: Path,
    preview_mix_extra_path: Path | None,
    timeline_path: Path,
    mix_report_path: Path,
    started_at: str,
    finished_at: str,
    elapsed_sec: float,
    placed_count: int,
    skipped_count: int,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "job_id": mix_report_path.parent.name,
        "input": {
            "background_path": str(request.background_path),
            "segments_path": str(request.segments_path),
            "translation_path": str(request.translation_path),
            "task_d_report_paths": [str(path) for path in request.task_d_report_paths],
            "selected_segments_path": str(request.selected_segments_path) if request.selected_segments_path else None,
        },
        "request": {
            "target_lang": target_lang,
            "fit_policy": request.fit_policy,
            "fit_backend": request.fit_backend,
            "mix_profile": request.mix_profile,
            "ducking_mode": request.ducking_mode,
            "output_sample_rate": request.output_sample_rate,
            "max_compress_ratio": request.max_compress_ratio,
            "background_gain_db": request.background_gain_db,
            "window_ducking_db": request.window_ducking_db,
            "preview_format": request.preview_format,
            "selected_segments_path": str(request.selected_segments_path) if request.selected_segments_path else None,
            "quality_gate": request.quality_gate,
        },
        "resolved": {
            "placed_count": placed_count,
            "skipped_count": skipped_count,
            "target_lang": target_lang,
        },
        "artifacts": {
            "dub_voice": str(dub_voice_path),
            "preview_mix_wav": str(preview_mix_wav_path),
            "preview_mix_extra": str(preview_mix_extra_path) if preview_mix_extra_path else None,
            "timeline_json": str(timeline_path),
            "mix_report_json": str(mix_report_path),
        },
        "timing": {
            "started_at": started_at,
            "finished_at": finished_at,
            "elapsed_sec": round(elapsed_sec, 3),
        },
        "status": "failed" if error else "succeeded",
        "error": error,
    }


def _build_quality_summary(*, items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total_count": len(items),
        "overall_status_counts": _count_by(items, "overall_status"),
        "duration_status_counts": _count_by(items, "duration_status"),
        "speaker_status_counts": _count_by(items, "speaker_status"),
        "intelligibility_status_counts": _count_by(items, "intelligibility_status"),
        "mix_status_counts": _count_by(items, "mix_status"),
        "failure_reason_counts": _failure_reason_counts(items),
        "qa_flag_counts": _token_counts(items, "qa_flags"),
        "note_counts": _token_counts(items, "notes"),
        "averages": {
            "speaker_similarity": _average_number(items, "speaker_similarity"),
            "text_similarity": _average_number(items, "text_similarity"),
            "duration_ratio": _average_duration_ratio(items),
            "quality_score": _average_number(items, "quality_score"),
        },
        "medians": {
            "speaker_similarity": _median_number(items, "speaker_similarity"),
            "text_similarity": _median_number(items, "text_similarity"),
            "duration_ratio": _median_duration_ratio(items),
            "quality_score": _median_number(items, "quality_score"),
        },
    }


def _build_content_quality(
    *,
    placed_count: int,
    skipped_count: int,
    quality_summary: dict[str, Any],
    audible_coverage: dict[str, Any],
) -> dict[str, Any]:
    total_count = int(quality_summary.get("total_count") or 0)
    overall_counts = quality_summary.get("overall_status_counts", {})
    speaker_counts = quality_summary.get("speaker_status_counts", {})
    text_counts = quality_summary.get("intelligibility_status_counts", {})
    failed_count = int(overall_counts.get("failed", 0)) if isinstance(overall_counts, dict) else 0
    speaker_failed = int(speaker_counts.get("failed", 0)) if isinstance(speaker_counts, dict) else 0
    intelligibility_failed = int(text_counts.get("failed", 0)) if isinstance(text_counts, dict) else 0
    coverage_ratio = placed_count / max(total_count, 1)
    failed_ratio = failed_count / max(total_count, 1)
    speaker_failed_ratio = speaker_failed / max(total_count, 1)
    intelligibility_failed_ratio = intelligibility_failed / max(total_count, 1)
    audible_coverage_failed = int(audible_coverage.get("failed_count") or 0)

    reasons: list[str] = []
    if total_count == 0:
        reasons.append("no_renderable_segments")
    if skipped_count > 0 or coverage_ratio < 0.98:
        reasons.append("coverage_below_deliverable_threshold")
    if failed_ratio > 0.05:
        reasons.append("upstream_failed_segments")
    if speaker_failed_ratio > 0.10:
        reasons.append("speaker_similarity_failed")
    if intelligibility_failed_ratio > 0.10:
        reasons.append("intelligibility_failed")
    if audible_coverage_failed > 0:
        reasons.append("audible_coverage_failed")

    if total_count == 0 or skipped_count > max(0, total_count * 0.20) or audible_coverage_failed > 0:
        status = "blocked"
    elif reasons:
        status = "review_required"
    else:
        status = "deliverable"
    return {
        "status": status,
        "coverage_ratio": round(coverage_ratio, 4),
        "failed_ratio": round(failed_ratio, 4),
        "speaker_failed_ratio": round(speaker_failed_ratio, 4),
        "intelligibility_failed_ratio": round(intelligibility_failed_ratio, 4),
        "reasons": reasons,
    }


def _build_audible_coverage(*, items: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[tuple[str, float]] = []
    failed_segment_ids: list[str] = []
    for item in items:
        if item.get("subtitle_window") is None:
            continue
        ratio = item.get("subtitle_coverage_ratio")
        if not isinstance(ratio, (int, float)):
            ratio = 0.0
        ratio = max(0.0, min(1.0, float(ratio)))
        segment_id = str(item.get("segment_id") or "")
        rows.append((segment_id, ratio))
        if ratio < 0.50:
            failed_segment_ids.append(segment_id)

    ratios = [ratio for _segment_id, ratio in rows]
    return {
        "subtitle_window_count": len(rows),
        "failed_count": len(failed_segment_ids),
        "failed_segment_ids": failed_segment_ids,
        "min_coverage_ratio": round(min(ratios), 4) if ratios else None,
        "average_coverage_ratio": round(statistics.mean(ratios), 4) if ratios else None,
    }


def _count_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(item.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _token_counts(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        values = item.get(key) or []
        if not isinstance(values, list):
            continue
        for value in values:
            token = str(value)
            counts[token] = counts.get(token, 0) + 1
    return dict(sorted(counts.items(), key=lambda pair: (-pair[1], pair[0])))


def _failure_reason_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        if item.get("overall_status") != "failed":
            continue
        reasons: list[str] = []
        if item.get("duration_status") == "failed":
            reasons.append("duration")
        if item.get("speaker_status") == "failed":
            reasons.append("speaker")
        if item.get("intelligibility_status") == "failed":
            reasons.append("intelligibility")
        reason = "+".join(reasons) if reasons else "overall"
        counts[reason] = counts.get(reason, 0) + 1
    return dict(sorted(counts.items(), key=lambda pair: (-pair[1], pair[0])))


def _average_number(items: list[dict[str, Any]], key: str) -> float | None:
    values = _numbers(items, key)
    if not values:
        return None
    return round(statistics.mean(values), 4)


def _median_number(items: list[dict[str, Any]], key: str) -> float | None:
    values = _numbers(items, key)
    if not values:
        return None
    return round(statistics.median(values), 4)


def _numbers(items: list[dict[str, Any]], key: str) -> list[float]:
    values: list[float] = []
    for item in items:
        value = item.get(key)
        if isinstance(value, (int, float)):
            values.append(float(value))
    return values


def _average_duration_ratio(items: list[dict[str, Any]]) -> float | None:
    values = _duration_ratios(items)
    if not values:
        return None
    return round(statistics.mean(values), 4)


def _median_duration_ratio(items: list[dict[str, Any]]) -> float | None:
    values = _duration_ratios(items)
    if not values:
        return None
    return round(statistics.median(values), 4)


def _duration_ratios(items: list[dict[str, Any]]) -> list[float]:
    ratios: list[float] = []
    for item in items:
        generated = item.get("generated_duration_sec")
        source = item.get("source_duration_sec")
        if not isinstance(generated, (int, float)) or not isinstance(source, (int, float)) or source <= 0:
            continue
        ratios.append(float(generated) / float(source))
    return ratios


__all__ = [
    "build_mix_report",
    "build_render_manifest",
    "build_timeline_payload",
    "now_iso",
    "write_json",
]
