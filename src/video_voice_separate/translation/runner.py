from __future__ import annotations

import json
import time
from pathlib import Path

from ..exceptions import VideoVoiceSeparateError
from ..types import TranslationArtifacts, TranslationRequest, TranslationResult
from ..utils.files import ensure_directory
from .backend import BackendSegmentInput, output_tag_for_language
from .duration import build_duration_budget, summarize_duration_budgets
from .export import (
    build_editable_payload,
    build_translation_manifest,
    build_translation_payload,
    now_iso,
    write_json,
    write_translation_srt,
)
from .glossary import apply_glossary, load_glossary, normalize_target_with_glossary
from .qa import build_qa_flags
from .units import ContextUnit, SegmentRecord, build_context_units


def translate_script(
    request: TranslationRequest,
    *,
    backend_override: object | None = None,
) -> TranslationResult:
    normalized_request = _validate_request(request)
    bundle_dir = ensure_directory(
        Path(normalized_request.output_dir) / Path(normalized_request.segments_path).parent.name
    )
    started_at = now_iso()
    started_monotonic = time.monotonic()
    manifest_path = bundle_dir / "task-c-manifest.json"

    try:
        segments_payload = json.loads(Path(normalized_request.segments_path).read_text(encoding="utf-8"))
        profiles_payload = json.loads(Path(normalized_request.profiles_path).read_text(encoding="utf-8"))
        normalized_request.source_lang = _resolved_source_language(
            requested=normalized_request.source_lang,
            payload=segments_payload,
        )
        output_tag = output_tag_for_language(normalized_request.target_lang)
        translation_json_path = bundle_dir / f"translation.{output_tag}.json"
        editable_json_path = bundle_dir / f"translation.{output_tag}.editable.json"
        srt_path = bundle_dir / f"translation.{output_tag}.srt"

        segments = _load_segment_records(segments_payload, profiles_payload)
        units = build_context_units(segments)
        glossary = load_glossary(Path(normalized_request.glossary_path) if normalized_request.glossary_path else None)
        backend = backend_override if backend_override is not None else build_translation_backend(normalized_request)

        translated_segments, editable_units, glossary_match_count = _translate_units(
            units=units,
            glossary=glossary,
            request=normalized_request,
            backend=backend,
        )

        payload = build_translation_payload(
            request=normalized_request,
            backend_name=backend.backend_name,
            resolved_model=backend.resolved_model,
            resolved_device=backend.resolved_device,
            output_tag=output_tag,
            segments=translated_segments,
            units=editable_units,
            glossary_match_count=glossary_match_count,
        )
        editable_payload = build_editable_payload(
            request=normalized_request,
            backend_name=backend.backend_name,
            resolved_model=backend.resolved_model,
            output_tag=output_tag,
            units=editable_units,
        )
        write_json(payload, translation_json_path)
        write_json(editable_payload, editable_json_path)
        write_translation_srt(translated_segments, srt_path)

        stats = payload["stats"]
        manifest = build_translation_manifest(
            request=normalized_request,
            output_tag=output_tag,
            translation_json_path=translation_json_path,
            editable_json_path=editable_json_path,
            srt_path=srt_path,
            started_at=started_at,
            finished_at=now_iso(),
            elapsed_sec=time.monotonic() - started_monotonic,
            resolved={
                "translation_backend": backend.backend_name,
                "model": backend.resolved_model,
                "device": backend.resolved_device,
            },
            stats=stats,
        )
        write_json(manifest, manifest_path)
        return TranslationResult(
            request=normalized_request,
            artifacts=TranslationArtifacts(
                bundle_dir=bundle_dir,
                translation_json_path=translation_json_path,
                editable_json_path=editable_json_path,
                srt_path=srt_path,
                manifest_path=manifest_path,
            ),
            manifest=manifest,
        )
    except Exception as exc:
        output_tag = output_tag_for_language(normalized_request.target_lang)
        manifest = build_translation_manifest(
            request=normalized_request,
            output_tag=output_tag,
            translation_json_path=bundle_dir / f"translation.{output_tag}.json",
            editable_json_path=bundle_dir / f"translation.{output_tag}.editable.json",
            srt_path=bundle_dir / f"translation.{output_tag}.srt",
            started_at=started_at,
            finished_at=now_iso(),
            elapsed_sec=time.monotonic() - started_monotonic,
            resolved={},
            stats={},
            error=str(exc),
        )
        write_json(manifest, manifest_path)
        raise


def build_translation_backend(request: TranslationRequest) -> object:
    if request.backend == "local-m2m100":
        from .m2m100_backend import M2M100Backend

        return M2M100Backend(model_name=request.local_model, requested_device=request.device)
    if request.backend == "siliconflow":
        from .siliconflow_backend import SiliconFlowBackend

        return SiliconFlowBackend(
            base_url=request.api_base_url,
            model_name=request.api_model,
        )
    raise VideoVoiceSeparateError(f"Unsupported translation backend: {request.backend}")


def _validate_request(request: TranslationRequest) -> TranslationRequest:
    normalized = request.normalized()
    if not Path(normalized.segments_path).exists():
        raise VideoVoiceSeparateError(f"Segments file does not exist: {normalized.segments_path}")
    if not Path(normalized.profiles_path).exists():
        raise VideoVoiceSeparateError(f"Profiles file does not exist: {normalized.profiles_path}")
    if normalized.glossary_path is not None and not Path(normalized.glossary_path).exists():
        raise VideoVoiceSeparateError(f"Glossary file does not exist: {normalized.glossary_path}")
    if normalized.batch_size <= 0:
        raise VideoVoiceSeparateError("batch_size must be greater than 0")
    return normalized


