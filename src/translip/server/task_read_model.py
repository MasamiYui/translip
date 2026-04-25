from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from .models import Task
from .task_config import normalize_task_config, normalize_task_delivery_config

_INTENT_TO_PROFILE = {
    "dub_final": "dub_no_subtitles",
    "bilingual_review": "bilingual_review",
    "english_subtitle": "english_subtitle_burned",
    "fast_validation": "preview_only",
}


def infer_output_intent(config: Mapping[str, Any] | None) -> str:
    pipeline = normalize_task_config(config)
    explicit = pipeline.get("output_intent")
    if isinstance(explicit, str) and explicit:
        return explicit

    template = pipeline.get("template")
    video_source = pipeline.get("video_source")
    if template == "asr-dub+ocr-subs+erase" or video_source in {"clean", "clean_if_available"}:
        return "english_subtitle"
    if template == "asr-dub+ocr-subs":
        return "bilingual_review"
    return "dub_final"


def infer_quality_preset(config: Mapping[str, Any] | None) -> str:
    pipeline = normalize_task_config(config)
    explicit = pipeline.get("quality_preset")
    if isinstance(explicit, str) and explicit:
        return explicit
    return "standard"


def build_asset_summary(task: Task) -> dict[str, dict[str, dict[str, str | None]]]:
    root = Path(task.output_root)
    target_lang = task.target_lang

    preview_audio = root / "task-e" / "voice" / f"preview_mix.{target_lang}.wav"
    dub_audio = root / "task-e" / "voice" / f"dub_voice.{target_lang}.wav"
    clean_video = root / "subtitle-erase" / "clean_video.mp4"
    ocr_srt = root / "ocr-translate" / f"ocr_subtitles.{target_lang}.srt"
    asr_srt = _first_existing(
        [
            root / "task-c" / "voice" / f"translation.{target_lang}.srt",
            root / "task-c" / f"translation.{target_lang}.srt",
        ]
    )
    preview_video = _first_glob(root, f"final_preview.{target_lang}.mp4")
    dub_video = _first_glob(root, f"final_dub.{target_lang}.mp4")
    subtitle_preview = _first_glob(root, "subtitle-preview.mp4")

    return {
        "video": {
            "original": _asset_entry(Path(task.input_path)),
            "clean": _asset_entry(clean_video, root),
        },
        "audio": {
            "preview": _asset_entry(preview_audio, root),
            "dub": _asset_entry(dub_audio, root),
        },
        "subtitles": {
            "ocr_translated": _asset_entry(ocr_srt, root),
            "asr_translated": _asset_entry(asr_srt, root),
        },
        "exports": {
            "subtitle_preview": _asset_entry(subtitle_preview, root),
            "final_preview": _asset_entry(preview_video, root),
            "final_dub": _asset_entry(dub_video, root),
        },
    }


