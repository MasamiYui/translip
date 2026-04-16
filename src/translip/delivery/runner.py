from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..exceptions import TranslipError
from ..types import ExportVideoArtifacts, ExportVideoRequest, ExportVideoResult, PipelineRequest
from ..utils.ffmpeg import mux_video_with_audio, probe_media
from ..utils.files import ensure_directory
from .export import build_delivery_manifest, build_delivery_report, now_iso, write_json


@dataclass(frozen=True, slots=True)
class ResolvedDeliveryInputs:
    video_path: Path
    preview_mix_path: Path | None
    dub_voice_path: Path | None


def resolve_delivery_inputs(request: PipelineRequest) -> ResolvedDeliveryInputs:
    clean_video_path = request.output_root / "subtitle-erase" / "clean_video.mp4"
    video_source = request.delivery_policy.get("video_source", "original")
    clean_video_available = _is_usable_clean_video(clean_video_path)
    if video_source == "clean":
        if not clean_video_available:
            raise FileNotFoundError("clean video requested but missing or invalid")
        video_path = clean_video_path
    elif video_source == "clean_if_available" and clean_video_available:
        video_path = clean_video_path
    else:
        video_path = Path(request.input_path)

    target_lang = request.target_lang
    return ResolvedDeliveryInputs(
        video_path=video_path,
        preview_mix_path=request.output_root / "task-e" / "voice" / f"preview_mix.{target_lang}.wav",
        dub_voice_path=request.output_root / "task-e" / "voice" / f"dub_voice.{target_lang}.wav",
    )


