from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..dubbing.planning import pick_segment_ids_for_speaker, pick_task_d_speaker_ids
from ..exceptions import TranslipError
from ..types import PipelineRequest, PipelineResult, PipelineStageName
from ..translation.backend import output_tag_for_language
from ..utils.files import ensure_directory
from .cache import StageCacheSpec, compute_cache_key, is_stage_cache_hit
from .erase_bridge import run_subtitle_erase
from .graph import resolve_template_plan
from .nodes import NODE_REGISTRY
from .ocr_bridge import (
    ocr_detect_manifest_path,
    ocr_detection_path,
    ocr_events_path,
    ocr_source_srt_path,
    run_ocr_detect,
)
from .commands import (
    build_asr_ocr_correction_command,
    build_stage1_command,
    build_task_a_command,
    build_task_b_command,
    build_task_c_command,
    build_task_d_command,
    build_task_e_command,
    effective_task_a_segments_path,
    stage1_background_path,
    stage1_manifest_path,
    stage1_voice_path,
    task_a_corrected_segments_path,
    task_a_corrected_srt_path,
    task_a_correction_manifest_path,
    task_a_correction_report_path,
    task_a_manifest_path,
    task_a_segments_path,
    task_b_manifest_path,
    task_b_matches_path,
    task_b_profiles_path,
    task_b_registry_path,
    task_c_manifest_path,
    task_c_translation_path,
    task_d_report_path,
    task_d_stage_manifest_path,
    task_e_dub_voice_path,
    task_e_manifest_path,
    task_e_mix_report_path,
    task_e_preview_mix_path,
    task_e_timeline_path,
)
from .export import build_pipeline_manifest, build_pipeline_report, build_request_payload, write_json
from .monitor import PipelineMonitor
from .stages import resolve_stage_sequence
from .subprocess_runner import StageSubprocessError, run_stage_command


def _now_job_id() -> str:
    return "pipeline-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _count_renderable_task_d_segments(payload: dict[str, Any]) -> int:
    return sum(1 for row in payload.get("segments", []) if isinstance(row, dict))


def _file_fingerprint(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {"path": str(path), "exists": False, "sha256": None}
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"path": str(path), "exists": True, "sha256": digest}


def _pipeline_paths(request: PipelineRequest) -> dict[str, Path]:
    return {
        "request_path": request.output_root / "request.json",
        "manifest_path": request.output_root / "pipeline-manifest.json",
        "report_path": request.output_root / "pipeline-report.json",
        "workflow_manifest_path": request.output_root / "workflow-manifest.json",
        "workflow_report_path": request.output_root / "workflow-report.json",
        "status_path": request.output_root / "pipeline-status.json",
        "logs_dir": request.output_root / "logs",
    }


def _previous_stage_cache_keys(output_root: Path) -> dict[str, str]:
    manifest_path = output_root / "workflow-manifest.json"
    if not manifest_path.exists():
        manifest_path = output_root / "pipeline-manifest.json"
    if not manifest_path.exists():
        return {}
    payload = _load_json(manifest_path)
    keys: dict[str, str] = {}
    for row in payload.get("nodes", payload.get("stages", [])):
        if not isinstance(row, dict):
            continue
        stage_name = str(row.get("node_name") or row.get("stage_name") or "")
        cache_key = str(row.get("cache_key") or "")
        if stage_name and cache_key:
            keys[stage_name] = cache_key
    return keys