def build_export_readiness(
    task: Task,
    *,
    output_intent: str,
    asset_summary: Mapping[str, Any],
) -> dict[str, Any]:
    recommended_profile = _INTENT_TO_PROFILE.get(output_intent, "dub_no_subtitles")
    exported = any(
        asset_summary["exports"][key]["status"] == "available"
        for key in ("final_preview", "final_dub")
    )

    if task.status in {"pending", "running"}:
        return {
            "status": "not_ready",
            "recommended_profile": recommended_profile,
            "summary": "task_running",
            "blockers": [],
        }

    if task.status == "failed":
        return {
            "status": "blocked",
            "recommended_profile": recommended_profile,
            "summary": "task_failed",
            "blockers": [
                {
                    "code": "task_failed",
                    "message": "任务尚未成功完成，当前无法导出。",
                    "action": "rerun_task",
                    "action_label": "从失败阶段重跑",
                }
            ],
        }

    has_original = _available(asset_summary, "video", "original")
    has_clean = _available(asset_summary, "video", "clean")
    has_preview_audio = _available(asset_summary, "audio", "preview")
    has_dub_audio = _available(asset_summary, "audio", "dub")
    has_ocr = _available(asset_summary, "subtitles", "ocr_translated")
    has_asr = _available(asset_summary, "subtitles", "asr_translated")

    blockers: list[dict[str, str]] = []

    if output_intent == "english_subtitle":
        if not has_clean:
            blockers.append(
                {
                    "code": "missing_clean_video",
                    "message": "当前没有干净画面，无法导出英文字幕版。",
                    "action": "rerun_subtitle_erase",
                    "action_label": "补跑擦字幕",
                }
            )
        if not (has_ocr or has_asr):
            blockers.append(
                {
                    "code": "missing_english_subtitles",
                    "message": "当前没有可用于烧录的英文字幕。",
                    "action": "rerun_subtitle_generation",
                    "action_label": "补跑字幕链路",
                }
            )
        if not (has_dub_audio or has_preview_audio):
            blockers.append(
                {
                    "code": "missing_audio_track",
                    "message": "当前没有可用于导出的目标音轨。",
                    "action": "rerun_audio_pipeline",
                    "action_label": "补跑音频链路",
                }
            )
    elif output_intent == "bilingual_review":
        if not has_original:
            blockers.append(
                {
                    "code": "missing_original_video",
                    "message": "当前没有原视频，无法导出双语审片版。",
                    "action": "check_input_video",
                    "action_label": "检查输入视频",
                }
            )
        if not (has_ocr or has_asr):
            blockers.append(
                {
                    "code": "missing_english_subtitles",
                    "message": "当前没有可用的英文字幕。",
                    "action": "rerun_subtitle_generation",
                    "action_label": "补跑字幕链路",
                }
            )
        if not (has_preview_audio or has_dub_audio):
            blockers.append(
                {
                    "code": "missing_audio_track",
                    "message": "当前没有可用于导出的目标音轨。",
                    "action": "rerun_audio_pipeline",
                    "action_label": "补跑音频链路",
                }
            )
    elif output_intent == "fast_validation":
        if not (has_preview_audio or has_dub_audio):
            blockers.append(
                {
                    "code": "missing_audio_track",
                    "message": "当前还没有可用于预览的音轨。",
                    "action": "rerun_audio_pipeline",
                    "action_label": "补跑音频链路",
                }
            )
        if has_preview_audio:
            recommended_profile = "preview_only"
        elif has_dub_audio:
            recommended_profile = "dub_no_subtitles"
    else:
        if has_dub_audio:
            recommended_profile = "dub_no_subtitles"
        elif has_preview_audio:
            recommended_profile = "preview_only"
        else:
            blockers.append(
                {
                    "code": "missing_audio_track",
                    "message": "当前还没有可用于导出的目标音轨。",
                    "action": "rerun_audio_pipeline",
                    "action_label": "补跑音频链路",
                }
            )

    if blockers:
        return {
            "status": "blocked",
            "recommended_profile": recommended_profile,
            "summary": "missing_required_assets",
            "blockers": blockers,
        }

    return {
        "status": "exported" if exported else "ready",
        "recommended_profile": recommended_profile,
        "summary": "ready_for_export" if not exported else "already_exported",
        "blockers": [],
    }


def detect_hard_subtitle_status(task: Task) -> str:
    root = Path(task.output_root)
    candidates = [
        root / "ocr-detect" / "ocr_subtitles.source.srt",
        root / "ocr-detect" / "ocr_events.json",
        root / "ocr-detect" / "detection.json",
    ]
    return "confirmed" if any(_has_meaningful_content(path) for path in candidates) else "none"


def build_last_export_summary(
    task: Task,
    *,
    asset_summary: Mapping[str, Any],
) -> dict[str, Any]:
    root = Path(task.output_root)
    delivery_config = normalize_task_delivery_config(task.config)
    report_summary = _last_export_files_from_report(root, delivery_config=delivery_config)
    report_path: Path | None = None
    if report_summary:
        files, exported_paths, report_path = report_summary
    else:
        files = []
        exported_paths: list[Path] = []

        for key, label in (("final_preview", "预览成品"), ("final_dub", "正式成品")):
            rel_path = asset_summary["exports"][key]["path"]
            if rel_path:
                files.append({"kind": key, "label": label, "path": rel_path})
                exported_paths.append(root / rel_path)

    if not files:
        return {
            "status": "not_exported",
            "profile": None,
            "updated_at": None,
            "files": [],
        }

    updated_at = None
    if report_path and report_path.exists():
        updated_at = datetime.fromtimestamp(report_path.stat().st_mtime)
    elif exported_paths:
        latest_mtime = max(path.stat().st_mtime for path in exported_paths if path.exists())
        updated_at = datetime.fromtimestamp(latest_mtime)

    return {
        "status": "exported",
        "profile": _profile_from_delivery_config(delivery_config),
        "updated_at": updated_at,
        "files": files,
    }


