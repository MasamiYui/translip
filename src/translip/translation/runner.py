from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

from ..exceptions import TranslipError
from ..types import TranslationArtifacts, TranslationRequest, TranslationResult
from ..utils.files import ensure_directory
from .backend import BackendSegmentInput, CondenseInput, canonical_language_code, output_tag_for_language
from .duration import build_duration_budget, estimate_tts_duration, summarize_duration_budgets
from .dubbing_script import polish_dubbing_script
from .export import (
    build_editable_payload,
    build_translation_manifest,
    build_translation_payload,
    now_iso,
    write_json,
    write_translation_srt,
)
from .glossary import (
    GlossaryEntry,
    apply_glossary,
    built_in_dubbing_glossary,
    load_glossary,
    merge_glossaries,
    normalize_target_with_glossary,
)
from .qa import build_qa_flags
from .units import ContextUnit, SegmentRecord, build_context_units

logger = logging.getLogger(__name__)

_CONDENSE_LEVELS = {
    "smart": {"risky"},
    "aggressive": {"risky", "review"},
}
_UNSAFE_RULE_BASED_CONDENSE_REASONS = {"trimmed_for_short_source_window"}


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
        user_glossary = load_glossary(Path(normalized_request.glossary_path) if normalized_request.glossary_path else None)
        glossary = merge_glossaries(
            user_glossary=user_glossary,
            built_in_glossary=built_in_dubbing_glossary(
                source_lang=normalized_request.source_lang,
                target_lang=normalized_request.target_lang,
            ),
        )
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
    raise TranslipError(f"Unsupported translation backend: {request.backend}")


def _validate_request(request: TranslationRequest) -> TranslationRequest:
    normalized = request.normalized()
    if not Path(normalized.segments_path).exists():
        raise TranslipError(f"Segments file does not exist: {normalized.segments_path}")
    if not Path(normalized.profiles_path).exists():
        raise TranslipError(f"Profiles file does not exist: {normalized.profiles_path}")
    if normalized.glossary_path is not None and not Path(normalized.glossary_path).exists():
        raise TranslipError(f"Glossary file does not exist: {normalized.glossary_path}")
    if normalized.batch_size <= 0:
        raise TranslipError("batch_size must be greater than 0")
    return normalized


def _resolved_source_language(*, requested: str, payload: dict[str, object]) -> str:
    canonical_requested = canonical_language_code(requested or "")
    if canonical_requested and canonical_requested != "auto":
        return canonical_requested
    segments = payload.get("segments", [])
    if isinstance(segments, list):
        for segment in segments:
            if not isinstance(segment, dict):
                continue
            language = canonical_language_code(str(segment.get("language") or ""))
            if language and language != "auto":
                return language
        for segment in segments:
            if not isinstance(segment, dict):
                continue
            detected = _detect_source_language(str(segment.get("text") or ""))
            if detected:
                return detected
    return "zh"


def _detect_source_language(text: str) -> str | None:
    if re.search(r"[\u3040-\u30ff]", text):
        return "ja"
    if re.search(r"[\u3400-\u9fff]", text):
        return "zh"
    if re.search(r"[A-Za-z]", text):
        return "en"
    return None


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
            script_decision = polish_dubbing_script(
                source_text=segment.text,
                target_text=target_text,
                source_lang=request.source_lang,
                target_lang=request.target_lang,
                source_duration_sec=segment.duration,
                glossary_matches=glossary_matches,
            )
            target_text = script_decision.target_text
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
                "original_target_text": target_text,
                "dubbing_text": script_decision.dubbing_text,
                "script_status": script_decision.script_status,
                "script_risk_flags": script_decision.risk_flags,
                "script_notes": script_decision.notes,
                "condense_status": "skipped",
                "condense_method": "none",
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
                        "dubbing_text": row["dubbing_text"],
                        "script_status": row["script_status"],
                        "script_risk_flags": row["script_risk_flags"],
                        "qa_flags": row["qa_flags"],
                        "fit_level": row["duration_budget"]["fit_level"],
                    }
                    for row in unit_segment_rows
                ],
            }
        )

    _apply_condensation(
        segment_rows=segment_rows,
        editable_units=editable_units,
        request=request,
        backend=backend,
    )
    return segment_rows, editable_units, glossary_match_count