def _stage_cache_payload(request: PipelineRequest, stage_name: str) -> dict[str, Any]:
    common = {
        "input_path": str(request.input_path),
        "template_id": request.template_id,
        "target_lang": request.target_lang,
        "translation_backend": request.translation_backend,
        "tts_backend": request.tts_backend,
        "device": request.device,
        "delivery_policy": dict(request.delivery_policy),
    }
    if stage_name == "stage1":
        common.update(
            {
                "mode": request.separation_mode,
                "quality": request.separation_quality,
                "audio_stream_index": request.audio_stream_index,
                "output_format": request.stage1_output_format,
            }
        )
    elif stage_name == "task-a":
        common.update({"language": request.transcription_language, "asr_model": request.asr_model})
    elif stage_name == "asr-ocr-correct":
        common.update({"transcription_correction": dict(request.transcription_correction)})
    elif stage_name == "task-b":
        common.update(
            {
                "segments": _file_fingerprint(effective_task_a_segments_path(request)),
                "registry_path": str(task_b_registry_path(request)),
                "top_k": request.top_k,
                "update_registry": request.update_registry,
            }
        )
    elif stage_name == "task-c":
        common.update(
            {
                "segments": _file_fingerprint(effective_task_a_segments_path(request)),
                "profiles": _file_fingerprint(task_b_profiles_path(request)),
                "glossary_path": str(request.glossary_path) if request.glossary_path else None,
                "api_model": request.api_model,
                "api_base_url": request.api_base_url,
                "condense_mode": request.condense_mode,
            }
        )
    elif stage_name == "task-d":
        common.update(
            {
                "speaker_limit": request.speaker_limit,
                "segments_per_speaker": request.segments_per_speaker,
            }
        )
    elif stage_name == "task-e":
        common.update(
            {
                "segments": _file_fingerprint(effective_task_a_segments_path(request)),
                "translation": _file_fingerprint(task_c_translation_path(request)),
                "fit_policy": request.fit_policy,
                "fit_backend": request.fit_backend,
                "mix_profile": request.mix_profile,
                "ducking_mode": request.ducking_mode,
                "preview_format": request.preview_format,
                "max_compress_ratio": request.max_compress_ratio,
            }
        )
    return common


def _node_cache_spec(
    request: PipelineRequest,
    stage_name: str,
    previous_cache_keys: dict[str, str],
) -> StageCacheSpec:
    if stage_name == "stage1":
        manifest_path = stage1_manifest_path(request)
        artifact_paths = [stage1_voice_path(request), stage1_background_path(request)]
    elif stage_name == "task-a":
        manifest_path = task_a_manifest_path(request)
        artifact_paths = [task_a_segments_path(request)]
    elif stage_name == "asr-ocr-correct":
        manifest_path = task_a_correction_manifest_path(request)
        artifact_paths = [
            task_a_corrected_segments_path(request),
            task_a_corrected_srt_path(request),
            task_a_correction_report_path(request),
            manifest_path,
        ]
    elif stage_name == "task-b":
        manifest_path = task_b_manifest_path(request)
        artifact_paths = [task_b_profiles_path(request), task_b_matches_path(request), task_b_registry_path(request)]
    elif stage_name == "task-c":
        manifest_path = task_c_manifest_path(request)
        artifact_paths = [task_c_translation_path(request)]
    elif stage_name == "task-d":
        manifest_path = task_d_stage_manifest_path(request)
        artifact_paths = [manifest_path]
    elif stage_name == "task-e":
        manifest_path = task_e_manifest_path(request)
        artifact_paths = [task_e_dub_voice_path(request), task_e_preview_mix_path(request), task_e_mix_report_path(request)]
    elif stage_name == "task-g":
        manifest_path = request.output_root / "task-g" / "delivery-manifest.json"
        artifact_paths = [manifest_path, request.output_root / "task-g" / "delivery-report.json"]
    elif stage_name == "ocr-detect":
        manifest_path = ocr_detect_manifest_path(request)
        artifact_paths = [ocr_events_path(request), ocr_detection_path(request), ocr_source_srt_path(request)]
    elif stage_name == "ocr-translate":
        output_tag = output_tag_for_language(request.target_lang)
        manifest_path = request.output_root / "ocr-translate" / "ocr-translate-manifest.json"
        artifact_paths = [
            request.output_root / "ocr-translate" / f"ocr_subtitles.{output_tag}.json",
            request.output_root / "ocr-translate" / f"ocr_subtitles.{output_tag}.srt",
            manifest_path,
        ]
    elif stage_name == "subtitle-erase":
        manifest_path = request.output_root / "subtitle-erase" / "subtitle-erase-manifest.json"
        artifact_paths = [request.output_root / "subtitle-erase" / "clean_video.mp4", manifest_path]
    else:
        manifest_path = request.output_root / stage_name / f"{stage_name}-manifest.json"
        artifact_paths = [manifest_path]

    return StageCacheSpec(
        stage_name=stage_name,
        manifest_path=manifest_path,
        artifact_paths=artifact_paths,
        cache_key=compute_cache_key(_stage_cache_payload(request, stage_name)),
        previous_cache_key=previous_cache_keys.get(stage_name),
    )


