from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..pipeline.manifest import now_iso
from ..types import TranslationRequest


def write_json(payload: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output_path


def write_translation_srt(segments: list[dict[str, Any]], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for index, segment in enumerate(segments, start=1):
        lines.extend(
            [
                str(index),
                f"{_srt_timestamp(float(segment['start']))} --> {_srt_timestamp(float(segment['end']))}",
                f"[{segment['speaker_label']}] {segment['target_text']}",
                "",
            ]
        )
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def build_translation_payload(
    *,
    request: TranslationRequest,
    backend_name: str,
    resolved_model: str,
    resolved_device: str | None,
    output_tag: str,
    segments: list[dict[str, Any]],
    units: list[dict[str, Any]],
    glossary_match_count: int,
) -> dict[str, Any]:
    qa_counts: dict[str, int] = {}
    fit_counts: dict[str, int] = {}
    for segment in segments:
        fit_level = segment["duration_budget"]["fit_level"]
        fit_counts[fit_level] = fit_counts.get(fit_level, 0) + 1
        for flag in segment["qa_flags"]:
            qa_counts[flag] = qa_counts.get(flag, 0) + 1
    return {
        "input": {
            "segments_path": str(request.segments_path),
            "profiles_path": str(request.profiles_path),
            "glossary_path": str(request.glossary_path) if request.glossary_path else None,
        },
        "backend": {
            "translation_backend": backend_name,
            "model": resolved_model,
            "device": resolved_device,
            "source_lang": request.source_lang,
            "target_lang": request.target_lang,
            "output_tag": output_tag,
        },
        "stats": {
            "segment_count": len(segments),
            "unit_count": len(units),
            "speaker_count": len({segment["speaker_label"] for segment in segments}),
            "glossary_match_count": glossary_match_count,
            "qa_flag_counts": qa_counts,
            "duration_fit_counts": fit_counts,
        },
        "segments": segments,
    }


def build_editable_payload(
    *,
    request: TranslationRequest,
    backend_name: str,
    resolved_model: str,
    output_tag: str,
    units: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "input": {
            "segments_path": str(request.segments_path),
            "profiles_path": str(request.profiles_path),
            "glossary_path": str(request.glossary_path) if request.glossary_path else None,
        },
        "backend": {
            "translation_backend": backend_name,
            "model": resolved_model,
            "source_lang": request.source_lang,
            "target_lang": request.target_lang,
            "output_tag": output_tag,
        },
        "units": units,
    }


def build_translation_manifest(
    *,
    request: TranslationRequest,
    output_tag: str,
    translation_json_path: Path,
    editable_json_path: Path,
    srt_path: Path,
    started_at: str,
    finished_at: str,
    elapsed_sec: float,
    resolved: dict[str, Any],
    stats: dict[str, Any],
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "job_id": translation_json_path.parent.name,
        "input": {
            "segments_path": str(request.segments_path),
            "profiles_path": str(request.profiles_path),
            "glossary_path": str(request.glossary_path) if request.glossary_path else None,
        },
        "request": {
            "source_lang": request.source_lang,
            "target_lang": request.target_lang,
            "backend": request.backend,
            "device": request.device,
            "batch_size": request.batch_size,
            "local_model": request.local_model,
            "api_model": request.api_model,
            "api_base_url": request.api_base_url,
        },
        "resolved": resolved | stats | {"output_tag": output_tag},
        "artifacts": {
            "translation_json": str(translation_json_path),
            "editable_json": str(editable_json_path),
            "translation_srt": str(srt_path),
        },
        "timing": {
            "started_at": started_at,
            "finished_at": finished_at,
            "elapsed_sec": round(elapsed_sec, 3),
        },
        "status": "failed" if error else "succeeded",
        "error": error,
    }


def _srt_timestamp(seconds: float) -> str:
    millis = int(round(seconds * 1000))
    hours, remainder = divmod(millis, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, ms = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


__all__ = [
    "build_editable_payload",
    "build_translation_manifest",
    "build_translation_payload",
    "now_iso",
    "write_json",
    "write_translation_srt",
]