def _apply_condensation(
    *,
    segment_rows: list[dict[str, object]],
    editable_units: list[dict[str, object]],
    request: TranslationRequest,
    backend: object,
) -> None:
    mode = request.condense_mode
    if mode not in _CONDENSE_LEVELS:
        return

    target_levels = _CONDENSE_LEVELS[mode]
    candidates: list[tuple[dict[str, object], CondenseInput]] = []
    for row in segment_rows:
        fit_level = str(row["duration_budget"].get("fit_level"))
        if fit_level not in target_levels:
            continue
        target_text = str(row["target_text"]).strip()
        if not target_text:
            continue
        source_dur = float(row.get("duration") or 0.0)
        estimated = float(row["duration_budget"].get("estimated_tts_duration_sec") or 0.0)
        max_chars = max(8, int(len(target_text) * (source_dur / max(estimated, 0.001))))
        protected_terms = [
            str(match.get("target") or match.get("source") or "")
            for match in row.get("glossary_matches", [])
            if isinstance(match, dict)
        ]
        protected_terms = [term for term in protected_terms if term]
        candidates.append(
            (
                row,
                CondenseInput(
                    segment_id=str(row["segment_id"]),
                    source_text=str(row.get("source_text") or ""),
                    current_target_text=target_text,
                    target_duration_sec=source_dur,
                    current_estimated_sec=estimated,
                    max_chars=max_chars,
                    protected_terms=protected_terms,
                ),
            )
        )

    if not candidates:
        return

    row_updates: dict[str, tuple[str, str, str]] = {}
    applied_segment_ids: set[str] = set()

    if getattr(backend, "supports_condensation", False):
        try:
            outputs = backend.condense_batch(
                items=[item for _, item in candidates],
                target_lang=request.target_lang,
            )
        except Exception as exc:  # pragma: no cover - network dependent
            logger.warning("Condense batch failed: %s; trying local rule-based fallback.", exc)
        else:
            output_by_id = {str(output.segment_id): str(output.target_text).strip() for output in outputs}
            for row, inp in candidates:
                seg_id = str(row["segment_id"])
                update = _apply_condensed_text(
                    row=row,
                    inp=inp,
                    new_text=output_by_id.get(seg_id, ""),
                    request=request,
                    method="backend",
                    reason="backend_condense",
                )
                if update is None:
                    continue
                row_updates[seg_id] = update
                applied_segment_ids.add(seg_id)
    else:
        logger.info(
            "Condense mode '%s' requested but backend %r does not support condensation; using local rule-based fallback.",
            mode,
            getattr(backend, "backend_name", type(backend).__name__),
        )

    for row, inp in candidates:
        seg_id = str(row["segment_id"])
        if seg_id in applied_segment_ids:
            continue
        fallback = _rule_based_condense_text(row=row, inp=inp, request=request)
        if fallback is None:
            row["condense_status"] = "condense_failed"
            row["condense_method"] = "none"
            continue
        new_text, reason = fallback
        update = _apply_condensed_text(
            row=row,
            inp=inp,
            new_text=new_text,
            request=request,
            method="rule_based",
            reason=reason,
        )
        if update is None:
            continue
        row_updates[seg_id] = update
        applied_segment_ids.add(seg_id)

    if not row_updates:
        return

    for unit in editable_units:
        unit_seg_rows = unit.get("segments", [])
        if not isinstance(unit_seg_rows, list):
            continue
        changed = False
        for seg in unit_seg_rows:
            if not isinstance(seg, dict):
                continue
            seg_id = str(seg.get("segment_id") or "")
            if seg_id in row_updates:
                new_text, status, method = row_updates[seg_id]
                source_row = next((row for row in segment_rows if str(row["segment_id"]) == seg_id), None)
                seg["draft_text"] = new_text
                if source_row is not None:
                    seg["dubbing_text"] = source_row.get("dubbing_text")
                    seg["script_status"] = source_row.get("script_status")
                    seg["script_risk_flags"] = source_row.get("script_risk_flags")
                seg["condense_status"] = status
                seg["condense_method"] = method
                changed = True
        if changed:
            rebuilt = [
                next((row for row in segment_rows if str(row["segment_id"]) == str(seg.get("segment_id"))), None)
                for seg in unit_seg_rows
                if isinstance(seg, dict)
            ]
            kept = [row for row in rebuilt if row is not None]
            if kept:
                unit["draft_text"] = " ".join(str(row["target_text"]) for row in kept).strip()
                unit["duration_summary"] = summarize_duration_budgets(
                    [row["duration_budget"] for row in kept]
                )


