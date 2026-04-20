from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from ..exceptions import TranslipError
from ..types import DubbingArtifacts, DubbingRequest, DubbingResult
from ..utils.files import ensure_directory, remove_tree, work_directory
from .backend import ReferencePackage, SynthSegmentInput
from .export import build_dubbing_manifest, build_dubbing_report, now_iso, render_demo_audio, write_json
from .metrics import evaluate_segment
from .moss_tts_nano_backend import MossTtsNanoOnnxBackend
from .qwen_tts_backend import QwenTTSBackend
from .reference import (
    load_profiles_payload,
    prepare_reference_package,
    select_reference_candidates,
)

logger = logging.getLogger(__name__)


def synthesize_speaker(
    request: DubbingRequest,
    *,
    backend_override: object | None = None,
) -> DubbingResult:
    normalized_request = _validate_request(request)
    translation_payload = json.loads(Path(normalized_request.translation_path).read_text(encoding="utf-8"))
    profiles_payload = load_profiles_payload(Path(normalized_request.profiles_path))
    target_lang = str(translation_payload.get("backend", {}).get("target_lang") or "en")

    bundle_dir = ensure_directory(
        Path(normalized_request.output_dir)
        / Path(normalized_request.translation_path).parent.name
        / normalized_request.speaker_id
    )
    work_dir = work_directory(Path(normalized_request.output_dir))
    report_path = bundle_dir / f"speaker_segments.{translation_payload.get('backend', {}).get('output_tag', target_lang)}.json"
    manifest_path = bundle_dir / "task-d-manifest.json"

    started_at = now_iso()
    started_monotonic = time.monotonic()
    copied_intermediates: dict[str, Path] = {}

    try:
        segments = _filtered_segments(translation_payload, normalized_request)
        backend = backend_override if backend_override is not None else _build_backend(normalized_request)
        reference_candidates = select_reference_candidates(
            profiles_payload=profiles_payload,
            speaker_id=normalized_request.speaker_id,
            reference_clip_path=normalized_request.reference_clip_path,
        )
        succeeded_audio_paths: list[Path] = []
        report_segments: list[dict[str, Any]] = []
        prepared_references: dict[Path, ReferencePackage] = {}

        for index, segment_row in enumerate(segments, start=1):
            segment = SynthSegmentInput(
                segment_id=str(segment_row["segment_id"]),
                speaker_id=normalized_request.speaker_id,
                target_lang=target_lang,
                target_text=str(segment_row["target_text"]).strip(),
                source_duration_sec=float(segment_row["duration"]),
                duration_budget_sec=float(
                    segment_row["duration_budget"].get("estimated_target_sec")
                    or segment_row["duration_budget"].get("estimated_tts_duration_sec")
                    or 0.0
                ),
                qa_flags=[str(flag) for flag in segment_row.get("qa_flags", [])],
                metadata={"context_unit_id": segment_row.get("context_unit_id")},
            )
            output_path = bundle_dir / "segments" / f"{segment.segment_id}.wav"
            synthesis_error: Exception | None = None
            selected_reference: ReferencePackage | None = None
            synth_output = None

            for candidate in reference_candidates[:2]:
                prepared = prepared_references.get(candidate.path)
                if prepared is None:
                    prepared = prepare_reference_package(
                        candidate,
                        output_path=work_dir / "reference" / f"{candidate.path.stem}_prepared.wav",
                    )
                    prepared_references[candidate.path] = prepared
                try:
                    synth_output = backend.synthesize(reference=prepared, segment=segment, output_path=output_path)
                    selected_reference = prepared
                    break
                except Exception as exc:  # pragma: no cover - covered by real pipeline run
                    synthesis_error = exc
                    logger.warning(
                        "Task D synthesis failed for %s with reference %s: %s",
                        segment.segment_id,
                        candidate.path,
                        exc,
                    )

            if synth_output is None or selected_reference is None:
                raise TranslipError(
                    f"Failed to synthesize segment {segment.segment_id}: {synthesis_error}"
                )

            evaluation = evaluate_segment(
                reference_audio_path=selected_reference.original_audio_path,
                generated_audio_path=synth_output.audio_path,
                target_text=segment.target_text,
                target_lang=target_lang,
                source_duration_sec=segment.source_duration_sec,
                requested_device=normalized_request.device,
                backread_model_name=normalized_request.backread_model,
            )
            succeeded_audio_paths.append(synth_output.audio_path)
            report_segments.append(
                {
                    "segment_id": segment.segment_id,
                    "speaker_id": normalized_request.speaker_id,
                    "target_text": segment.target_text,
                    "source_duration_sec": round(segment.source_duration_sec, 3),
                    "generated_duration_sec": round(synth_output.generated_duration_sec, 3),
                    "duration_ratio": round(evaluation.duration_ratio, 3),
                    "duration_status": evaluation.duration_status,
                    "speaker_similarity": (
                        round(evaluation.speaker_similarity, 4)
                        if evaluation.speaker_similarity is not None
                        else None
                    ),
                    "speaker_status": evaluation.speaker_status,
                    "backread_text": evaluation.backread_text,
                    "text_similarity": round(evaluation.text_similarity, 4),
                    "intelligibility_status": evaluation.intelligibility_status,
                    "overall_status": evaluation.overall_status,
                    "qa_flags": segment.qa_flags,
                    "reference_path": str(selected_reference.original_audio_path),
                    "audio_path": str(synth_output.audio_path),
                    "index": index,
                }
            )
            partial_report = build_dubbing_report(
                request=normalized_request,
                target_lang=target_lang,
                backend_name=backend.backend_name,
                resolved_model=backend.resolved_model,
                resolved_device=backend.resolved_device,
                reference={
                    "path": str(selected_reference.original_audio_path),
                    "selection_reason": selected_reference.selection_reason,
                },
                segments=report_segments,
            )
            write_json(partial_report, report_path)

        demo_audio_path = render_demo_audio(
            succeeded_audio_paths,
            bundle_dir / f"speaker_demo.{translation_payload.get('backend', {}).get('output_tag', target_lang)}.wav",
        )
        reference_used = report_segments[0]["reference_path"] if report_segments else None
        reference_reason = next(iter(prepared_references.values())).selection_reason if prepared_references else None
        report = build_dubbing_report(
            request=normalized_request,
            target_lang=target_lang,
            backend_name=backend.backend_name,
            resolved_model=backend.resolved_model,
            resolved_device=backend.resolved_device,
            reference={
                "path": reference_used,
                "selection_reason": reference_reason,
            },
            segments=report_segments,
        )
        write_json(report, report_path)
        stats = report["stats"] | {
            "selected_segment_count": len(segments),
            "backread_model": normalized_request.backread_model,
        }
        manifest = build_dubbing_manifest(
            request=normalized_request,
            target_lang=target_lang,
            report_path=report_path,
            demo_audio_path=demo_audio_path,
            started_at=started_at,
            finished_at=now_iso(),
            elapsed_sec=time.monotonic() - started_monotonic,
            resolved={
                "tts_backend": backend.backend_name,
                "model": backend.resolved_model,
                "device": backend.resolved_device,
            },
            stats=stats,
        )
        write_json(manifest, manifest_path)
        if normalized_request.keep_intermediate:
            for prepared in prepared_references.values():
                target = bundle_dir / "intermediate" / prepared.prepared_audio_path.name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(prepared.prepared_audio_path.read_bytes())
                copied_intermediates[prepared.prepared_audio_path.stem] = target
        else:
            remove_tree(work_dir)
        return DubbingResult(
            request=normalized_request,
            artifacts=DubbingArtifacts(
                bundle_dir=bundle_dir,
                segments_dir=bundle_dir / "segments",
                report_path=report_path,
                manifest_path=manifest_path,
                demo_audio_path=demo_audio_path,
                intermediate_paths=copied_intermediates,
            ),
            manifest=manifest,
            work_dir=work_dir,
        )
    except Exception as exc:
        logger.exception("Task D speaker synthesis failed.")
        ensure_directory(bundle_dir)
        manifest = build_dubbing_manifest(
            request=normalized_request,
            target_lang=target_lang,
            report_path=report_path,
            demo_audio_path=None,
            started_at=started_at,
            finished_at=now_iso(),
            elapsed_sec=time.monotonic() - started_monotonic,
            resolved={},
            stats={},
            error=str(exc),
        )
        write_json(manifest, manifest_path)
        raise