def _is_usable_clean_video(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        media_info = probe_media(path)
    except Exception:
        return False
    return media_info.media_type == "video"


def export_video(request: ExportVideoRequest) -> ExportVideoResult:
    normalized_request = _resolve_request(request)
    ensure_directory(normalized_request.output_dir)

    task_e_manifest_path = normalized_request.task_e_dir / "task-e-manifest.json"
    task_e_manifest = _load_json(task_e_manifest_path)
    preview_audio_path = _resolve_preview_audio_path(normalized_request, task_e_manifest)
    dub_audio_path = _resolve_dub_audio_path(normalized_request, task_e_manifest)
    target_lang = _resolve_target_lang(normalized_request, task_e_manifest)
    normalized_request = ExportVideoRequest(
        input_video_path=normalized_request.input_video_path,
        pipeline_root=normalized_request.pipeline_root,
        task_e_dir=normalized_request.task_e_dir,
        output_dir=normalized_request.output_dir,
        target_lang=target_lang,
        export_preview=normalized_request.export_preview,
        export_dub=normalized_request.export_dub,
        container=normalized_request.container,
        video_codec=normalized_request.video_codec,
        audio_codec=normalized_request.audio_codec,
        audio_bitrate=normalized_request.audio_bitrate,
        end_policy=normalized_request.end_policy,
        overwrite=normalized_request.overwrite,
        keep_temp=normalized_request.keep_temp,
    )

    manifest_path = normalized_request.output_dir / "delivery-manifest.json"
    report_path = normalized_request.output_dir / "delivery-report.json"
    started_at = now_iso()
    started_monotonic = time.monotonic()

    try:
        input_video_info = probe_media(normalized_request.input_video_path)
        outputs: list[dict[str, Any]] = []
        preview_video_path: Path | None = None
        dub_video_path: Path | None = None

        if normalized_request.export_preview:
            preview_video_path = _build_output_video_path(
                normalized_request.output_dir / "final-preview",
                stem=f"final_preview.{target_lang}",
                container=normalized_request.container,
            )
            mux_video_with_audio(
                input_video_path=normalized_request.input_video_path,
                input_audio_path=preview_audio_path,
                output_path=preview_video_path,
                video_codec=normalized_request.video_codec,
                audio_codec=normalized_request.audio_codec,
                audio_bitrate=normalized_request.audio_bitrate,
                end_policy=normalized_request.end_policy,
            )
            outputs.append(
                _output_payload(
                    kind="preview",
                    output_path=preview_video_path,
                )
            )

        if normalized_request.export_dub:
            dub_video_path = _build_output_video_path(
                normalized_request.output_dir / "final-dub",
                stem=f"final_dub.{target_lang}",
                container=normalized_request.container,
            )
            mux_video_with_audio(
                input_video_path=normalized_request.input_video_path,
                input_audio_path=dub_audio_path,
                output_path=dub_video_path,
                video_codec=normalized_request.video_codec,
                audio_codec=normalized_request.audio_codec,
                audio_bitrate=normalized_request.audio_bitrate,
                end_policy=normalized_request.end_policy,
            )
            outputs.append(
                _output_payload(
                    kind="dub",
                    output_path=dub_video_path,
                )
            )

        manifest = build_delivery_manifest(
            request=normalized_request,
            input_video_info=input_video_info,
            task_e_manifest_path=task_e_manifest_path,
            preview_audio_path=preview_audio_path,
            dub_audio_path=dub_audio_path,
            preview_video_path=preview_video_path,
            dub_video_path=dub_video_path,
            started_at=started_at,
            finished_at=now_iso(),
            elapsed_sec=time.monotonic() - started_monotonic,
        )
        report = build_delivery_report(
            request=normalized_request,
            input_video_info=input_video_info,
            target_lang=target_lang,
            outputs=outputs,
            preview_audio_path=preview_audio_path,
            dub_audio_path=dub_audio_path,
            task_e_manifest_path=task_e_manifest_path,
            status="succeeded",
        )
        write_json(manifest, manifest_path)
        write_json(report, report_path)
        return ExportVideoResult(
            request=normalized_request,
            artifacts=ExportVideoArtifacts(
                output_dir=normalized_request.output_dir,
                preview_video_path=preview_video_path,
                dub_video_path=dub_video_path,
                manifest_path=manifest_path,
                report_path=report_path,
            ),
            manifest=manifest,
            report=report,
        )
    except Exception as exc:
        input_video_info = probe_media(normalized_request.input_video_path)
        manifest = build_delivery_manifest(
            request=normalized_request,
            input_video_info=input_video_info,
            task_e_manifest_path=task_e_manifest_path,
            preview_audio_path=preview_audio_path,
            dub_audio_path=dub_audio_path,
            preview_video_path=None,
            dub_video_path=None,
            started_at=started_at,
            finished_at=now_iso(),
            elapsed_sec=time.monotonic() - started_monotonic,
            error=str(exc),
        )
        report = build_delivery_report(
            request=normalized_request,
            input_video_info=input_video_info,
            target_lang=target_lang,
            outputs=[],
            preview_audio_path=preview_audio_path,
            dub_audio_path=dub_audio_path,
            task_e_manifest_path=task_e_manifest_path,
            status="failed",
        )
        write_json(manifest, manifest_path)
        write_json(report, report_path)
        raise


def _resolve_request(request: ExportVideoRequest) -> ExportVideoRequest:
    normalized = request.normalized()
    if not normalized.export_preview and not normalized.export_dub:
        raise TranslipError("At least one export target must be enabled for Task G")

    pipeline_root = normalized.pipeline_root
    task_e_dir = normalized.task_e_dir
    if task_e_dir is None and pipeline_root is not None:
        task_e_dir = pipeline_root / "task-e" / "voice"
    if task_e_dir is None:
        raise TranslipError("Task G requires task_e_dir or pipeline_root")
    if not task_e_dir.exists():
        raise TranslipError(f"Task E directory does not exist: {task_e_dir}")

    input_video_path = normalized.input_video_path
    if input_video_path is None and pipeline_root is not None:
        pipeline_manifest_path = pipeline_root / "pipeline-manifest.json"
        if pipeline_manifest_path.exists():
            payload = _load_json(pipeline_manifest_path)
            inferred = payload.get("request", {}).get("input_path")
            if inferred:
                input_video_path = Path(str(inferred)).expanduser().resolve()
    if input_video_path is None:
        raise TranslipError("Task G requires input_video_path or pipeline_root with pipeline-manifest.json")
    if not input_video_path.exists():
        raise TranslipError(f"Task G input video does not exist: {input_video_path}")

    output_dir = normalized.output_dir
    if output_dir is None:
        if pipeline_root is not None:
            output_dir = pipeline_root / "task-g" / "delivery"
        else:
            output_dir = Path("output-delivery").resolve()

    return ExportVideoRequest(
        input_video_path=input_video_path,
        pipeline_root=pipeline_root,
        task_e_dir=task_e_dir,
        output_dir=output_dir,
        target_lang=normalized.target_lang,
        export_preview=normalized.export_preview,
        export_dub=normalized.export_dub,
        container=normalized.container,
        video_codec=normalized.video_codec,
        audio_codec=normalized.audio_codec,
        audio_bitrate=normalized.audio_bitrate,
        end_policy=normalized.end_policy,
        overwrite=normalized.overwrite,
        keep_temp=normalized.keep_temp,
    )


def _resolve_target_lang(request: ExportVideoRequest, task_e_manifest: dict[str, Any]) -> str:
    if request.target_lang:
        return request.target_lang
    return str(
        task_e_manifest.get("resolved", {}).get("target_lang")
        or task_e_manifest.get("request", {}).get("target_lang")
        or "en"
    )


def _resolve_preview_audio_path(request: ExportVideoRequest, task_e_manifest: dict[str, Any]) -> Path:
    path = task_e_manifest.get("artifacts", {}).get("preview_mix_wav")
    if path:
        resolved = Path(str(path)).expanduser().resolve()
    else:
        target_lang = _resolve_target_lang(request, task_e_manifest)
        resolved = (request.task_e_dir / f"preview_mix.{target_lang}.wav").resolve()
    if not resolved.exists():
        raise TranslipError(f"Task G preview mix does not exist: {resolved}")
    return resolved


def _resolve_dub_audio_path(request: ExportVideoRequest, task_e_manifest: dict[str, Any]) -> Path:
    path = task_e_manifest.get("artifacts", {}).get("dub_voice")
    if path:
        resolved = Path(str(path)).expanduser().resolve()
    else:
        target_lang = _resolve_target_lang(request, task_e_manifest)
        resolved = (request.task_e_dir / f"dub_voice.{target_lang}.wav").resolve()
    if not resolved.exists():
        raise TranslipError(f"Task G dub voice does not exist: {resolved}")
    return resolved


def _build_output_video_path(output_dir: Path, *, stem: str, container: str) -> Path:
    ensure_directory(output_dir)
    return output_dir / f"{stem}.{container}"


def _output_payload(*, kind: str, output_path: Path) -> dict[str, Any]:
    media_info = probe_media(output_path)
    return {
        "kind": kind,
        "status": "succeeded",
        "path": str(output_path),
        "file_size_bytes": output_path.stat().st_size,
        "duration_sec": round(media_info.duration_sec, 3),
        "format_name": media_info.format_name,
    }


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


__all__ = ["export_video"]
