from __future__ import annotations

import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from ..config import DEFAULT_SUBTITLE_FONT_CJK
from ..exceptions import TranslipError
from ..subtitles.burn import merge_bilingual_ass, recommend_style, srt_to_ass
from ..types import ExportVideoArtifacts, ExportVideoRequest, ExportVideoResult, PipelineRequest, SubtitleStyle
from ..utils.ffmpeg import (
    burn_subtitle_and_mux,
    mux_video_with_audio,
    mux_with_soft_subtitle,
    probe_media,
    probe_video_resolution,
)
from ..utils.files import ensure_directory
from ..utils.io import read_json
from .export import build_delivery_manifest, build_delivery_report, now_iso, write_json


@dataclass(frozen=True, slots=True)
class ResolvedDeliveryInputs:
    video_path: Path
    preview_mix_path: Path | None
    dub_voice_path: Path | None
    clean_video_path: Path | None = None


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
        preview_mix_path=request.output_root / "render" / "voice" / f"preview_mix.{target_lang}.wav",
        dub_voice_path=request.output_root / "render" / "voice" / f"dub_voice.{target_lang}.wav",
        clean_video_path=clean_video_path if clean_video_available else None,
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

    task_e_manifest_path = normalized_request.task_e_dir / "render-manifest.json"
    task_e_manifest = _load_json(task_e_manifest_path)
    task_e_content_quality = _resolve_task_e_content_quality(task_e_manifest)
    preview_audio_path = _resolve_preview_audio_path(normalized_request, task_e_manifest)
    final_dub_audio_path = (
        _resolve_dub_audio_path(normalized_request, task_e_manifest)
        if normalized_request.export_dub
        else None
    )
    target_lang = _resolve_target_lang(normalized_request, task_e_manifest)
    _cleanup_unrequested_outputs(normalized_request, target_lang)
    subtitle_path = _resolve_subtitle_path(normalized_request, target_lang)
    chinese_subtitle_path = _resolve_chinese_subtitle_path(normalized_request)
    # Pin the resolved target_lang; replace() carries every other field so newly
    # added request fields (subtitle_delivery, embed_original_audio, …) are never
    # silently dropped here (cf. ARCH-14).
    normalized_request = replace(normalized_request, target_lang=target_lang)

    manifest_path = normalized_request.output_dir / "delivery-manifest.json"
    report_path = normalized_request.output_dir / "delivery-report.json"
    started_at = now_iso()
    started_monotonic = time.monotonic()

    try:
        input_video_info = probe_media(normalized_request.input_video_path)
        outputs: list[dict[str, Any]] = []
        preview_video_path: Path | None = None
        dub_video_path: Path | None = None

        try:
            width, height = probe_video_resolution(normalized_request.input_video_path)
        except Exception:
            width, height = 1920, 1080
        style = _resolve_subtitle_style(normalized_request.subtitle_style, width, height)

        if normalized_request.export_preview:
            preview_video_path = _build_output_video_path(
                normalized_request.output_dir / "final-preview",
                stem=f"final_preview.{target_lang}",
                container=normalized_request.container,
            )
            _export_video_variant(
                request=normalized_request,
                audio_path=preview_audio_path,
                output_path=preview_video_path,
                target_lang=target_lang,
                subtitle_path=subtitle_path,
                chinese_subtitle_path=chinese_subtitle_path,
                style=style,
                video_width=width,
                video_height=height,
            )
            outputs.append(_output_payload(kind="preview", output_path=preview_video_path))

        if normalized_request.export_dub:
            if final_dub_audio_path is None:
                raise TranslipError("Task G dub voice does not exist")
            dub_video_path = _build_output_video_path(
                normalized_request.output_dir / "final-dub",
                stem=f"final_dub.{target_lang}",
                container=normalized_request.container,
            )
            _export_video_variant(
                request=normalized_request,
                audio_path=final_dub_audio_path,
                output_path=dub_video_path,
                target_lang=target_lang,
                subtitle_path=subtitle_path,
                chinese_subtitle_path=chinese_subtitle_path,
                style=style,
                video_width=width,
                video_height=height,
            )
            outputs.append(_output_payload(kind="dub", output_path=dub_video_path))

        manifest = build_delivery_manifest(
            request=normalized_request,
            input_video_info=input_video_info,
            task_e_manifest_path=task_e_manifest_path,
            preview_audio_path=preview_audio_path,
            dub_audio_path=final_dub_audio_path,
            preview_video_path=preview_video_path,
            dub_video_path=dub_video_path,
            started_at=started_at,
            finished_at=now_iso(),
            elapsed_sec=time.monotonic() - started_monotonic,
            task_e_content_quality=task_e_content_quality,
        )
        report = build_delivery_report(
            request=normalized_request,
            input_video_info=input_video_info,
            target_lang=target_lang,
            outputs=outputs,
            preview_audio_path=preview_audio_path,
            dub_audio_path=final_dub_audio_path,
            task_e_manifest_path=task_e_manifest_path,
            status="succeeded",
            task_e_content_quality=task_e_content_quality,
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
            dub_audio_path=final_dub_audio_path,
            preview_video_path=None,
            dub_video_path=None,
            started_at=started_at,
            finished_at=now_iso(),
            elapsed_sec=time.monotonic() - started_monotonic,
            task_e_content_quality=task_e_content_quality,
            error=str(exc),
        )
        report = build_delivery_report(
            request=normalized_request,
            input_video_info=input_video_info,
            target_lang=target_lang,
            outputs=[],
            preview_audio_path=preview_audio_path,
            dub_audio_path=final_dub_audio_path,
            task_e_manifest_path=task_e_manifest_path,
            status="failed",
            task_e_content_quality=task_e_content_quality,
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
        task_e_dir = pipeline_root / "render" / "voice"
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
            output_dir = pipeline_root / "delivery" / "delivery"
        else:
            output_dir = Path("output-delivery").resolve()

    # Only the inferred paths are overridden; replace() preserves all other
    # request fields so new ones aren't silently dropped here (cf. ARCH-14).
    return replace(
        normalized,
        input_video_path=input_video_path,
        task_e_dir=task_e_dir,
        output_dir=output_dir,
    )


def _resolve_target_lang(request: ExportVideoRequest, task_e_manifest: dict[str, Any]) -> str:
    if request.target_lang:
        return request.target_lang
    return str(
        task_e_manifest.get("resolved", {}).get("target_lang")
        or task_e_manifest.get("request", {}).get("target_lang")
        or "en"
    )


def _resolve_task_e_content_quality(task_e_manifest: dict[str, Any]) -> dict[str, Any] | None:
    artifacts = task_e_manifest.get("artifacts", {})
    mix_report_path = artifacts.get("mix_report_json") if isinstance(artifacts, dict) else None
    if mix_report_path:
        path = Path(str(mix_report_path)).expanduser().resolve()
        if path.exists():
            try:
                mix_report = _load_json(path)
                content_quality = mix_report.get("stats", {}).get("content_quality")
                if isinstance(content_quality, dict):
                    return content_quality
            except Exception:
                pass
    resolved = task_e_manifest.get("resolved", {})
    if isinstance(resolved, dict) and resolved.get("content_status"):
        return {
            "status": str(resolved.get("content_status")),
            "reasons": [str(item) for item in resolved.get("content_quality_reasons", [])],
        }
    return None


def _resolve_subtitle_style(style: SubtitleStyle | None, width: int, height: int) -> SubtitleStyle:
    if style is None:
        return recommend_style(width, height)
    auto = recommend_style(width, height, position=style.position)
    return SubtitleStyle(
        font_family=style.font_family,
        font_size=style.font_size or auto.font_size,
        primary_color=style.primary_color,
        outline_color=style.outline_color,
        outline_width=style.outline_width,
        shadow_depth=style.shadow_depth,
        bold=style.bold,
        position=style.position,
        margin_v=style.margin_v or auto.margin_v,
        margin_h=style.margin_h,
        alignment=style.alignment,
    )


def _resolve_subtitle_path(request: ExportVideoRequest, target_lang: str) -> Path | None:
    if request.subtitle_mode in {"none", "chinese_only"}:
        return None
    if request.pipeline_root is None:
        raise TranslipError("subtitle export requires pipeline_root")
    if request.subtitle_source == "ocr":
        path = request.pipeline_root / "ocr-translate" / f"ocr_subtitles.{target_lang}.srt"
        if path.exists():
            return path
    else:
        candidates = sorted(request.pipeline_root.glob(f"translation/**/translation.{target_lang}.srt"))
        if candidates:
            return candidates[0]
        direct_path = request.pipeline_root / "translation" / f"translation.{target_lang}.srt"
        if direct_path.exists():
            return direct_path
        path = direct_path
    raise TranslipError(f"Subtitle file does not exist: {path}")


def _resolve_chinese_subtitle_path(request: ExportVideoRequest) -> Path | None:
    if request.subtitle_mode != "bilingual":
        return None
    if request.bilingual_export_strategy == "preserve_hard_subtitles_add_english":
        return None
    if request.pipeline_root is None:
        raise TranslipError("bilingual export requires pipeline_root")
    candidates = [
        request.pipeline_root / "ocr-detect" / "ocr_subtitles.source.srt",
        *sorted(request.pipeline_root.glob("transcription/**/segments.zh.srt")),
        request.pipeline_root / "transcription" / "segments.zh.srt",
    ]
    for path in candidates:
        if path.exists():
            return path
    raise TranslipError("Bilingual mode requires Chinese subtitle source SRT")


def _export_video_variant(
    *,
    request: ExportVideoRequest,
    audio_path: Path,
    output_path: Path,
    target_lang: str,
    subtitle_path: Path | None,
    chinese_subtitle_path: Path | None,
    style: SubtitleStyle,
    video_width: int,
    video_height: int,
) -> None:
    # Container-native delivery (DEL-1): copy the video (no re-encode), keep the
    # dub as the default track, optionally embed the original audio as a second
    # track, and attach the translated subtitle as a *soft* (selectable) stream
    # with language tags. Bilingual layout / hard-sub erase remain burn-only, so
    # soft delivery embeds the translated track and leaves the source video as-is.
    if request.subtitle_delivery == "soft":
        soft_subtitle = (
            Path(subtitle_path)
            if subtitle_path and request.subtitle_mode in {"english_only", "bilingual"}
            else None
        )
        mux_with_soft_subtitle(
            input_video_path=Path(request.input_video_path),
            dub_audio_path=audio_path,
            subtitle_path=soft_subtitle,
            output_path=output_path,
            container=request.container,
            video_codec=request.video_codec,
            audio_codec=request.audio_codec,
            audio_bitrate=request.audio_bitrate,
            audio_language=target_lang,
            subtitle_language=target_lang,
            embed_original_audio=request.embed_original_audio,
            end_policy=request.end_policy,
            loudnorm=True,
        )
        return

    if request.subtitle_mode in {"none", "chinese_only"}:
        mux_video_with_audio(
            input_video_path=Path(request.input_video_path),
            input_audio_path=audio_path,
            output_path=output_path,
            video_codec=request.video_codec,
            audio_codec=request.audio_codec,
            audio_bitrate=request.audio_bitrate,
            audio_language=target_lang,
            end_policy=request.end_policy,
            loudnorm=True,
        )
        return

    work_dir = ensure_directory(request.output_dir / ".delivery-subtitles")
    ass_path = work_dir / f"{output_path.stem}.ass"

    if request.subtitle_mode == "english_only":
        english_style = SubtitleStyle(
            font_family=style.font_family,
            font_size=style.font_size,
            primary_color=style.primary_color,
            outline_color=style.outline_color,
            outline_width=style.outline_width,
            shadow_depth=style.shadow_depth,
            bold=style.bold,
            position=request.bilingual_english_position,
            margin_v=style.margin_v,
            margin_h=style.margin_h,
            alignment=8 if request.bilingual_english_position == "top" else 2,
        )
        srt_to_ass(Path(subtitle_path), english_style, ass_path, play_res=(video_width, video_height))
    elif request.subtitle_mode == "bilingual":
        english_style = SubtitleStyle(
            font_family=style.font_family,
            font_size=style.font_size,
            primary_color=style.primary_color,
            outline_color=style.outline_color,
            outline_width=style.outline_width,
            shadow_depth=style.shadow_depth,
            bold=style.bold,
            position=request.bilingual_english_position,
            margin_v=style.margin_v,
            margin_h=style.margin_h,
            alignment=8 if request.bilingual_english_position == "top" else 2,
        )
        if request.bilingual_export_strategy == "preserve_hard_subtitles_add_english":
            srt_to_ass(Path(subtitle_path), english_style, ass_path, play_res=(video_width, video_height))
        else:
            chinese_style = SubtitleStyle(
                font_family=DEFAULT_SUBTITLE_FONT_CJK,
                font_size=max(style.font_size, 1),
                primary_color="#FFFFFF",
                outline_color="#000000",
                outline_width=style.outline_width,
                shadow_depth=style.shadow_depth,
                bold=False,
                position=request.bilingual_chinese_position,
                margin_v=style.margin_v,
                margin_h=style.margin_h,
                alignment=8 if request.bilingual_chinese_position == "top" else 2,
            )
            merge_bilingual_ass(
                Path(chinese_subtitle_path),
                Path(subtitle_path),
                chinese_style,
                english_style,
                ass_path,
                play_res=(video_width, video_height),
            )
    else:
        raise TranslipError(f"Unsupported subtitle mode: {request.subtitle_mode}")

    source_video_path = Path(request.input_video_path)
    needs_clean_video = request.subtitle_mode == "english_only" or (
        request.subtitle_mode == "bilingual"
        and request.bilingual_export_strategy == "clean_video_rebuild_bilingual"
    )
    if needs_clean_video and request.pipeline_root is not None:
        clean_candidate = request.pipeline_root / "subtitle-erase" / "clean_video.mp4"
        if clean_candidate.exists():
            source_video_path = clean_candidate
        else:
            if request.subtitle_mode == "english_only":
                raise TranslipError("english_only mode requires subtitle-erase clean_video.mp4")
            raise TranslipError("clean_video_rebuild_bilingual requires subtitle-erase clean_video.mp4")

    burn_subtitle_and_mux(
        input_video_path=source_video_path,
        input_audio_path=audio_path,
        subtitle_path=ass_path,
        output_path=output_path,
        video_codec="libx264" if request.video_codec == "copy" else request.video_codec,
        audio_codec=request.audio_codec,
        audio_bitrate=request.audio_bitrate,
        audio_language=target_lang,
        end_policy=request.end_policy,
        crf=request.crf,
        preset=request.preset,
        loudnorm=True,
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
    resolved = _resolve_optional_dub_audio_path(request, task_e_manifest)
    if resolved is None:
        target_lang = _resolve_target_lang(request, task_e_manifest)
        fallback = (request.task_e_dir / f"dub_voice.{target_lang}.wav").resolve()
        raise TranslipError(f"Task G dub voice does not exist: {fallback}")
    return resolved


def _resolve_optional_dub_audio_path(request: ExportVideoRequest, task_e_manifest: dict[str, Any]) -> Path | None:
    path = task_e_manifest.get("artifacts", {}).get("dub_voice")
    if path:
        resolved = Path(str(path)).expanduser().resolve()
    else:
        target_lang = _resolve_target_lang(request, task_e_manifest)
        resolved = (request.task_e_dir / f"dub_voice.{target_lang}.wav").resolve()
    if not resolved.exists():
        return None
    return resolved


def _cleanup_unrequested_outputs(request: ExportVideoRequest, target_lang: str) -> None:
    if request.output_dir is None:
        return
    if not request.export_preview:
        _remove_matching_outputs(request.output_dir / "final-preview", f"final_preview.{target_lang}.*")
    if not request.export_dub:
        _remove_matching_outputs(request.output_dir / "final-dub", f"final_dub.{target_lang}.*")


def _remove_matching_outputs(directory: Path, pattern: str) -> None:
    if not directory.exists():
        return
    for path in directory.glob(pattern):
        if path.is_file() or path.is_symlink():
            path.unlink()
    try:
        directory.rmdir()
    except OSError:
        pass


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
    return read_json(path)


__all__ = ["export_video"]