def _final_artifacts(request: PipelineRequest) -> dict[str, str]:
    return {
        "voice_path": str(stage1_voice_path(request)),
        "background_path": str(stage1_background_path(request)),
        "segments_path": str(effective_task_a_segments_path(request)),
        "profiles_path": str(task_b_profiles_path(request)),
        "translation_path": str(task_c_translation_path(request)),
        "dub_voice_path": str(task_e_dub_voice_path(request)),
        "preview_mix_path": str(task_e_preview_mix_path(request)),
        "timeline_path": str(task_e_timeline_path(request)),
        "mix_report_path": str(task_e_mix_report_path(request)),
    }


def _stage_log_path(request: PipelineRequest, stage_name: PipelineStageName) -> Path:
    return request.output_root / "logs" / f"{stage_name}.log"


def _node_log_path(request: PipelineRequest, node_name: str) -> Path:
    return request.output_root / "logs" / f"{node_name}.log"


def _resolve_execution_nodes(request: PipelineRequest) -> tuple[Any, list[str]]:
    plan = resolve_template_plan(request.template_id)
    start_hint = NODE_REGISTRY[request.run_from_stage].sequence_hint
    end_hint = NODE_REGISTRY[request.run_to_stage].sequence_hint
    node_names = [
        node_name
        for node_name in plan.node_order
        if start_hint <= NODE_REGISTRY[node_name].sequence_hint <= end_hint
    ]
    return plan, node_names


def _node_weights(node_names: list[str]) -> dict[str, float]:
    if not node_names:
        return {}
    weight = 1.0 / len(node_names)
    return {node_name: weight for node_name in node_names}


def execute_stage(
    stage_name: str,
    request: PipelineRequest,
    *,
    monitor: PipelineMonitor,
) -> dict[str, Any]:
    stage = stage_name  # string for monkeypatch compatibility
    if stage == "stage1":
        monitor.update_stage_progress(stage, 5.0, "separating source audio")
        run_stage_command(build_stage1_command(request), log_path=_stage_log_path(request, "stage1"))
        return {
            "manifest_path": str(stage1_manifest_path(request)),
            "artifact_paths": [str(stage1_voice_path(request)), str(stage1_background_path(request))],
            "log_path": str(_stage_log_path(request, "stage1")),
        }

    if stage == "task-a":
        monitor.update_stage_progress(stage, 5.0, "transcribing voice track")
        run_stage_command(build_task_a_command(request), log_path=_stage_log_path(request, "task-a"))
        return {
            "manifest_path": str(task_a_manifest_path(request)),
            "artifact_paths": [str(task_a_segments_path(request))],
            "log_path": str(_stage_log_path(request, "task-a")),
        }

    if stage == "task-b":
        monitor.update_stage_progress(stage, 5.0, "building speaker profiles")
        run_stage_command(build_task_b_command(request), log_path=_stage_log_path(request, "task-b"))
        return {
            "manifest_path": str(task_b_manifest_path(request)),
            "artifact_paths": [
                str(task_b_profiles_path(request)),
                str(task_b_matches_path(request)),
                str(task_b_registry_path(request)),
            ],
            "log_path": str(_stage_log_path(request, "task-b")),
        }

    if stage == "task-c":
        monitor.update_stage_progress(stage, 5.0, "translating script")
        run_stage_command(build_task_c_command(request), log_path=_stage_log_path(request, "task-c"))
        return {
            "manifest_path": str(task_c_manifest_path(request)),
            "artifact_paths": [str(task_c_translation_path(request))],
            "log_path": str(_stage_log_path(request, "task-c")),
        }

    if stage == "task-d":
        profiles_payload = _load_json(task_b_profiles_path(request))
        translation_payload = _load_json(task_c_translation_path(request))
        profile_count = len(profiles_payload.get("profiles", []))
        candidate_limit = (
            profile_count
            if request.speaker_limit <= 0
            else min(profile_count, max(request.speaker_limit * 3, request.speaker_limit))
        )
        ranked_speaker_ids = pick_task_d_speaker_ids(
            profiles_payload=profiles_payload,
            translation_payload=translation_payload,
            limit=candidate_limit,
        )
        if not ranked_speaker_ids:
            raise TranslipError("No suitable speakers found for Task D pipeline stage")

        reports: list[str] = []
        selected_segment_map: dict[str, list[str] | None] = {}
        total = max(len(ranked_speaker_ids), 1)
        for index, speaker_id in enumerate(ranked_speaker_ids, start=1):
            progress = ((index - 1) / total) * 100.0
            monitor.update_stage_progress(stage, progress, f"speaker {speaker_id} {index - 1}/{total}")
            segment_limit = None if request.segments_per_speaker <= 0 else request.segments_per_speaker
            selected_segment_ids = pick_segment_ids_for_speaker(
                translation_payload=translation_payload,
                speaker_id=speaker_id,
                limit=segment_limit,
            )
            selected_segment_map[speaker_id] = selected_segment_ids
            run_stage_command(
                build_task_d_command(request, speaker_id=speaker_id, segment_ids=selected_segment_ids),
                log_path=_stage_log_path(request, "task-d"),
            )
            report_path = task_d_report_path(request, speaker_id)
            if report_path.exists():
                report_payload = _load_json(report_path)
                if _count_renderable_task_d_segments(report_payload) > 0:
                    reports.append(str(report_path))
            if request.speaker_limit > 0 and len(reports) >= request.speaker_limit:
                break

        if not reports:
            raise TranslipError("Task D did not produce any reports for Task E")

        stage_manifest = {
            "status": "succeeded",
            "target_lang": request.target_lang,
            "reports": reports,
            "selected_segment_map": selected_segment_map,
        }
        write_json(stage_manifest, task_d_stage_manifest_path(request))
        return {
            "manifest_path": str(task_d_stage_manifest_path(request)),
            "artifact_paths": reports + [str(task_d_stage_manifest_path(request))],
            "log_path": str(_stage_log_path(request, "task-d")),
        }

    if stage == "task-e":
        task_d_manifest = _load_json(task_d_stage_manifest_path(request))
        task_d_reports = [Path(path) for path in task_d_manifest.get("reports", [])]
        monitor.update_stage_progress(stage, 5.0, "rendering dub timeline")
        run_stage_command(
            build_task_e_command(request, task_d_reports=task_d_reports),
            log_path=_stage_log_path(request, "task-e"),
        )
        return {
            "manifest_path": str(task_e_manifest_path(request)),
            "artifact_paths": [
                str(task_e_dub_voice_path(request)),
                str(task_e_preview_mix_path(request)),
                str(task_e_timeline_path(request)),
                str(task_e_mix_report_path(request)),
            ],
            "log_path": str(_stage_log_path(request, "task-e")),
        }

    raise ValueError(f"Unsupported stage: {stage}")


