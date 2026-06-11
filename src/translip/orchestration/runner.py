from __future__ import annotations
import logging

import hashlib
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..characters.ledger import CharacterLedgerRequest, CharacterLedgerResult, build_character_ledger
from ..dubbing.planning import pick_segment_ids_for_speaker, pick_task_d_speaker_ids
from ..dubbing.voice_bank import VoiceBankRequest, build_voice_bank
from ..exceptions import TranslipError
from ..quality import DubBenchmarkRequest, DubBenchmarkResult, build_dub_benchmark
from ..repair import RepairPlanRequest, RepairRunRequest, plan_dub_repair, run_dub_repair
from ..types import PipelineRequest, PipelineResult, PipelineStageName
from ..translation.backend import output_tag_for_language
from ..utils.files import ensure_directory
from ..utils.io import read_json
from .cache import StageCacheSpec, compute_cache_key, is_stage_cache_hit
from .erase_bridge import run_subtitle_erase
from .graph import resolve_template_plan
from .nodes import NODE_REGISTRY
from .ocr_bridge import (
    effective_ocr_events_path,
    ocr_classified_events_path,
    ocr_detect_manifest_path,
    ocr_detection_path,
    ocr_events_path,
    ocr_source_srt_path,
    run_ocr_detect,
)
from .vision_bridge import (
    run_visual_context,
    visual_context_manifest_path,
    visual_context_path,
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
    glossary_hotwords,
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
    task_b_voice_bank_path,
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
from .subprocess_runner import (
    StageSubprocessCancelled,
    StageSubprocessError,
    run_stage_command,
)

logger = logging.getLogger(__name__)


def _now_job_id() -> str:
    return "pipeline-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _load_json(path: Path) -> dict[str, Any]:
    return read_json(path)


def _count_renderable_task_d_segments(payload: dict[str, Any]) -> int:
    return sum(1 for row in payload.get("segments", []) if isinstance(row, dict))


def _task_d_speaker_already_rendered(report_path: Path, *, resume_ok: bool) -> bool:
    """ARCH-6: whether this speaker can be skipped on a resume.

    True only when resume is allowed (same cache key — a crash, not a param
    change) and a prior run already wrote a renderable report for the speaker.
    """
    if not resume_ok or not report_path.exists():
        return False
    try:
        return _count_renderable_task_d_segments(_load_json(report_path)) > 0
    except Exception:
        return False


def _file_fingerprint(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {"path": str(path), "exists": False, "sha256": None}
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"path": str(path), "exists": True, "sha256": digest}


def _resolved_vision_backend(request: PipelineRequest) -> dict[str, str]:
    """Resolve vision "auto" to the concrete backend/model for the cache key.

    Cheap by contract (find_spec + HTTP probe, no model load). Resolution
    failure is itself a stable key value — the node will fail with the real
    dependency error when it runs, and installing a backend later changes the
    key, forcing the recompute we want.
    """
    import dataclasses

    from ..vision.backends import VisionDependencyError, resolve_backend_name
    from ..vision.config import load_settings

    settings = load_settings()
    if request.vision_backend and request.vision_backend != settings.backend:
        settings = dataclasses.replace(settings, backend=str(request.vision_backend))
    try:
        backend_name, model_id = resolve_backend_name(settings)
    except VisionDependencyError:
        return {"backend": "unavailable", "model": ""}
    return {"backend": backend_name, "model": model_id}


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
        common.update(
            {
                "voice": _file_fingerprint(stage1_voice_path(request)),
                "language": request.transcription_language,
                "asr_model": request.asr_model,
                "asr_backend": request.asr_backend,
                "diarizer_backend": request.diarizer_backend,
                "enable_diarization": request.enable_diarization,
                "generate_srt": request.generate_srt,
                "vad_filter": request.vad_filter,
                "vad_min_silence_duration_ms": request.vad_min_silence_duration_ms,
                "vad_max_segment_sec": request.vad_max_segment_sec,
                "expected_speakers": request.expected_speakers,
                "beam_size": request.beam_size,
                "best_of": request.best_of,
                "temperature": request.temperature,
                "condition_on_previous_text": request.condition_on_previous_text,
                # task-a now feeds glossary terms as --hotwords, so the cache key
                # must track them or a glossary change would reuse stale ASR (ASR-7).
                "hotwords": glossary_hotwords(request),
            }
        )
    elif stage_name == "asr-ocr-correct":
        common.update(
            {
                "transcription_correction": dict(request.transcription_correction),
                # Correction aligns against OCR events; classification changes
                # which events participate (scene_text/watermark are dropped).
                "ocr_events": _file_fingerprint(effective_ocr_events_path(request)),
            }
        )
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
                # Batch size changes how segments are grouped in each LLM prompt,
                # which can change the translation — track it so it recomputes (ARCH-4).
                "translation_batch_size": request.translation_batch_size,
                # Visual scene context is injected into translation prompts when
                # present, so its content must cascade into task-c's key. Missing
                # file fingerprints to a stable {exists: False} (no-vision runs).
                "visual_context": _file_fingerprint(visual_context_path(request)),
            }
        )
    elif stage_name == "task-d":
        common.update(
            {
                "translation": _file_fingerprint(task_c_translation_path(request)),
                "profiles": _file_fingerprint(task_b_profiles_path(request)),
                "voice_bank": _file_fingerprint(task_b_voice_bank_path(request)),
                "speaker_limit": request.speaker_limit,
                "segments_per_speaker": request.segments_per_speaker,
                "dubbing_workers": request.dubbing_workers,
                "dubbing_quality_check": request.dubbing_quality_check,
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
                "background_gain_db": request.background_gain_db,
                "window_ducking_db": request.window_ducking_db,
                "preview_format": request.preview_format,
                "max_compress_ratio": request.max_compress_ratio,
                "overflow_max_compress_ratio": request.overflow_max_compress_ratio,
                "output_sample_rate": request.output_sample_rate,
                "dub_repair_enabled": request.dub_repair_enabled,
                "dub_repair_backends": request.dub_repair_backends,
                "dub_repair_max_items": request.dub_repair_max_items,
                "dub_repair_attempts_per_item": request.dub_repair_attempts_per_item,
                "dub_repair_include_risk": request.dub_repair_include_risk,
            }
        )
    elif stage_name == "ocr-detect":
        common.update(
            {
                "language": request.transcription_language,
                "ocr_sample_interval": request.ocr_sample_interval,
                "ocr_position_mode": request.ocr_position_mode,
                "ocr_extraction_mode": request.ocr_extraction_mode,
                # Classification runs as a post-step of this node, so toggling
                # it (or switching the vision backend) must recompute.
                "ocr_classify_text": bool(request.ocr_classify_text),
                "ocr_classify_backend": (
                    _resolved_vision_backend(request) if request.ocr_classify_text else None
                ),
            }
        )
    elif stage_name == "ocr-translate":
        common.update(
            {
                # Classification drops scene_text/watermark events from the
                # translation input set, so the effective events file is the input.
                "ocr_events": _file_fingerprint(effective_ocr_events_path(request)),
            }
        )
    elif stage_name == "visual-context":
        common.update(
            {
                # "auto" must not go into the key — its resolution drifts with the
                # environment (mlx installed or not, ollama up or not). Resolve via
                # the cheap probe so backend/model changes force a recompute.
                "vision_backend_resolved": _resolved_vision_backend(request),
                "vision_frames_per_unit": int(request.vision_frames_per_unit),
                "vision_lang": request.vision_lang,
                "segments": _file_fingerprint(effective_task_a_segments_path(request)),
            }
        )
    elif stage_name == "subtitle-erase":
        common.update(
            {
                "erase_backend": request.erase_backend,
                "erase_device": request.erase_device,
                "erase_mask_dilate_x": request.erase_mask_dilate_x,
                "erase_mask_dilate_y": request.erase_mask_dilate_y,
                "erase_event_lead_frames": request.erase_event_lead_frames,
                "erase_event_trail_frames": request.erase_event_trail_frames,
                "erase_neighbor_stride": request.erase_neighbor_stride,
                "erase_reference_length": request.erase_reference_length,
                "erase_max_load": request.erase_max_load,
                "erase_regions": request.erase_regions,
                "detection": _file_fingerprint(ocr_detection_path(request)),
                # Classified events filter scene_text/watermark boxes out of the
                # erase masks — toggling or re-classifying must recompute.
                "classified_events": _file_fingerprint(effective_ocr_events_path(request))
                if request.ocr_classify_text
                else None,
            }
        )
    return common