def build_transcription_correction_summary(task: Task) -> dict[str, Any]:
    report_path = Path(task.output_root) / "asr-ocr-correct" / "voice" / "correction-report.json"
    if not report_path.exists():
        return {
            "status": "not_available",
            "corrected_count": 0,
            "kept_asr_count": 0,
            "review_count": 0,
            "ocr_only_count": 0,
        }
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "status": "unreadable",
            "corrected_count": 0,
            "kept_asr_count": 0,
            "review_count": 0,
            "ocr_only_count": 0,
        }
    summary = dict(payload.get("summary") or {})
    return {"status": "available", **summary}


def _profile_from_delivery_config(delivery_config: Mapping[str, Any]) -> str:
    mode = delivery_config.get("subtitle_mode", "none")
    if mode == "bilingual":
        return "bilingual_review"
    if mode == "english_only":
        return "english_subtitle_burned"
    return "dub_no_subtitles"


def _last_export_files_from_report(
    root: Path,
    *,
    delivery_config: Mapping[str, Any],
) -> tuple[list[dict[str, str]], list[Path], Path] | None:
    report_path = _latest_delivery_report_path(root)
    if report_path is None:
        return None
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    outputs = payload.get("outputs")
    if not isinstance(outputs, list):
        return None

    files: list[dict[str, str]] = []
    exported_paths: list[Path] = []
    for output in outputs:
        if not isinstance(output, Mapping):
            continue
        if output.get("status", "succeeded") != "succeeded":
            continue
        raw_path = output.get("path")
        if not raw_path:
            continue
        path = Path(str(raw_path)).expanduser()
        if not path.is_absolute():
            path = root / path
        path = path.resolve()
        if not path.exists():
            continue
        kind = str(output.get("kind") or _export_kind_from_path(path))
        files.append(
            {
                "kind": kind,
                "label": _export_label(kind, delivery_config=delivery_config),
                "path": str(path.relative_to(root)) if path.is_relative_to(root) else str(path),
            }
        )
        exported_paths.append(path)
    return files, exported_paths, report_path


def _latest_delivery_report_path(root: Path) -> Path | None:
    candidates = [
        root / "task-g" / "delivery-report.json",
        root / "task-g" / "delivery" / "delivery-report.json",
    ]
    existing = [path for path in candidates if path.exists()]
    if not existing:
        return None
    return max(existing, key=lambda path: path.stat().st_mtime)


def _export_kind_from_path(path: Path) -> str:
    if "final_dub" in path.name:
        return "dub"
    if "final_preview" in path.name:
        return "preview"
    return "export"


def _export_label(kind: str, *, delivery_config: Mapping[str, Any]) -> str:
    if kind in {"preview", "final_preview"}:
        if delivery_config.get("export_preview") is True and delivery_config.get("export_dub") is False:
            return "正式成品"
        return "预览成品"
    if kind in {"dub", "final_dub"}:
        return "纯配音质检版"
    return "成品文件"


def _asset_entry(path: Path | None, root: Path | None = None) -> dict[str, str | None]:
    if not path or not path.exists():
        return {"status": "missing", "path": None}
    stored_path = str(path.relative_to(root)) if root and path.is_relative_to(root) else str(path)
    return {"status": "available", "path": stored_path}


def _available(asset_summary: Mapping[str, Any], group: str, key: str) -> bool:
    return asset_summary[group][key]["status"] == "available"


def _first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def _first_glob(root: Path, pattern: str) -> Path | None:
    for path in sorted(root.rglob(pattern)):
        if path.is_file():
            return path
    return None


def _has_meaningful_content(path: Path) -> bool:
    if not path.exists() or not path.is_file():
        return False
    try:
        return bool(path.read_text(encoding="utf-8").strip())
    except UnicodeDecodeError:
        return path.stat().st_size > 0


__all__ = [
    "build_asset_summary",
    "build_export_readiness",
    "build_last_export_summary",
    "build_transcription_correction_summary",
    "detect_hard_subtitle_status",
    "infer_output_intent",
    "infer_quality_preset",
]