def execute_delivery_node(
    request: PipelineRequest,
    *,
    monitor: PipelineMonitor,
) -> dict[str, Any]:
    from ..delivery.runner import export_video
    from ..delivery.runner import resolve_delivery_inputs
    from ..types import ExportVideoRequest

    delivery_inputs = resolve_delivery_inputs(request)
    audio_source = request.delivery_policy.get("audio_source", "both")
    export_preview = audio_source in {"preview_mix", "both"}
    export_dub = audio_source in {"dub_voice", "both"}
    monitor.update_stage_progress("task-g", 5.0, "assembling delivery")
    result = export_video(
        ExportVideoRequest(
            input_video_path=delivery_inputs.video_path,
            pipeline_root=request.output_root,
            output_dir=request.output_root / "task-g",
            target_lang=request.target_lang,
            export_preview=export_preview,
            export_dub=export_dub,
            subtitle_mode=request.subtitle_mode,
            subtitle_source=request.subtitle_source,
            subtitle_style=request.subtitle_style,
            bilingual_chinese_position=request.bilingual_chinese_position,
            bilingual_english_position=request.bilingual_english_position,
        )
    )
    artifact_paths = [
        str(path)
        for path in (
            result.artifacts.preview_video_path,
            result.artifacts.dub_video_path,
            result.artifacts.manifest_path,
            result.artifacts.report_path,
        )
        if path is not None
    ]
    return {
        "manifest_path": str(result.artifacts.manifest_path),
        "artifact_paths": artifact_paths,
        "log_path": str(_node_log_path(request, "task-g")),
    }