def _task_g_expected_artifact_paths(request: PipelineRequest) -> list[Path]:
    task_g_dir = request.output_root / "task-g"
    artifact_paths = [task_g_dir / "delivery-manifest.json", task_g_dir / "delivery-report.json"]
    audio_source = _delivery_audio_source(request)
    if audio_source in {"preview_mix", "both"}:
        artifact_paths.append(task_g_dir / "final-preview" / f"final_preview.{request.target_lang}.mp4")
    if audio_source in {"dub_voice", "both"}:
        artifact_paths.append(task_g_dir / "final-dub" / f"final_dub.{request.target_lang}.mp4")
    return artifact_paths


def _delivery_audio_source(request: PipelineRequest) -> str:
    audio_source = str(request.delivery_policy.get("audio_source", "both") or "both")
    aliases = {
        "preview": "preview_mix",
        "final_preview": "preview_mix",
        "dub": "dub_voice",
        "final_dub": "dub_voice",
    }
    return aliases.get(audio_source, audio_source)


def _is_node_cache_hit(cache_spec: StageCacheSpec) -> bool:
    if not is_stage_cache_hit(cache_spec):
        return False
    if cache_spec.stage_name != "task-g":
        return True
    return _task_g_manifest_declares_expected_outputs(cache_spec)