def _resolved_source_language(*, requested: str, payload: dict[str, object]) -> str:
    if requested and requested != "auto":
        return requested
    segments = payload.get("segments", [])
    if isinstance(segments, list) and segments:
        first = segments[0]
        if isinstance(first, dict) and first.get("language"):
            return str(first["language"])
    return "zh"


def _load_segment_records(
    segments_payload: dict[str, object],
    profiles_payload: dict[str, object],
) -> list[SegmentRecord]:
    speaker_map: dict[str, str | None] = {}
    for profile in profiles_payload.get("profiles", []):
        if not isinstance(profile, dict):
            continue
        speaker_map[str(profile.get("source_label"))] = (
            str(profile["speaker_id"]) if profile.get("speaker_id") else None
        )
    records: list[SegmentRecord] = []
    for raw in segments_payload.get("segments", []):
        if not isinstance(raw, dict):
            continue
        speaker_label = str(raw["speaker_label"])
        records.append(
            SegmentRecord(
                segment_id=str(raw["id"]),
                start=float(raw["start"]),
                end=float(raw["end"]),
                duration=float(raw["duration"]),
                speaker_label=speaker_label,
                speaker_id=speaker_map.get(speaker_label),
                text=str(raw["text"]).strip(),
                language=str(raw.get("language") or "zh"),
            )
        )
    return records


def _translate_units(
    *,
    units: list[ContextUnit],
    glossary: list[object],
    request: TranslationRequest,
    backend: object,
) -> tuple[list[dict[str, object]], list[dict[str, object]], int]:
    segment_rows: list[dict[str, object]] = []
    editable_units: list[dict[str, object]] = []
    glossary_match_count = 0

    for unit in units:
        prepared_items: list[BackendSegmentInput] = []
        prepared_meta: dict[str, tuple[str, list[dict[str, object]]]] = {}
        for segment in unit.segments:
            prepared_text, glossary_matches = apply_glossary(
                segment.text,
                target_lang=request.target_lang,
                glossary=glossary,
            )
            glossary_match_count += len(glossary_matches)
            prepared_items.append(
                BackendSegmentInput(
                    segment_id=segment.segment_id,
                    source_text=prepared_text,
                    context_text=unit.source_text,
                    metadata={"speaker_label": segment.speaker_label},
                )
            )
            prepared_meta[segment.segment_id] = (prepared_text, glossary_matches)

        translated_by_id: dict[str, str] = {}
        for index in range(0, len(prepared_items), request.batch_size):
            batch = prepared_items[index : index + request.batch_size]
            outputs = backend.translate_batch(
                items=batch,
                source_lang=request.source_lang,
                target_lang=request.target_lang,
            )
            for output in outputs:
                translated_by_id[output.segment_id] = output.target_text.strip()

        unit_segment_rows: list[dict[str, object]] = []
        for segment in unit.segments:
            prepared_text, glossary_matches = prepared_meta[segment.segment_id]
            target_text = translated_by_id.get(segment.segment_id, "").strip()
            target_text = normalize_target_with_glossary(
                source_text=segment.text,
                target_text=target_text,
                glossary_matches=glossary_matches,
            )
            duration_budget = build_duration_budget(
                source_duration_sec=segment.duration,
                target_text=target_text,
                target_lang=request.target_lang,
            )
            qa_flags = build_qa_flags(
                source_text=segment.text,
                target_text=target_text,
                glossary_matches=glossary_matches,
                duration_budget=duration_budget,
            )
            row = {
                "segment_id": segment.segment_id,
                "speaker_label": segment.speaker_label,
                "speaker_id": segment.speaker_id,
                "start": round(segment.start, 3),
                "end": round(segment.end, 3),
                "duration": round(segment.duration, 3),
                "source_text": segment.text,
                "prepared_source_text": prepared_text,
                "target_text": target_text,
                "context_unit_id": unit.unit_id,
                "glossary_matches": glossary_matches,
                "duration_budget": duration_budget,
                "qa_flags": qa_flags,
            }
            segment_rows.append(row)
            unit_segment_rows.append(row)

        editable_units.append(
            {
                "unit_id": unit.unit_id,
                "speaker_label": unit.speaker_label,
                "speaker_id": unit.speaker_id,
                "start": round(unit.start, 3),
                "end": round(unit.end, 3),
                "segment_ids": [segment.segment_id for segment in unit.segments],
                "source_text": unit.source_text,
                "draft_text": " ".join(row["target_text"] for row in unit_segment_rows).strip(),
                "edited_text": None,
                "duration_summary": summarize_duration_budgets(
                    [row["duration_budget"] for row in unit_segment_rows]
                ),
                "status": "draft",
                "notes": [],
                "segments": [
                    {
                        "segment_id": row["segment_id"],
                        "source_text": row["source_text"],
                        "draft_text": row["target_text"],
                        "qa_flags": row["qa_flags"],
                        "fit_level": row["duration_budget"]["fit_level"],
                    }
                    for row in unit_segment_rows
                ],
            }
        )
    return segment_rows, editable_units, glossary_match_count