def _apply_condensed_text(
    *,
    row: dict[str, object],
    inp: CondenseInput,
    new_text: str,
    request: TranslationRequest,
    method: str,
    reason: str,
) -> tuple[str, str, str] | None:
    condensed = new_text.strip()
    if not condensed:
        row["condense_status"] = "condense_failed"
        return None
    if _missing_protected_terms(condensed, inp.protected_terms):
        row["condense_status"] = "condense_failed"
        return None

    normalized = normalize_target_with_glossary(
        source_text=str(row.get("source_text") or ""),
        target_text=condensed,
        glossary_matches=list(row.get("glossary_matches", [])),
    )
    script_decision = polish_dubbing_script(
        source_text=str(row.get("source_text") or ""),
        target_text=normalized,
        source_lang=request.source_lang,
        target_lang=request.target_lang,
        source_duration_sec=float(row.get("duration") or 0.0),
        glossary_matches=list(row.get("glossary_matches", [])),
    )
    normalized = script_decision.target_text
    original_estimated = float(row["duration_budget"].get("estimated_tts_duration_sec") or 0.0)
    new_estimated = estimate_tts_duration(normalized, target_lang=request.target_lang)
    if new_estimated >= original_estimated:
        row["condense_status"] = "condense_failed"
        return None

    row["target_text"] = normalized
    row["dubbing_text"] = script_decision.dubbing_text
    row["script_status"] = script_decision.script_status
    row["script_risk_flags"] = script_decision.risk_flags
    row["script_notes"] = script_decision.notes
    row["duration_budget"] = build_duration_budget(
        source_duration_sec=float(row.get("duration") or 0.0),
        target_text=str(row["target_text"]),
        target_lang=request.target_lang,
    )
    row["qa_flags"] = build_qa_flags(
        source_text=str(row.get("source_text") or ""),
        target_text=str(row["target_text"]),
        glossary_matches=list(row.get("glossary_matches", [])),
        duration_budget=row["duration_budget"],
    )
    if "condensed" not in row["qa_flags"]:
        row["qa_flags"].append("condensed")
    fit_level = str(row["duration_budget"].get("fit_level"))
    row["condense_status"] = "condensed" if fit_level != "risky" else "still_risky"
    row["condense_method"] = method
    row["condense_reason"] = reason
    return str(row["target_text"]), row["condense_status"], method


def _rule_based_condense_text(
    *,
    row: dict[str, object],
    inp: CondenseInput,
    request: TranslationRequest,
) -> tuple[str, str] | None:
    if canonical_language_code(request.target_lang) != "en":
        return None

    from ..repair.rewrite import rewrite_for_dubbing

    glossary = _glossary_entries_from_matches(
        list(row.get("glossary_matches", [])),
        target_lang=request.target_lang,
    )
    candidates = rewrite_for_dubbing(
        segment_id=str(row.get("segment_id") or inp.segment_id),
        source_text=inp.source_text,
        current_target_text=inp.current_target_text,
        source_duration_sec=inp.target_duration_sec,
        target_lang=request.target_lang,
        glossary=glossary,
    )
    scored: list[tuple[int, float, str, str]] = []
    for candidate in candidates:
        if candidate.reason in _UNSAFE_RULE_BASED_CONDENSE_REASONS:
            continue
        text = normalize_target_with_glossary(
            source_text=inp.source_text,
            target_text=candidate.target_text,
            glossary_matches=list(row.get("glossary_matches", [])),
        )
        if not text or _missing_protected_terms(text, inp.protected_terms):
            continue
        estimated = estimate_tts_duration(text, target_lang=request.target_lang)
        if estimated >= inp.current_estimated_sec:
            continue
        budget = build_duration_budget(
            source_duration_sec=inp.target_duration_sec,
            target_text=text,
            target_lang=request.target_lang,
        )
        fit_level = str(budget.get("fit_level"))
        fit_rank = {"fit": 0, "review": 1, "risky": 2}.get(fit_level, 3)
        scored.append((fit_rank, estimated, text, candidate.reason))
    if not scored:
        return None

    scored.sort(key=lambda item: (item[0], -item[1] if item[0] == 0 else item[1]))
    _, _, text, reason = scored[0]
    return text, reason


def _glossary_entries_from_matches(
    matches: list[object],
    *,
    target_lang: str,
) -> list[GlossaryEntry]:
    entries: list[GlossaryEntry] = []
    canonical = canonical_language_code(target_lang)
    for index, match in enumerate(matches, start=1):
        if not isinstance(match, dict):
            continue
        source = str(match.get("matched_text") or "").strip()
        target = str(match.get("replacement_text") or "").strip()
        if not source or not target:
            continue
        entries.append(
            GlossaryEntry(
                entry_id=str(match.get("entry_id") or f"match-{index:04d}"),
                source_variants=(source,),
                targets={target_lang: target, canonical: target},
                normalized_source=source,
            )
        )
    return entries


def _missing_protected_terms(text: str, terms: list[str]) -> bool:
    lowered = text.lower()
    for term in terms:
        cleaned = term.strip()
        if not cleaned:
            continue
        if cleaned.lower() not in lowered:
            return True
    return False