def _task_g_manifest_declares_expected_outputs(cache_spec: StageCacheSpec) -> bool:
    try:
        manifest = _load_json(cache_spec.manifest_path)
    except Exception:
        return False
    request = manifest.get("request", {})
    artifacts = manifest.get("artifacts", {})
    expected_paths = {str(path) for path in cache_spec.artifact_paths}
    if any("/final-preview/" in path for path in expected_paths):
        if request.get("export_preview") is not True or not artifacts.get("final_preview_video"):
            return False
    if any("/final-dub/" in path for path in expected_paths):
        if request.get("export_dub") is not True or not artifacts.get("final_dub_video"):
            return False
    return True


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
        artifact_paths = _task_g_expected_artifact_paths(request)
    elif stage_name == "ocr-detect":
        manifest_path = ocr_detect_manifest_path(request)
        artifact_paths = [ocr_events_path(request), ocr_detection_path(request), ocr_source_srt_path(request)]
        if request.ocr_classify_text:
            artifact_paths.append(ocr_classified_events_path(request))
    elif stage_name == "ocr-translate":
        output_tag = output_tag_for_language(request.target_lang)
        manifest_path = request.output_root / "ocr-translate" / "ocr-translate-manifest.json"
        artifact_paths = [
            request.output_root / "ocr-translate" / f"ocr_subtitles.{output_tag}.json",
            request.output_root / "ocr-translate" / f"ocr_subtitles.{output_tag}.srt",
            manifest_path,
        ]
    elif stage_name == "visual-context":
        manifest_path = visual_context_manifest_path(request)
        artifact_paths = [visual_context_path(request), manifest_path]
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
    should_cancel: Callable[[], bool] | None = None,
    resume_ok: bool = False,
) -> dict[str, Any]:
    stage = stage_name  # string for monkeypatch compatibility
    if stage == "stage1":
        monitor.update_stage_progress(stage, 5.0, "separating source audio")
        run_stage_command(build_stage1_command(request), log_path=_stage_log_path(request, "stage1"), should_cancel=should_cancel)
        return {
            "manifest_path": str(stage1_manifest_path(request)),
            "artifact_paths": [str(stage1_voice_path(request)), str(stage1_background_path(request))],
            "log_path": str(_stage_log_path(request, "stage1")),
        }

    if stage == "task-a":
        monitor.update_stage_progress(stage, 5.0, "transcribing voice track")
        run_stage_command(build_task_a_command(request), log_path=_stage_log_path(request, "task-a"), should_cancel=should_cancel)
        return {
            "manifest_path": str(task_a_manifest_path(request)),
            "artifact_paths": [str(task_a_segments_path(request))],
            "log_path": str(_stage_log_path(request, "task-a")),
        }

    if stage == "task-b":
        monitor.update_stage_progress(stage, 5.0, "building speaker profiles")
        run_stage_command(build_task_b_command(request), log_path=_stage_log_path(request, "task-b"), should_cancel=should_cancel)
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
        run_stage_command(build_task_c_command(request), log_path=_stage_log_path(request, "task-c"), should_cancel=should_cancel)
        return {
            "manifest_path": str(task_c_manifest_path(request)),
            "artifact_paths": [str(task_c_translation_path(request))],
            "log_path": str(_stage_log_path(request, "task-c")),
        }

    if stage == "task-d":
        profiles_payload = _load_json(task_b_profiles_path(request))
        translation_payload = _load_json(task_c_translation_path(request))
        if not task_b_voice_bank_path(request).exists():
            build_voice_bank(
                VoiceBankRequest(
                    profiles_path=task_b_profiles_path(request),
                    output_dir=task_b_profiles_path(request).parent,
                    target_lang=request.target_lang,
                )
            )
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
            report_path = task_d_report_path(request, speaker_id)
            # ARCH-6: reuse a renderable report from a prior crash (same cache key)
            # and skip the heavy re-synthesis; a param change clears resume_ok so
            # everyone is re-synthesized.
            if _task_d_speaker_already_rendered(report_path, resume_ok=resume_ok):
                monitor.update_stage_progress(
                    stage, progress, f"speaker {speaker_id} resumed {index - 1}/{total}"
                )
                reports.append(str(report_path))
                if request.speaker_limit > 0 and len(reports) >= request.speaker_limit:
                    break
                continue
            run_stage_command(
                build_task_d_command(request, speaker_id=speaker_id, segment_ids=selected_segment_ids),
                log_path=_stage_log_path(request, "task-d"),
                should_cancel=should_cancel,
            )
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
        character_ledger_result = _build_character_ledger_for_task_e(
            request=request,
            task_d_reports=task_d_reports,
            monitor=monitor,
        )
        selected_segments_path = _run_dub_repair_for_task_e(
            request=request,
            task_d_reports=task_d_reports,
            character_ledger_path=(
                character_ledger_result.artifacts.ledger_path
                if character_ledger_result is not None
                else None
            ),
            monitor=monitor,
        )
        monitor.update_stage_progress(stage, 5.0, "rendering dub timeline")
        run_stage_command(
            build_task_e_command(
                request,
                task_d_reports=task_d_reports,
                selected_segments_path=selected_segments_path,
            ),
            log_path=_stage_log_path(request, "task-e"),
            should_cancel=should_cancel,
        )
        artifact_paths = [
            str(task_e_dub_voice_path(request)),
            str(task_e_preview_mix_path(request)),
            str(task_e_timeline_path(request)),
            str(task_e_mix_report_path(request)),
        ]
        if character_ledger_result is not None:
            artifact_paths.extend([
                str(character_ledger_result.artifacts.ledger_path),
                str(character_ledger_result.artifacts.report_path),
                str(character_ledger_result.artifacts.manifest_path),
            ])
        if selected_segments_path is not None:
            artifact_paths.append(str(selected_segments_path))
        benchmark_result = _build_dub_benchmark_for_task_e(
            request=request,
            monitor=monitor,
        )
        if benchmark_result is not None:
            artifact_paths.extend([
                str(benchmark_result.artifacts.benchmark_path),
                str(benchmark_result.artifacts.report_path),
                str(benchmark_result.artifacts.manifest_path),
            ])
        return {
            "manifest_path": str(task_e_manifest_path(request)),
            "artifact_paths": artifact_paths,
            "log_path": str(_stage_log_path(request, "task-e")),
        }

    raise ValueError(f"Unsupported stage: {stage}")


