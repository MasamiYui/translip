from __future__ import annotations

import json
import logging
import re
import shutil
import time
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from ..config import (
    DEFAULT_TTS_GENERATED_DURATION_HARD_RATIO,
    DEFAULT_TTS_GENERATED_DURATION_LOWER_RATIO,
)
from ..exceptions import TranslipError
from ..types import DubbingArtifacts, DubbingRequest, DubbingResult
from ..utils.files import ensure_directory, remove_tree, work_directory
from .backend import ReferencePackage, SynthSegmentInput, SynthSegmentOutput, TTSBackend
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

_UNIT_SPLIT_FRAME_SEC = 0.02
_UNIT_SPLIT_HOP_SEC = 0.01
_UNIT_SPLIT_MIN_PIECE_SEC = 0.08
_UNIT_SPLIT_MIN_SILENCE_SEC = 0.05
_UNIT_SPLIT_SEARCH_RADIUS_SEC = 0.25
_UNIT_SPLIT_MAX_SEARCH_RADIUS_SEC = 0.35
_UNIT_SPLIT_DURATION_GUARD_TOLERANCE = 0.18


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
        backends = (
            _backend_pool_from_override(backend_override)
            if backend_override is not None
            else _build_backend_pool(normalized_request)
        )
        backend_summary = _backend_pool_summary(backends)
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
                    backends=backends,
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
                    backends=backends,
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
                backend_name=backend_summary["backend_name"],
                resolved_model=backend_summary["resolved_model"],
                resolved_device=backend_summary["resolved_device"],
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
            backend_name=backend_summary["backend_name"],
            resolved_model=backend_summary["resolved_model"],
            resolved_device=backend_summary["resolved_device"],
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
                "tts_backend": backend_summary["backend_name"],
                "tts_backends": backend_summary["tts_backends"],
                "model": backend_summary["resolved_model"],
                "device": backend_summary["resolved_device"],
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
    boundaries, split_method = _unit_split_boundaries(
        waveform=waveform,
        sample_rate=int(sample_rate),
        segment_rows=segment_rows,
    )
    outputs: list[SynthSegmentOutput] = []
    cursor = 0
    for index, row in enumerate(segment_rows):
        end = total_samples if index == len(segment_rows) - 1 else boundaries[index]
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
                backend_metadata={
                    "unit_audio_path": str(unit_audio_path),
                    "split_strategy": "vad_text_boundary",
                    "split_method": split_method,
                    "split_start_sec": round(float((cursor - piece.size) / sample_rate), 4) if sample_rate else 0.0,
                    "split_end_sec": round(float(cursor / sample_rate), 4) if sample_rate else 0.0,
                },
            )
        )
    return outputs


def _unit_split_boundaries(
    *,
    waveform: np.ndarray,
    sample_rate: int,
    segment_rows: list[dict[str, Any]],
) -> tuple[list[int], str]:
    total_samples = int(waveform.size)
    if total_samples <= 0 or len(segment_rows) <= 1:
        return [], "single"
    expected = _expected_unit_boundaries(
        total_samples=total_samples,
        segment_rows=segment_rows,
    )
    duration_boundaries = _duration_unit_boundaries(
        total_samples=total_samples,
        segment_rows=segment_rows,
    )
    silence_intervals = _silence_intervals(waveform=waveform, sample_rate=sample_rate)
    boundaries: list[int] = []
    methods: list[str] = []
    min_piece = max(1, int(_UNIT_SPLIT_MIN_PIECE_SEC * sample_rate))
    for index, target in enumerate(expected):
        lower = (boundaries[-1] if boundaries else 0) + min_piece
        upper = total_samples - ((len(expected) - index) * min_piece)
        target = min(max(int(target), lower), max(lower, upper))
        boundary, method = _nearest_boundary(
            waveform=waveform,
            sample_rate=sample_rate,
            target=target,
            lower=lower,
            upper=max(lower, upper),
            silence_intervals=silence_intervals,
        )
        boundaries.append(boundary)
        methods.append(method)
    if _split_duration_deviation(boundaries, total_samples, sample_rate, segment_rows) > (
        _split_duration_deviation(duration_boundaries, total_samples, sample_rate, segment_rows)
        + _UNIT_SPLIT_DURATION_GUARD_TOLERANCE
    ):
        return duration_boundaries, "duration_guard"
    return boundaries, "+".join(_dedupe(methods))