def execute_node(
    node_name: str,
    request: PipelineRequest,
    *,
    monitor: PipelineMonitor,
) -> dict[str, Any]:
    if node_name in {"stage1", "task-a", "task-b", "task-c", "task-d", "task-e"}:
        return execute_stage(node_name, request, monitor=monitor)
    if node_name == "ocr-detect":
        monitor.update_stage_progress(node_name, 5.0, "extracting hard subtitles")
        return run_ocr_detect(request, log_path=_node_log_path(request, node_name))
    if node_name == "asr-ocr-correct":
        monitor.update_stage_progress(node_name, 5.0, "correcting ASR transcript with OCR")
        run_stage_command(build_asr_ocr_correction_command(request), log_path=_node_log_path(request, node_name))
        return {
            "manifest_path": str(task_a_correction_manifest_path(request)),
            "artifact_paths": [
                str(task_a_corrected_segments_path(request)),
                str(task_a_corrected_srt_path(request)),
                str(task_a_correction_report_path(request)),
                str(task_a_correction_manifest_path(request)),
            ],
            "log_path": str(_node_log_path(request, node_name)),
        }
    if node_name == "ocr-translate":
        from ..subtitles.runner import translate_ocr_events

        monitor.update_stage_progress(node_name, 5.0, "translating OCR subtitles")

        def _on_ocr_translation_progress(completed: int, total: int) -> None:
            if total <= 0:
                return
            percent = 5.0 + (90.0 * completed / total)
            monitor.update_stage_progress(
                node_name,
                percent,
                f"translating OCR subtitles ({completed}/{total})",
            )

        result = translate_ocr_events(
            events_path=ocr_events_path(request),
            output_dir=request.output_root / "ocr-translate",
            target_lang=request.target_lang,
            backend_name=request.translation_backend,
            device=request.device,
            api_model=request.api_model,
            api_base_url=request.api_base_url,
            batch_size=request.translation_batch_size,
            progress_callback=_on_ocr_translation_progress,
        )
        return {
            "manifest_path": str(result.manifest_path),
            "artifact_paths": [str(result.json_path), str(result.srt_path), str(result.manifest_path)],
            "log_path": str(_node_log_path(request, node_name)),
        }
    if node_name == "subtitle-erase":
        monitor.update_stage_progress(node_name, 5.0, "erasing hard subtitles")
        return run_subtitle_erase(request, log_path=_node_log_path(request, node_name))
    if node_name == "task-g":
        return execute_delivery_node(request, monitor=monitor)
    raise TranslipError(f"Unsupported workflow node: {node_name}")