def _build_character_ledger_for_task_e(
    *,
    request: PipelineRequest,
    task_d_reports: list[Path],
    monitor: PipelineMonitor,
) -> CharacterLedgerResult | None:
    if not task_d_reports:
        return None
    try:
        monitor.update_stage_progress("task-e", 0.5, "building character ledger")
        return build_character_ledger(
            CharacterLedgerRequest(
                profiles_path=task_b_profiles_path(request),
                task_d_report_paths=task_d_reports,
                output_dir=request.output_root / "task-d" / "voice" / "character-ledger",
                target_lang=request.target_lang,
            )
        )
    except Exception as exc:  # pragma: no cover - diagnostics should not block baseline render
        logger.exception("Character ledger generation failed before Task E: %s", exc)
        return None


def _build_dub_benchmark_for_task_e(
    *,
    request: PipelineRequest,
    monitor: PipelineMonitor,
) -> DubBenchmarkResult | None:
    try:
        monitor.update_stage_progress("task-e", 95.0, "building dub benchmark")
        return build_dub_benchmark(
            DubBenchmarkRequest(
                pipeline_root=request.output_root,
                output_dir=request.output_root / "benchmark" / "voice",
                target_lang=request.target_lang,
            )
        )
    except Exception as exc:  # pragma: no cover - diagnostics should not block baseline render
        logger.exception("Dub benchmark generation failed after Task E: %s", exc)
        return None