def _expected_unit_boundaries(
    *,
    total_samples: int,
    segment_rows: list[dict[str, Any]],
) -> list[int]:
    duration_weights = [max(0.001, float(row.get("duration") or 0.0)) for row in segment_rows]
    text_weights = [_text_boundary_weight(row) for row in segment_rows]
    duration_total = max(sum(duration_weights), 0.001)
    text_total = max(sum(text_weights), 0.001)
    weights = [
        (0.75 * (duration / duration_total)) + (0.25 * (text / text_total))
        for duration, text in zip(duration_weights, text_weights, strict=True)
    ]
    return _boundaries_from_weights(total_samples=total_samples, weights=weights)


def _duration_unit_boundaries(
    *,
    total_samples: int,
    segment_rows: list[dict[str, Any]],
) -> list[int]:
    duration_weights = [max(0.001, float(row.get("duration") or 0.0)) for row in segment_rows]
    total = max(sum(duration_weights), 0.001)
    return _boundaries_from_weights(
        total_samples=total_samples,
        weights=[duration / total for duration in duration_weights],
    )


def _boundaries_from_weights(*, total_samples: int, weights: list[float]) -> list[int]:
    cumulative = 0.0
    boundaries: list[int] = []
    for weight in weights[:-1]:
        cumulative += weight
        boundaries.append(int(round(total_samples * cumulative)))
    return boundaries


def _split_duration_deviation(
    boundaries: list[int],
    total_samples: int,
    sample_rate: int,
    segment_rows: list[dict[str, Any]],
) -> float:
    if sample_rate <= 0:
        return 0.0
    starts = [0, *boundaries]
    ends = [*boundaries, total_samples]
    deviations: list[float] = []
    for start, end, row in zip(starts, ends, segment_rows, strict=True):
        generated_sec = max(0.001, float(end - start) / sample_rate)
        source_sec = max(0.001, float(row.get("duration") or 0.0))
        deviations.append(abs(np.log(generated_sec / source_sec)))
    return float(sum(deviations) / max(len(deviations), 1))


def _text_boundary_weight(row: dict[str, Any]) -> float:
    text = str(row.get("dubbing_text") or row.get("target_text") or "").strip()
    words = re.findall(r"[A-Za-z0-9']+", text)
    if words:
        return max(1.0, sum(max(1, len(word)) for word in words) / 4.0)
    cjk_chars = re.findall(r"[\u4e00-\u9fff]", text)
    if cjk_chars:
        return max(1.0, float(len(cjk_chars)))
    return max(1.0, float(len(text)) / 4.0)


def _silence_intervals(*, waveform: np.ndarray, sample_rate: int) -> list[tuple[int, int]]:
    if waveform.size == 0 or sample_rate <= 0:
        return []
    frame = max(1, int(_UNIT_SPLIT_FRAME_SEC * sample_rate))
    hop = max(1, int(_UNIT_SPLIT_HOP_SEC * sample_rate))
    if waveform.size <= frame:
        return []
    rms_values: list[float] = []
    starts: list[int] = []
    for start in range(0, waveform.size - frame + 1, hop):
        window = waveform[start : start + frame]
        rms_values.append(float(np.sqrt(np.mean(np.square(window), dtype=np.float64))))
        starts.append(start)
    if not rms_values:
        return []
    rms = np.asarray(rms_values, dtype=np.float32)
    max_rms = float(np.max(rms))
    if max_rms <= 0.0:
        return [(0, int(waveform.size))]
    threshold = max(float(np.percentile(rms, 20)) * 1.6, max_rms * 0.035, 1e-5)
    silent = rms <= threshold
    min_silence = max(1, int(_UNIT_SPLIT_MIN_SILENCE_SEC * sample_rate))
    intervals: list[tuple[int, int]] = []
    run_start: int | None = None
    run_end: int | None = None
    for is_silent, start in zip(silent, starts, strict=True):
        if is_silent:
            if run_start is None:
                run_start = start
            run_end = start + frame
        elif run_start is not None and run_end is not None:
            if run_end - run_start >= min_silence:
                intervals.append((run_start, min(run_end, int(waveform.size))))
            run_start = None
            run_end = None
    if run_start is not None and run_end is not None and run_end - run_start >= min_silence:
        intervals.append((run_start, min(run_end, int(waveform.size))))
    return intervals