def _validate_request(request: DubbingRequest) -> DubbingRequest:
    normalized = request.normalized()
    if not Path(normalized.translation_path).exists():
        raise TranslipError(f"Translation file does not exist: {normalized.translation_path}")
    if not Path(normalized.profiles_path).exists():
        raise TranslipError(f"Profiles file does not exist: {normalized.profiles_path}")
    if not normalized.speaker_id:
        raise TranslipError("speaker_id is required for Task D")
    if normalized.max_segments is not None and normalized.max_segments <= 0:
        raise TranslipError("max_segments must be greater than 0 when provided")
    return normalized


def _filtered_segments(
    translation_payload: dict[str, Any],
    request: DubbingRequest,
) -> list[dict[str, Any]]:
    rows = [
        row
        for row in translation_payload.get("segments", [])
        if isinstance(row, dict) and str(row.get("speaker_id")) == request.speaker_id
    ]
    if request.segment_ids:
        allowed = set(request.segment_ids)
        rows = [row for row in rows if str(row.get("segment_id")) in allowed]
    rows = sorted(rows, key=lambda item: (float(item.get("start", 0.0)), str(item.get("segment_id"))))
    if request.max_segments is not None:
        rows = rows[: request.max_segments]
    if not rows:
        raise TranslipError(f"No translation segments found for speaker {request.speaker_id}")
    return rows


def _build_backend(request: DubbingRequest) -> object:
    if request.backend == "moss-tts-nano-onnx":
        return MossTtsNanoOnnxBackend(requested_device=request.device)
    if request.backend == "qwen3tts":
        return QwenTTSBackend(requested_device=request.device)
    raise TranslipError(f"Unsupported dubbing backend: {request.backend}")