def _run_dub_repair_for_task_e(
    *,
    request: PipelineRequest,
    task_d_reports: list[Path],
    character_ledger_path: Path | None,
    monitor: PipelineMonitor,
) -> Path | None:
    if not request.dub_repair_enabled:
        return None
    if not task_d_reports:
        return None

    plan_dir = request.output_root / "task-d" / "voice" / "repair-plan"
    run_dir = request.output_root / "task-d" / "voice" / "repair-run"
    try:
        monitor.update_stage_progress("task-e", 1.0, "planning dub repair")
        plan_result = plan_dub_repair(
            RepairPlanRequest(
                translation_path=task_c_translation_path(request),
                profiles_path=task_b_profiles_path(request),
                task_d_report_paths=task_d_reports,
                output_dir=plan_dir,
                target_lang=request.target_lang,
                glossary_path=request.glossary_path,
                max_items=request.dub_repair_max_items,
                api_model=request.api_model,
                api_base_url=request.api_base_url,
            )
        )
        repair_count = int(plan_result.manifest.get("stats", {}).get("repair_count") or 0)
        if repair_count <= 0:
            return None

        monitor.update_stage_progress("task-e", 3.0, f"running dub repair ({repair_count} candidates)")
        run_result = run_dub_repair(
            RepairRunRequest(
                repair_queue_path=plan_result.artifacts.repair_queue_path,
                rewrite_plan_path=plan_result.artifacts.rewrite_plan_path,
                reference_plan_path=plan_result.artifacts.reference_plan_path,
                character_ledger_path=character_ledger_path,
                output_dir=run_dir,
                tts_backends=_repair_backends_for_request(request),
                device=request.device,
                backread_model="tiny",
                max_items=request.dub_repair_max_items,
                attempts_per_item=request.dub_repair_attempts_per_item,
                include_risk=request.dub_repair_include_risk,
            )
        )
        return run_result.artifacts.selected_segments_path
    except Exception as exc:  # pragma: no cover - real backend failures should not block baseline render
        logger.exception("Dub repair failed before Task E; continuing with original Task D reports: %s", exc)
        return None