def _nearest_boundary(
    *,
    waveform: np.ndarray,
    sample_rate: int,
    target: int,
    lower: int,
    upper: int,
    silence_intervals: list[tuple[int, int]],
) -> tuple[int, str]:
    radius = min(
        int(_UNIT_SPLIT_MAX_SEARCH_RADIUS_SEC * sample_rate),
        max(int(_UNIT_SPLIT_SEARCH_RADIUS_SEC * sample_rate), int(waveform.size * 0.05)),
    )
    silence_centers = [
        int(round((start + end) / 2))
        for start, end in silence_intervals
        if lower <= int(round((start + end) / 2)) <= upper and abs(int(round((start + end) / 2)) - target) <= radius
    ]
    if silence_centers:
        return min(silence_centers, key=lambda item: abs(item - target)), "silence"
    search_start = max(lower, target - radius)
    search_end = min(upper, target + radius)
    if search_end <= search_start:
        return target, "text_weighted"
    boundary = _lowest_energy_sample(
        waveform=waveform,
        sample_rate=sample_rate,
        start=search_start,
        end=search_end,
    )
    return boundary, "energy_min"


def _lowest_energy_sample(
    *,
    waveform: np.ndarray,
    sample_rate: int,
    start: int,
    end: int,
) -> int:
    frame = max(1, int(_UNIT_SPLIT_FRAME_SEC * sample_rate))
    hop = max(1, int(_UNIT_SPLIT_HOP_SEC * sample_rate))
    if end - start <= frame:
        return int(round((start + end) / 2))
    best_start = start
    best_energy: float | None = None
    for frame_start in range(start, end - frame + 1, hop):
        window = waveform[frame_start : frame_start + frame]
        energy = float(np.mean(np.square(window), dtype=np.float64))
        if best_energy is None or energy < best_energy:
            best_energy = energy
            best_start = frame_start
    return best_start + (frame // 2)


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
        "tts_backend": attempt_summary.get("selected_backend"),
        "resolved_model": attempt_summary.get("selected_model"),
        "resolved_device": attempt_summary.get("selected_device"),
        "attempt_count": attempt_summary["attempt_count"],
        "selected_attempt_index": attempt_summary["selected_attempt_index"],
        "selected_reference_attempt_index": attempt_summary.get("selected_reference_attempt_index"),
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
        row["split_strategy"] = synth_output.backend_metadata.get("split_strategy")
        row["split_method"] = synth_output.backend_metadata.get("split_method")
        row["split_start_sec"] = synth_output.backend_metadata.get("split_start_sec")
        row["split_end_sec"] = synth_output.backend_metadata.get("split_end_sec")
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
    backends: list[TTSBackend],
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
    attempt_index = 0

    for candidate_index, candidate in enumerate(reference_candidates, start=1):
        prepared = prepared_references.get(candidate.path)
        if prepared is None:
            prepared = prepare_reference_package(
                candidate,
                output_path=work_dir / "reference" / f"{candidate.path.stem}_prepared.wav",
            )
            prepared_references[candidate.path] = prepared
        candidate_attempts: list[dict[str, Any]] = []
        for backend_index, backend in enumerate(backends, start=1):
            attempt_index += 1
            attempt_path = (
                work_dir
                / "attempts"
                / segment.segment_id
                / f"{_safe_audio_id(backend.backend_name)}_ref-{candidate_index:02d}.wav"
            )
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
                    "Task D synthesis failed for %s with backend %s and reference %s: %s",
                    segment.segment_id,
                    backend.backend_name,
                    candidate.path,
                    exc,
                )
                attempts.append(
                    {
                        "attempt_index": attempt_index,
                        "reference_attempt_index": candidate_index,
                        "backend_index": backend_index,
                        "backend": backend.backend_name,
                        "resolved_model": backend.resolved_model,
                        "resolved_device": backend.resolved_device,
                        "reference_path": str(candidate.path),
                        "status": "failed",
                        "error": str(exc),
                    }
                )
                continue

            attempt = {
                "attempt_index": attempt_index,
                "reference_attempt_index": candidate_index,
                "backend_index": backend_index,
                "backend": backend.backend_name,
                "resolved_model": backend.resolved_model,
                "resolved_device": backend.resolved_device,
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
                "_backend": backend,
                "_prepared": prepared,
                "_synth_output": synth_output,
                "_evaluation": evaluation,
            }
            attempts.append(attempt)
            candidate_attempts.append(attempt)
        if candidate_attempts:
            best_candidate = max(candidate_attempts, key=lambda attempt: _attempt_score(attempt["_evaluation"]))
            candidate_retry_reasons = _quality_retry_reasons(best_candidate["_evaluation"])
            if candidate_index == 1:
                retry_reasons = candidate_retry_reasons
            if not candidate_retry_reasons:
                break

    successful_attempts = [attempt for attempt in attempts if attempt.get("status") == "candidate"]
    if not successful_attempts:
        raise TranslipError(f"Failed to synthesize segment {segment.segment_id}: {synthesis_error}")

    selected = max(successful_attempts, key=lambda attempt: _attempt_score(attempt["_evaluation"]))
    selected["status"] = "selected"
    selected_output = selected["_synth_output"]
    selected_reference = selected["_prepared"]
    selected_evaluation = selected["_evaluation"]
    selected_backend = selected["_backend"]
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
        backend_metadata={
            **dict(getattr(selected_output, "backend_metadata", {}) or {}),
            "selected_backend": selected_backend.backend_name,
        },
    )
    return (
        final_output,
        selected_reference,
        selected_evaluation,
        {
            "attempt_count": len(attempts),
            "selected_attempt_index": int(selected["attempt_index"]),
            "selected_reference_attempt_index": int(selected["reference_attempt_index"]),
            "selected_backend": selected_backend.backend_name,
            "selected_model": selected_backend.resolved_model,
            "selected_device": selected_backend.resolved_device,
            "quality_retry_reasons": retry_reasons,
            "attempts": report_attempts,
        },
    )