def run_pipeline(
    request: PipelineRequest,
    *,
    stage_executor=None,
) -> PipelineResult:
    request = request.normalized()
    if not request.input_path.exists():
        raise TranslipError(f"Pipeline input path does not exist: {request.input_path}")

    ensure_directory(request.output_root)
    paths = _pipeline_paths(request)
    request_payload = build_request_payload(request)
    write_json(request_payload, paths["request_path"])

    job_id = _now_job_id()
    plan, node_names = _resolve_execution_nodes(request)
    monitor = PipelineMonitor(
        job_id=job_id,
        status_path=paths["status_path"],
        write_status=request.write_status,
        item_order=node_names,
        item_weights=_node_weights(node_names),
    )
    previous_cache_keys = _previous_stage_cache_keys(request.output_root) if request.reuse_existing else {}
    force_stages = {stage for stage in (request.force_stages or [])}
    stage_rows: list[dict[str, Any]] = []
    optional_failures: list[str] = []

    try:
        for node_name in node_names:
            node_meta = plan.nodes[node_name]
            cache_spec = _node_cache_spec(request, node_name, previous_cache_keys)
            stage_row: dict[str, Any] = {
                "node_name": node_name,
                "stage_name": node_name,
                "required": node_meta.required,
                "status": "pending",
                "cache_key": cache_spec.cache_key,
                "cache_hit": False,
                "manifest_path": str(cache_spec.manifest_path),
                "artifact_paths": [str(path) for path in cache_spec.artifact_paths],
                "log_path": str(_node_log_path(request, node_name)),
                "error": None,
            }
            stage_rows.append(stage_row)
            if request.reuse_existing and node_name not in force_stages and is_stage_cache_hit(cache_spec):
                monitor.start_stage(node_name, current_step="cached")
                monitor.complete_stage(node_name, status="cached", current_step="cached")
                stage_row["status"] = "cached"
                stage_row["cache_hit"] = True
                print(f"[node:{node_name}] status=cached")
                continue

            monitor.start_stage(node_name, current_step="starting")
            print(f"[workflow] status=running node={node_name}")
            try:
                if stage_executor is not None and node_name in {"stage1", "task-a", "task-b", "task-c", "task-d", "task-e"}:
                    result = stage_executor(node_name, request, monitor=monitor)
                else:
                    result = execute_node(node_name, request, monitor=monitor)
            except Exception as exc:
                stage_row["status"] = "failed"
                stage_row["error"] = str(exc)
                stage_row["error_message"] = str(exc)
                if node_meta.required:
                    monitor.fail_stage(node_name, error=str(exc))
                    raise
                optional_failures.append(node_name)
                monitor.fail_stage(node_name, error=str(exc), pipeline_status="running")
                print(f"[node:{node_name}] status=failed required=false error={exc}")
                continue

            monitor.complete_stage(node_name, status="succeeded", current_step="completed")
            stage_row["status"] = "succeeded"
            stage_row["manifest_path"] = result.get("manifest_path", stage_row["manifest_path"])
            stage_row["artifact_paths"] = result.get("artifact_paths", stage_row["artifact_paths"])
            stage_row["log_path"] = result.get("log_path", stage_row["log_path"])
            print(f"[node:{node_name}] status=succeeded progress={monitor.payload()['overall_progress_percent']}%")

        final_artifacts = _final_artifacts(request)
        workflow_status = "partial_success" if optional_failures else "succeeded"
        manifest = build_pipeline_manifest(
            request=request,
            job_id=job_id,
            stages=stage_rows,
            final_artifacts=final_artifacts,
            status=workflow_status,
        )
        report = build_pipeline_report(
            request=request,
            job_id=job_id,
            stages=stage_rows,
            final_artifacts=final_artifacts,
            status=workflow_status,
        )
        write_json(manifest, paths["manifest_path"])
        write_json(report, paths["report_path"])
        write_json(manifest, paths["workflow_manifest_path"])
        write_json(report, paths["workflow_report_path"])
        monitor.finalize(status=workflow_status)
        return PipelineResult(
            request=request,
            output_root=request.output_root,
            manifest_path=paths["manifest_path"],
            report_path=paths["report_path"],
            status_path=paths["status_path"],
            request_path=paths["request_path"],
            manifest=manifest,
            report=report,
        )
    except Exception as exc:
        if stage_rows and stage_rows[-1]["status"] == "pending":
            stage_rows[-1]["status"] = "failed"
            stage_rows[-1]["error"] = str(exc)
            stage_rows[-1]["error_message"] = str(exc)
            monitor.fail_stage(stage_rows[-1]["stage_name"], error=str(exc))
        elif not stage_rows or stage_rows[-1]["status"] != "failed":
            stage_rows.append(
                {
                    "node_name": node_names[len(stage_rows)] if len(stage_rows) < len(node_names) else "unknown",
                    "stage_name": node_names[len(stage_rows)] if len(stage_rows) < len(node_names) else "unknown",
                    "status": "failed",
                    "cache_key": "",
                    "cache_hit": False,
                    "manifest_path": "",
                    "artifact_paths": [],
                    "log_path": "",
                    "error": str(exc),
                    "error_message": str(exc),
                }
            )
            monitor.fail_stage(stage_rows[-1]["stage_name"], error=str(exc))
        final_artifacts = _final_artifacts(request)
        manifest = build_pipeline_manifest(
            request=request,
            job_id=job_id,
            stages=stage_rows,
            final_artifacts=final_artifacts,
            status="failed",
            error=str(exc),
        )
        report = build_pipeline_report(
            request=request,
            job_id=job_id,
            stages=stage_rows,
            final_artifacts=final_artifacts,
            status="failed",
        )
        write_json(manifest, paths["manifest_path"])
        write_json(report, paths["report_path"])
        write_json(manifest, paths["workflow_manifest_path"])
        write_json(report, paths["workflow_report_path"])
        monitor.finalize(status="failed")
        if isinstance(exc, StageSubprocessError):
            raise TranslipError(
                f"{exc}\nlog={exc.log_path}\nlast_output={' | '.join(exc.tail)}"
            ) from exc
        raise


__all__ = ["execute_delivery_node", "execute_node", "execute_stage", "run_pipeline"]