def _repair_backends_for_request(request: PipelineRequest) -> list[str]:
    configured = [
        str(backend)
        for backend in (request.dub_repair_backends or [])
        if str(backend) in {"moss-tts-nano-onnx", "qwen3tts", "voxcpm2"}
    ]
    if configured:
        return _dedupe(configured)
    return [str(request.tts_backend)]


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def execute_delivery_node(
    request: PipelineRequest,
    *,
    monitor: PipelineMonitor,
) -> dict[str, Any]:
    from ..delivery.runner import export_video
    from ..delivery.runner import resolve_delivery_inputs
    from ..types import ExportVideoRequest

    delivery_inputs = resolve_delivery_inputs(request)
    audio_source = _delivery_audio_source(request)
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
    should_cancel: Callable[[], bool] | None = None,
    resume_ok: bool = False,
) -> dict[str, Any]:
    if node_name in {"stage1", "task-a", "task-b", "task-c", "task-d", "task-e"}:
        return execute_stage(
            node_name, request, monitor=monitor, should_cancel=should_cancel, resume_ok=resume_ok
        )
    if node_name == "ocr-detect":
        monitor.update_stage_progress(node_name, 5.0, "extracting hard subtitles")
        return run_ocr_detect(request, log_path=_node_log_path(request, node_name), monitor=monitor, should_cancel=should_cancel)
    if node_name == "asr-ocr-correct":
        monitor.update_stage_progress(node_name, 5.0, "correcting ASR transcript with OCR")
        run_stage_command(build_asr_ocr_correction_command(request), log_path=_node_log_path(request, node_name), should_cancel=should_cancel)
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
            # Classified variant when classification ran: scene_text/watermark/
            # title_card events are skipped (not dialogue, must not be subtitled).
            events_path=effective_ocr_events_path(request),
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
    if node_name == "visual-context":
        monitor.update_stage_progress(node_name, 5.0, "analyzing video scenes")
        return run_visual_context(request, log_path=_node_log_path(request, node_name), monitor=monitor, should_cancel=should_cancel)
    if node_name == "subtitle-erase":
        monitor.update_stage_progress(node_name, 5.0, "erasing hard subtitles")
        return run_subtitle_erase(request, log_path=_node_log_path(request, node_name), monitor=monitor, should_cancel=should_cancel)
    if node_name == "task-g":
        return execute_delivery_node(request, monitor=monitor)
    raise TranslipError(f"Unsupported workflow node: {node_name}")


def run_pipeline(
    request: PipelineRequest,
    *,
    stage_executor=None,
    should_cancel: Callable[[], bool] | None = None,
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
        status_update_interval_sec=request.status_update_interval_sec,
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
            if request.reuse_existing and node_name not in force_stages and _is_node_cache_hit(cache_spec):
                monitor.start_stage(node_name, current_step="cached")
                monitor.complete_stage(node_name, status="cached", current_step="cached")
                stage_row["status"] = "cached"
                stage_row["cache_hit"] = True
                print(f"[node:{node_name}] status=cached")
                continue

            monitor.start_stage(node_name, current_step="starting")
            print(f"[workflow] status=running node={node_name}")
            try:
                if should_cancel is not None and should_cancel():
                    raise StageSubprocessCancelled(
                        command=[f"node:{node_name}"],
                        log_path=Path(stage_row["log_path"]),
                    )
                if stage_executor is not None and node_name in {"stage1", "task-a", "task-b", "task-c", "task-d", "task-e"}:
                    result = stage_executor(node_name, request, monitor=monitor)
                else:
                    # ARCH-6: allow per-speaker resume only when re-running with an
                    # unchanged cache key (a crash, not a param change).
                    resume_ok = (
                        cache_spec.previous_cache_key is not None
                        and cache_spec.cache_key == cache_spec.previous_cache_key
                    )
                    result = execute_node(
                        node_name,
                        request,
                        monitor=monitor,
                        should_cancel=should_cancel,
                        resume_ok=resume_ok,
                    )
            except StageSubprocessCancelled:
                stage_row["status"] = "failed"
                stage_row["error"] = "Stopped by user"
                stage_row["error_message"] = "Stopped by user"
                monitor.fail_stage(node_name, error="Stopped by user")
                raise
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