def _quality_retry_reasons(evaluation: object) -> list[str]:
    reasons: list[str] = []
    duration_ratio = float(getattr(evaluation, "duration_ratio", 0.0) or 0.0)
    text_similarity = float(getattr(evaluation, "text_similarity", 0.0) or 0.0)
    duration_status = str(getattr(evaluation, "duration_status", ""))
    hard_upper = DEFAULT_TTS_GENERATED_DURATION_HARD_RATIO
    hard_lower = DEFAULT_TTS_GENERATED_DURATION_LOWER_RATIO
    # Historical threshold (2.0 / 0.45) triggered retry only when status was
    # already "failed". Sprint 2 tightens this: if the generated audio is
    # *obviously* out of band (e.g. 1.5x the source window) we retry even if
    # downstream metric accepted it, because that kind of pathology leaks into
    # the "mom mom mom..." loops observed in task-20260425-023015.
    if duration_ratio >= hard_upper or (0.0 < duration_ratio <= hard_lower):
        reasons.append("pathological_duration")
    elif duration_status == "failed" and (
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


def _backend_pool_from_override(backend_override: object) -> list[TTSBackend]:
    if isinstance(backend_override, (list, tuple)):
        return list(backend_override)
    return [backend_override]


def _build_backend_pool(request: DubbingRequest) -> list[TTSBackend]:
    backend_names = request.tts_backends or [request.backend]
    return [_build_backend(backend_name, requested_device=request.device) for backend_name in backend_names]


def _build_backend(
    backend_name: str | DubbingRequest,
    *,
    requested_device: str | None = None,
) -> TTSBackend:
    if isinstance(backend_name, DubbingRequest):
        request = backend_name.normalized()
        backend_name = request.backend
        requested_device = request.device
    requested_device = requested_device or "auto"
    if backend_name == "moss-tts-nano-onnx":
        return MossTtsNanoOnnxBackend(requested_device=requested_device)
    if backend_name == "qwen3tts":
        return QwenTTSBackend(requested_device=requested_device)
    raise TranslipError(f"Unsupported dubbing backend: {backend_name}")


def _backend_pool_summary(backends: list[TTSBackend]) -> dict[str, Any]:
    return {
        "backend_name": "+".join(backend.backend_name for backend in backends),
        "tts_backends": [backend.backend_name for backend in backends],
        "resolved_model": "+".join(str(backend.resolved_model) for backend in backends),
        "resolved_device": "+".join(str(backend.resolved_device) for backend in backends),
    }
