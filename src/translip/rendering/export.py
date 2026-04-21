from __future__ import annotations

import json
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


__all__ = [
    "build_mix_report",
    "build_render_manifest",
    "build_timeline_payload",
    "now_iso",
    "write_json",
]
