from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..pipeline.manifest import now_iso
from ..types import ExportVideoRequest, MediaInfo


def write_json(payload: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output_path


def build_delivery_manifest(
    *,
    request: ExportVideoRequest,
    input_video_info: MediaInfo,
    task_e_manifest_path: Path,
    preview_audio_path: Path,
    dub_audio_path: Path,
    preview_video_path: Path | None,
    dub_video_path: Path | None,
    started_at: str,
    finished_at: str,
    elapsed_sec: float,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "job_id": request.output_dir.name if request.output_dir is not None else "delivery",
        "input": {
            "video_path": str(request.input_video_path),
            "video_duration_sec": round(input_video_info.duration_sec, 3),
            "format_name": input_video_info.format_name,
            "task_e_manifest_path": str(task_e_manifest_path),
            "preview_audio_path": str(preview_audio_path),
            "dub_audio_path": str(dub_audio_path),
        },
        "request": {
            "pipeline_root": str(request.pipeline_root) if request.pipeline_root else None,
            "task_e_dir": str(request.task_e_dir) if request.task_e_dir else None,
            "output_dir": str(request.output_dir) if request.output_dir else None,
            "target_lang": request.target_lang,
            "export_preview": request.export_preview,
            "export_dub": request.export_dub,
            "container": request.container,
            "video_codec": request.video_codec,
            "audio_codec": request.audio_codec,
            "audio_bitrate": request.audio_bitrate,
            "end_policy": request.end_policy,
            "overwrite": request.overwrite,
            "keep_temp": request.keep_temp,
            "subtitle_mode": request.subtitle_mode,
            "subtitle_source": request.subtitle_source,
            "subtitle_style": request.subtitle_style.__dict__ if request.subtitle_style else None,
            "bilingual_chinese_position": request.bilingual_chinese_position,
            "bilingual_english_position": request.bilingual_english_position,
        },
        "artifacts": {
            "final_preview_video": str(preview_video_path) if preview_video_path else None,
            "final_dub_video": str(dub_video_path) if dub_video_path else None,
        },
        "timing": {
            "started_at": started_at,
            "finished_at": finished_at,
            "elapsed_sec": round(elapsed_sec, 3),
        },
        "status": "failed" if error else "succeeded",
        "error": error,
    }


def build_delivery_report(
    *,
    request: ExportVideoRequest,
    input_video_info: MediaInfo,
    target_lang: str,
    outputs: list[dict[str, Any]],
    preview_audio_path: Path,
    dub_audio_path: Path,
    task_e_manifest_path: Path,
    status: str,
) -> dict[str, Any]:
    requested_exports: list[str] = []
    if request.export_preview:
        requested_exports.append("preview")
    if request.export_dub:
        requested_exports.append("dub")
    failed_count = sum(1 for item in outputs if item.get("status") != "succeeded")
    return {
        "status": status,
        "summary": {
            "requested_exports": requested_exports,
            "exported_count": sum(1 for item in outputs if item.get("status") == "succeeded"),
            "failed_count": failed_count,
            "target_lang": target_lang,
        },
        "input": {
            "video_path": str(request.input_video_path),
            "video_duration_sec": round(input_video_info.duration_sec, 3),
            "task_e_manifest_path": str(task_e_manifest_path),
            "preview_audio_path": str(preview_audio_path),
            "dub_audio_path": str(dub_audio_path),
        },
        "config": {
            "container": request.container,
            "video_codec": request.video_codec,
            "audio_codec": request.audio_codec,
            "audio_bitrate": request.audio_bitrate,
            "end_policy": request.end_policy,
            "subtitle_mode": request.subtitle_mode,
            "subtitle_source": request.subtitle_source,
            "subtitle_style": request.subtitle_style.__dict__ if request.subtitle_style else None,
            "bilingual_chinese_position": request.bilingual_chinese_position,
            "bilingual_english_position": request.bilingual_english_position,
        },
        "outputs": outputs,
    }


__all__ = [
    "build_delivery_manifest",
    "build_delivery_report",
    "now_iso",
    "write_json",
]
