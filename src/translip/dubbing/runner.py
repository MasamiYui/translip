from __future__ import annotations

import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from ..exceptions import TranslipError
from ..types import DubbingArtifacts, DubbingRequest, DubbingResult
from ..utils.files import ensure_directory, remove_tree, work_directory
from .backend import ReferencePackage, SynthSegmentInput, SynthSegmentOutput
from .export import build_dubbing_manifest, build_dubbing_report, now_iso, render_demo_audio, write_json
from .metrics import evaluate_segment
from .moss_tts_nano_backend import MossTtsNanoOnnxBackend
from .qwen_tts_backend import QwenTTSBackend
from .reference import (
    load_profiles_payload,
    prepare_reference_package,
    select_reference_candidates,
    select_voice_bank_reference_candidates,
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
        reference_candidates = _select_reference_candidates(
            profiles_payload=profiles_payload,
            speaker_id=normalized_request.speaker_id,
            reference_clip_path=normalized_request.reference_clip_path,
            voice_bank_path=normalized_request.voice_bank_path,
        )
        succeeded_audio_paths: list[Path] = []
        report_segments: list[dict[str, Any]] = []
        prepared_references: dict[Path, ReferencePackage] = {}

        for group in _synthesis_groups(segments):
            if len(group) == 1:
                segment_row = group[0]
                segment = _segment_input_from_row(
                    segment_row,
                    speaker_id=normalized_request.speaker_id,
                    target_lang=target_lang,
                )
                output_path = bundle_dir / "segments" / f"{segment.segment_id}.wav"
                synth_output, selected_reference, evaluation, attempt_summary = _synthesize_with_quality_retry(
                    backend=backend,
                    segment=segment,
                    output_path=output_path,
                    reference_candidates=reference_candidates[:3],
                    prepared_references=prepared_references,
                    work_dir=work_dir,
                    request=normalized_request,
                    target_lang=target_lang,
                )
                succeeded_audio_paths.append(synth_output.audio_path)
                report_segments.append(
                    _segment_report_row(
                        segment_row=segment_row,
                        segment=segment,
                        synth_output=synth_output,
                        selected_reference=selected_reference,
                        evaluation=evaluation,
                        attempt_summary=attempt_summary,
                        index=len(report_segments) + 1,
                        synthesis_mode="segment",
                    )
                )
            else:
                unit_rows = group
                unit_segment = _unit_input_from_rows(
                    unit_rows,
                    speaker_id=normalized_request.speaker_id,
                    target_lang=target_lang,
                )
                unit_output_path = bundle_dir / "units" / f"{unit_segment.segment_id}.wav"
                synth_output, selected_reference, evaluation, attempt_summary = _synthesize_with_quality_retry(
                    backend=backend,
                    segment=unit_segment,
                    output_path=unit_output_path,
                    reference_candidates=reference_candidates[:3],
                    prepared_references=prepared_references,
                    work_dir=work_dir,
                    request=normalized_request,
                    target_lang=target_lang,
                )
                split_outputs = _split_unit_audio(
                    unit_audio_path=synth_output.audio_path,
                    segment_rows=unit_rows,
                    output_dir=bundle_dir / "segments",
                )
                for segment_row, split_output in zip(unit_rows, split_outputs, strict=True):
                    segment = _segment_input_from_row(
                        segment_row,
                        speaker_id=normalized_request.speaker_id,
                        target_lang=target_lang,
                    )
                    succeeded_audio_paths.append(split_output.audio_path)
                    report_segments.append(
                        _segment_report_row(
                            segment_row=segment_row,
                            segment=segment,
                            synth_output=split_output,
                            selected_reference=selected_reference,
                            evaluation=evaluation,
                            attempt_summary=attempt_summary,
                            index=len(report_segments) + 1,
                            synthesis_mode="dubbing_unit",
                            unit_segment=unit_segment,
                            unit_audio_path=synth_output.audio_path,
                        )
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


def _segment_input_from_row(
    segment_row: dict[str, Any],
    *,
    speaker_id: str,
    target_lang: str,
) -> SynthSegmentInput:
    return SynthSegmentInput(
        segment_id=str(segment_row["segment_id"]),
        speaker_id=speaker_id,
        target_lang=target_lang,
        target_text=str(segment_row.get("dubbing_text") or segment_row["target_text"]).strip(),
        source_duration_sec=float(segment_row["duration"]),
        duration_budget_sec=float(
            segment_row.get("duration_budget", {}).get("estimated_target_sec")
            or segment_row.get("duration_budget", {}).get("estimated_tts_duration_sec")
            or 0.0
        ),
        qa_flags=[str(flag) for flag in segment_row.get("qa_flags", [])],
        metadata={"context_unit_id": segment_row.get("context_unit_id")},
    )


def _unit_input_from_rows(
    segment_rows: list[dict[str, Any]],
    *,
    speaker_id: str,
    target_lang: str,
) -> SynthSegmentInput:
    first = segment_rows[0]
    last = segment_rows[-1]
    unit_id = str(first.get("context_unit_id") or f"unit-{first.get('segment_id')}")
    target_text = _join_dubbing_text(segment_rows)
    source_duration_sec = max(
        sum(float(row.get("duration") or 0.0) for row in segment_rows),
        float(last.get("end") or 0.0) - float(first.get("start") or 0.0),
    )
    duration_budget_sec = sum(
        float(
            row.get("duration_budget", {}).get("estimated_target_sec")
            or row.get("duration_budget", {}).get("estimated_tts_duration_sec")
            or 0.0
        )
        for row in segment_rows
    )
    qa_flags = _dedupe(
        [
            str(flag)
            for row in segment_rows
            for flag in row.get("qa_flags", [])
        ]
        + ["dubbing_unit"]
    )
    return SynthSegmentInput(
        segment_id=_safe_audio_id(unit_id),
        speaker_id=speaker_id,
        target_lang=target_lang,
        target_text=target_text,
        source_duration_sec=source_duration_sec,
        duration_budget_sec=duration_budget_sec,
        qa_flags=qa_flags,
        metadata={
            "context_unit_id": first.get("context_unit_id"),
            "segment_ids": [str(row.get("segment_id")) for row in segment_rows],
            "synthesis_mode": "dubbing_unit",
        },
    )


def _synthesis_groups(segments: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    pending: list[dict[str, Any]] = []
    pending_context: str | None = None

    def flush() -> None:
        nonlocal pending, pending_context
        if not pending:
            return
        if _should_synthesize_as_unit(pending):
            groups.append(list(pending))
        else:
            groups.extend([[row] for row in pending])
        pending = []
        pending_context = None

    for row in segments:
        context_id = str(row.get("context_unit_id") or "")
        if not context_id:
            flush()
            groups.append([row])
            continue
        if pending and context_id != pending_context:
            flush()
        pending.append(row)
        pending_context = context_id
    flush()
    return groups


def _should_synthesize_as_unit(rows: list[dict[str, Any]]) -> bool:
    if len(rows) < 2 or len(rows) > 4:
        return False
    first_start = float(rows[0].get("start") or 0.0)
    last_end = float(rows[-1].get("end") or first_start)
    if last_end - first_start > 8.0:
        return False
    return any(_row_needs_dubbing_unit(row) for row in rows)


def _row_needs_dubbing_unit(row: dict[str, Any]) -> bool:
    flags = {str(flag) for flag in row.get("qa_flags", [])}
    script_flags = {str(flag) for flag in row.get("script_risk_flags", [])}
    return bool({"too_short_source"} & flags or {"needs_dubbing_unit", "target_fragment"} & script_flags)


def _split_unit_audio(
    *,
    unit_audio_path: Path,
    segment_rows: list[dict[str, Any]],
    output_dir: Path,
) -> list[SynthSegmentOutput]:
    waveform, sample_rate = sf.read(unit_audio_path, dtype="float32", always_2d=False)
    if waveform.ndim == 2:
        waveform = waveform.mean(axis=1)
    waveform = waveform.astype(np.float32)
    total_samples = int(waveform.size)
    durations = [max(0.001, float(row.get("duration") or 0.0)) for row in segment_rows]
    total_duration = sum(durations)
    outputs: list[SynthSegmentOutput] = []
    cursor = 0
    for index, (row, duration) in enumerate(zip(segment_rows, durations, strict=True)):
        if index == len(segment_rows) - 1:
            end = total_samples
        else:
            end = min(total_samples, cursor + int(round(total_samples * (duration / max(total_duration, 0.001)))))
        if end <= cursor:
            end = min(total_samples, cursor + 1)
        piece = waveform[cursor:end].astype(np.float32)
        cursor = end
        output_path = output_dir / f"{row['segment_id']}.wav"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(output_path, piece, sample_rate)
        outputs.append(
            SynthSegmentOutput(
                segment_id=str(row["segment_id"]),
                audio_path=output_path,
                sample_rate=int(sample_rate),
                generated_duration_sec=float(piece.size / sample_rate) if sample_rate else 0.0,
                backend_metadata={"unit_audio_path": str(unit_audio_path)},
            )
        )
    return outputs


def _segment_report_row(
    *,
    segment_row: dict[str, Any],
    segment: SynthSegmentInput,
    synth_output: SynthSegmentOutput,
    selected_reference: ReferencePackage,
    evaluation: object,
    attempt_summary: dict[str, Any],
    index: int,
    synthesis_mode: str,
    unit_segment: SynthSegmentInput | None = None,
    unit_audio_path: Path | None = None,
) -> dict[str, Any]:
    duration_ratio = (
        float(synth_output.generated_duration_sec) / max(float(segment.source_duration_sec), 0.001)
    )
    duration_status = (
        _duration_status_from_ratio(duration_ratio)
        if synthesis_mode == "dubbing_unit"
        else str(getattr(evaluation, "duration_status", ""))
    )
    speaker_status = str(getattr(evaluation, "speaker_status", ""))
    intelligibility_status = str(getattr(evaluation, "intelligibility_status", ""))
    overall_status = (
        _overall_status_from_parts(
            duration_status=duration_status,
            speaker_status=speaker_status,
            intelligibility_status=intelligibility_status,
        )
        if synthesis_mode == "dubbing_unit"
        else str(getattr(evaluation, "overall_status", ""))
    )
    row = {
        "segment_id": segment.segment_id,
        "speaker_id": segment.speaker_id,
        "target_text": str(segment_row.get("target_text") or segment.target_text),
        "dubbing_text": segment.target_text,
        "source_duration_sec": round(segment.source_duration_sec, 3),
        "generated_duration_sec": round(synth_output.generated_duration_sec, 3),
        "duration_ratio": round(duration_ratio, 3),
        "duration_status": duration_status,
        "speaker_similarity": (
            round(float(getattr(evaluation, "speaker_similarity")), 4)
            if getattr(evaluation, "speaker_similarity", None) is not None
            else None
        ),
        "speaker_status": speaker_status,
        "backread_text": str(getattr(evaluation, "backread_text", "")),
        "text_similarity": round(float(getattr(evaluation, "text_similarity", 0.0) or 0.0), 4),
        "intelligibility_status": intelligibility_status,
        "overall_status": overall_status,
        "qa_flags": segment.qa_flags,
        "reference_path": str(selected_reference.original_audio_path),
        "audio_path": str(synth_output.audio_path),
        "attempt_count": attempt_summary["attempt_count"],
        "selected_attempt_index": attempt_summary["selected_attempt_index"],
        "quality_retry_reasons": attempt_summary["quality_retry_reasons"],
        "attempts": attempt_summary["attempts"],
        "index": index,
        "synthesis_mode": synthesis_mode,
    }
    if unit_segment is not None:
        row["dubbing_unit_id"] = unit_segment.segment_id
        row["dubbing_unit_text"] = unit_segment.target_text
        row["dubbing_unit_segment_ids"] = list(unit_segment.metadata.get("segment_ids", []))
        row["dubbing_unit_audio_path"] = str(unit_audio_path) if unit_audio_path else None
    return row


def _join_dubbing_text(rows: list[dict[str, Any]]) -> str:
    return " ".join(str(row.get("dubbing_text") or row.get("target_text") or "").strip() for row in rows).strip()


def _safe_audio_id(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value) or "unit"


def _duration_status_from_ratio(duration_ratio: float) -> str:
    if 0.7 <= duration_ratio <= 1.35:
        return "passed"
    if 0.55 <= duration_ratio <= 1.65:
        return "review"
    return "failed"


def _overall_status_from_parts(
    *,
    duration_status: str,
    speaker_status: str,
    intelligibility_status: str,
) -> str:
    statuses = {duration_status, speaker_status, intelligibility_status}
    if "failed" in statuses:
        return "failed"
    if "review" in statuses:
        return "review"
    return "passed"


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def _select_reference_candidates(
    *,
    profiles_payload: dict[str, Any],
    speaker_id: str,
    reference_clip_path: Path | None,
    voice_bank_path: Path | None,
) -> list[object]:
    if reference_clip_path is not None:
        return select_reference_candidates(
            profiles_payload=profiles_payload,
            speaker_id=speaker_id,
            reference_clip_path=reference_clip_path,
        )
    if voice_bank_path is not None and Path(voice_bank_path).exists():
        try:
            voice_bank_payload = json.loads(Path(voice_bank_path).read_text(encoding="utf-8"))
            candidates = select_voice_bank_reference_candidates(
                voice_bank_payload=voice_bank_payload,
                speaker_id=speaker_id,
            )
            if candidates:
                return candidates
        except Exception as exc:
            logger.warning("Failed to load voice bank reference candidates from %s: %s", voice_bank_path, exc)
    return select_reference_candidates(
        profiles_payload=profiles_payload,
        speaker_id=speaker_id,
    )


def _synthesize_with_quality_retry(
    *,
    backend: object,
    segment: SynthSegmentInput,
    output_path: Path,
    reference_candidates: list[object],
    prepared_references: dict[Path, ReferencePackage],
    work_dir: Path,
    request: DubbingRequest,
    target_lang: str,
) -> tuple[SynthSegmentOutput, ReferencePackage, object, dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    retry_reasons: list[str] = []
    synthesis_error: Exception | None = None
    reference_tournament = os.environ.get("TRANSLIP_REFERENCE_TOURNAMENT", "").strip().lower() in {"1", "true", "yes"}

    for candidate_index, candidate in enumerate(reference_candidates, start=1):
        prepared = prepared_references.get(candidate.path)
        if prepared is None:
            prepared = prepare_reference_package(
                candidate,
                output_path=work_dir / "reference" / f"{candidate.path.stem}_prepared.wav",
            )
            prepared_references[candidate.path] = prepared
        attempt_path = work_dir / "attempts" / segment.segment_id / f"ref-{candidate_index:02d}.wav"
        try:
            synth_output = backend.synthesize(reference=prepared, segment=segment, output_path=attempt_path)
            evaluation = evaluate_segment(
                reference_audio_path=prepared.original_audio_path,
                generated_audio_path=synth_output.audio_path,
                target_text=segment.target_text,
                target_lang=target_lang,
                source_duration_sec=segment.source_duration_sec,
                requested_device=request.device,
                backread_model_name=request.backread_model,
            )
        except Exception as exc:  # pragma: no cover - covered by real pipeline run
            synthesis_error = exc
            logger.warning(
                "Task D synthesis failed for %s with reference %s: %s",
                segment.segment_id,
                candidate.path,
                exc,
            )
            attempts.append(
                {
                    "attempt_index": candidate_index,
                    "reference_path": str(candidate.path),
                    "status": "failed",
                    "error": str(exc),
                }
            )
            continue

        attempt = {
            "attempt_index": candidate_index,
            "reference_path": str(prepared.original_audio_path),
            "status": "candidate",
            "audio_path": str(synth_output.audio_path),
            "sample_rate": synth_output.sample_rate,
            "generated_duration_sec": round(float(synth_output.generated_duration_sec), 3),
            "duration_ratio": round(float(evaluation.duration_ratio), 3),
            "duration_status": evaluation.duration_status,
            "speaker_similarity": (
                round(float(evaluation.speaker_similarity), 4)
                if evaluation.speaker_similarity is not None
                else None
            ),
            "speaker_status": evaluation.speaker_status,
            "text_similarity": round(float(evaluation.text_similarity), 4),
            "intelligibility_status": evaluation.intelligibility_status,
            "overall_status": evaluation.overall_status,
            "_prepared": prepared,
            "_synth_output": synth_output,
            "_evaluation": evaluation,
        }
        attempts.append(attempt)
        if candidate_index == 1:
            retry_reasons = _quality_retry_reasons(evaluation)
            if not retry_reasons and not reference_tournament:
                break

    successful_attempts = [attempt for attempt in attempts if attempt.get("status") == "candidate"]
    if not successful_attempts:
        raise TranslipError(f"Failed to synthesize segment {segment.segment_id}: {synthesis_error}")

    selected = max(successful_attempts, key=lambda attempt: _attempt_score(attempt["_evaluation"]))
    selected["status"] = "selected"
    selected_output = selected["_synth_output"]
    selected_reference = selected["_prepared"]
    selected_evaluation = selected["_evaluation"]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(selected_output.audio_path, output_path)

    report_attempts: list[dict[str, Any]] = []
    for attempt in attempts:
        public = {key: value for key, value in attempt.items() if not key.startswith("_")}
        public["selected"] = attempt is selected
        if attempt is selected:
            public["audio_path"] = str(output_path)
        else:
            public.pop("audio_path", None)
        report_attempts.append(public)

    final_output = SynthSegmentOutput(
        segment_id=selected_output.segment_id,
        audio_path=output_path,
        sample_rate=int(selected_output.sample_rate),
        generated_duration_sec=float(selected_output.generated_duration_sec),
        backend_metadata=dict(getattr(selected_output, "backend_metadata", {}) or {}),
    )
    return (
        final_output,
        selected_reference,
        selected_evaluation,
        {
            "attempt_count": len(attempts),
            "selected_attempt_index": int(selected["attempt_index"]),
            "quality_retry_reasons": retry_reasons,
            "attempts": report_attempts,
        },
    )


def _quality_retry_reasons(evaluation: object) -> list[str]:
    reasons: list[str] = []
    duration_ratio = float(getattr(evaluation, "duration_ratio", 0.0) or 0.0)
    text_similarity = float(getattr(evaluation, "text_similarity", 0.0) or 0.0)
    if getattr(evaluation, "duration_status", "") == "failed" and (
        duration_ratio >= 2.0 or 0.0 < duration_ratio <= 0.45
    ):
        reasons.append("pathological_duration")
    if getattr(evaluation, "intelligibility_status", "") == "failed" and text_similarity < 0.6:
        reasons.append("poor_backread")
    speaker_similarity = getattr(evaluation, "speaker_similarity", None)
    if getattr(evaluation, "speaker_status", "") == "failed":
        if speaker_similarity is None or float(speaker_similarity) < 0.35:
            reasons.append("poor_speaker_match")
    return reasons


def _attempt_score(evaluation: object) -> float:
    overall = _status_score(str(getattr(evaluation, "overall_status", ""))) * 100.0
    duration = _status_score(str(getattr(evaluation, "duration_status", ""))) * 24.0
    intelligibility = _status_score(str(getattr(evaluation, "intelligibility_status", ""))) * 18.0
    speaker = _status_score(str(getattr(evaluation, "speaker_status", ""))) * 24.0
    duration_ratio = float(getattr(evaluation, "duration_ratio", 0.0) or 0.0)
    duration_proximity = max(0.0, 1.0 - abs(1.0 - duration_ratio))
    text = float(getattr(evaluation, "text_similarity", 0.0) or 0.0)
    speaker_similarity = getattr(evaluation, "speaker_similarity", None)
    speaker_score = float(speaker_similarity) if speaker_similarity is not None else 0.0
    return overall + duration + intelligibility + speaker + duration_proximity + text + (speaker_score * 8.0)


def _status_score(status: str) -> float:
    return {"passed": 2.0, "review": 1.0, "failed": 0.0}.get(status, 0.0)


def _build_backend(request: DubbingRequest) -> object:
    if request.backend == "moss-tts-nano-onnx":
        return MossTtsNanoOnnxBackend(requested_device=request.device)
    if request.backend == "qwen3tts":
        return QwenTTSBackend(requested_device=request.device)
    raise TranslipError(f"Unsupported dubbing backend: {request.backend}")
