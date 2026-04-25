from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from ..exceptions import TranslipError
from ..types import RenderDubArtifacts, RenderDubRequest, RenderDubResult
from ..utils.ffmpeg import export_audio, render_wav
from ..utils.files import ensure_directory, remove_tree, work_directory
from .audio import (
    apply_fade,
    audio_duration_sec,
    build_sidechain_preview_mix,
    compress_audio,
    db_to_gain,
    peak_limit,
    prepare_audio_for_mix,
    write_wav,
)
from .export import (
    build_mix_report,
    build_render_manifest,
    build_timeline_payload,
    now_iso,
    write_json,
)

logger = logging.getLogger(__name__)
OVERLAP_TOLERANCE_SEC = 0.05
OVERFLOW_MAX_SPILL_RATIO = 1.3
SHORT_SEGMENT_COMPRESS_MAX_SOURCE_SEC = 1.5
SHORT_SEGMENT_COMPRESS_MAX_OVERFLOW_SEC = 0.75
SHORT_SEGMENT_COMPRESS_MAX_RATIO = 1.75
MIN_SUBTITLE_COVERAGE_RATIO = 0.50


@dataclass(slots=True)
class TimelineItem:
    segment_id: str
    speaker_id: str
    target_lang: str
    target_text: str
    anchor_start: float
    anchor_end: float
    source_duration_sec: float
    anchor_source: str
    generated_duration_sec: float
    audio_path: Path
    task_d_status: str
    duration_status: str
    speaker_status: str
    intelligibility_status: str
    speaker_similarity: float | None
    text_similarity: float | None
    overall_status: str
    task_d_report_path: Path
    qa_flags: list[str] = field(default_factory=list)
    fit_strategy: str = "pending"
    placement_start: float | None = None
    placement_end: float | None = None
    fitted_audio_path: Path | None = None
    fitted_duration_sec: float | None = None
    mix_status: str = "pending"
    quality_score: float = 0.0
    notes: list[str] = field(default_factory=list)
    subtitle_start: float | None = None
    subtitle_end: float | None = None
    subtitle_coverage_ratio: float | None = None
    dubbing_window_policy: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "speaker_id": self.speaker_id,
            "target_lang": self.target_lang,
            "target_text": self.target_text,
            "anchor_start": round(self.anchor_start, 3),
            "anchor_end": round(self.anchor_end, 3),
            "anchor_source": self.anchor_source,
            "source_duration_sec": round(self.source_duration_sec, 3),
            "generated_duration_sec": round(self.generated_duration_sec, 3),
            "fitted_duration_sec": round(self.fitted_duration_sec, 3) if self.fitted_duration_sec is not None else None,
            "fit_strategy": self.fit_strategy,
            "placement_start": round(self.placement_start, 3) if self.placement_start is not None else None,
            "placement_end": round(self.placement_end, 3) if self.placement_end is not None else None,
            "task_d_status": self.task_d_status,
            "duration_status": self.duration_status,
            "speaker_status": self.speaker_status,
            "intelligibility_status": self.intelligibility_status,
            "speaker_similarity": round(self.speaker_similarity, 4) if self.speaker_similarity is not None else None,
            "text_similarity": round(self.text_similarity, 4) if self.text_similarity is not None else None,
            "overall_status": self.overall_status,
            "mix_status": self.mix_status,
            "audio_path": str(self.audio_path),
            "fitted_audio_path": str(self.fitted_audio_path) if self.fitted_audio_path else None,
            "task_d_report_path": str(self.task_d_report_path),
            "qa_flags": self.qa_flags,
            "quality_score": round(self.quality_score, 4),
            "notes": self.notes,
            "subtitle_window": (
                {
                    "start": round(self.subtitle_start, 3),
                    "end": round(self.subtitle_end, 3),
                    "duration": round(max(0.0, self.subtitle_end - self.subtitle_start), 3),
                }
                if self.subtitle_start is not None and self.subtitle_end is not None
                else None
            ),
            "subtitle_coverage_ratio": (
                round(self.subtitle_coverage_ratio, 4)
                if self.subtitle_coverage_ratio is not None
                else None
            ),
            "dubbing_window_policy": self.dubbing_window_policy,
        }


def render_dub(request: RenderDubRequest) -> RenderDubResult:
    normalized_request = _validate_request(request)
    target_lang = normalized_request.target_lang
    bundle_dir = ensure_directory(
        Path(normalized_request.output_dir) / Path(normalized_request.translation_path).parent.name
    )
    work_dir = work_directory(Path(normalized_request.output_dir))
    timeline_path = bundle_dir / f"timeline.{target_lang}.json"
    mix_report_path = bundle_dir / f"mix_report.{target_lang}.json"
    dub_voice_path = bundle_dir / f"dub_voice.{target_lang}.wav"
    preview_mix_wav_path = bundle_dir / f"preview_mix.{target_lang}.wav"
    manifest_path = bundle_dir / "task-e-manifest.json"

    started_at = now_iso()
    started_monotonic = time.monotonic()

    try:
        segments_payload = _load_json(Path(normalized_request.segments_path))
        translation_payload = _load_json(Path(normalized_request.translation_path))
        report_payloads = [
            (report_path, _load_json(report_path))
            for report_path in normalized_request.task_d_report_paths
        ]
        selected_payload = (
            _load_json(Path(normalized_request.selected_segments_path))
            if normalized_request.selected_segments_path is not None
            else None
        )
        target_lang = str(translation_payload.get("backend", {}).get("target_lang") or normalized_request.target_lang)

        background_wav_path = render_wav(
            Path(normalized_request.background_path),
            work_dir / "background.wav",
            sample_rate=normalized_request.output_sample_rate,
        )
        background_waveform = prepare_audio_for_mix(background_wav_path, target_sample_rate=normalized_request.output_sample_rate)
        total_duration_sec = len(background_waveform) / normalized_request.output_sample_rate

        candidates, skipped_items = _load_candidates(
            request=normalized_request,
            segments_payload=segments_payload,
            translation_payload=translation_payload,
            report_payloads=report_payloads,
            selected_payload=selected_payload,
        )
        planned_items, skipped_fit = _apply_fit_strategy(
            request=normalized_request,
            items=candidates,
            work_dir=work_dir,
        )
        skipped_items.extend(skipped_fit)
        placed_items, skipped_overlap = _resolve_overlaps(planned_items)
        skipped_items.extend(skipped_overlap)
        for item in [*placed_items, *skipped_items]:
            _apply_subtitle_coverage(item)

        timeline_payload = build_timeline_payload(
            request=normalized_request,
            target_lang=target_lang,
            items=[item.to_payload() for item in sorted(placed_items + skipped_items, key=_timeline_sort_key)],
        )
        write_json(timeline_payload, timeline_path)

        dub_waveform = _render_dub_voice(
            items=placed_items,
            total_duration_sec=total_duration_sec,
            output_sample_rate=normalized_request.output_sample_rate,
        )
        write_wav(dub_voice_path, dub_waveform, sample_rate=normalized_request.output_sample_rate)

        preview_mix_extra_path = _render_preview_mix(
            request=normalized_request,
            dub_voice_path=dub_voice_path,
            dub_waveform=dub_waveform,
            background_wav_path=background_wav_path,
            background_waveform=background_waveform,
            placed_items=placed_items,
            preview_mix_wav_path=preview_mix_wav_path,
        )

        mix_report = build_mix_report(
            request=normalized_request,
            target_lang=target_lang,
            placed_items=[item.to_payload() for item in sorted(placed_items, key=_timeline_sort_key)],
            skipped_items=[item.to_payload() for item in sorted(skipped_items, key=_timeline_sort_key)],
            total_duration_sec=total_duration_sec,
        )
        write_json(mix_report, mix_report_path)

        manifest = build_render_manifest(
            request=normalized_request,
            target_lang=target_lang,
            dub_voice_path=dub_voice_path,
            preview_mix_wav_path=preview_mix_wav_path,
            preview_mix_extra_path=preview_mix_extra_path,
            timeline_path=timeline_path,
            mix_report_path=mix_report_path,
            started_at=started_at,
            finished_at=now_iso(),
            elapsed_sec=time.monotonic() - started_monotonic,
            placed_count=len(placed_items),
            skipped_count=len(skipped_items),
        )
        manifest["resolved"]["content_status"] = mix_report["stats"]["content_quality"]["status"]
        manifest["resolved"]["content_quality_reasons"] = mix_report["stats"]["content_quality"]["reasons"]
        write_json(manifest, manifest_path)
        remove_tree(work_dir)
        return RenderDubResult(
            request=normalized_request,
            artifacts=RenderDubArtifacts(
                bundle_dir=bundle_dir,
                dub_voice_path=dub_voice_path,
                preview_mix_wav_path=preview_mix_wav_path,
                timeline_path=timeline_path,
                mix_report_path=mix_report_path,
                manifest_path=manifest_path,
                preview_mix_extra_path=preview_mix_extra_path,
            ),
            manifest=manifest,
            work_dir=work_dir,
        )
    except Exception as exc:
        logger.exception("Task E dub render failed.")
        ensure_directory(bundle_dir)
        manifest = build_render_manifest(
            request=normalized_request,
            target_lang=target_lang,
            dub_voice_path=dub_voice_path,
            preview_mix_wav_path=preview_mix_wav_path,
            preview_mix_extra_path=None,
            timeline_path=timeline_path,
            mix_report_path=mix_report_path,
            started_at=started_at,
            finished_at=now_iso(),
            elapsed_sec=time.monotonic() - started_monotonic,
            placed_count=0,
            skipped_count=0,
            error=str(exc),
        )
        write_json(manifest, manifest_path)
        raise


def _validate_request(request: RenderDubRequest) -> RenderDubRequest:
    normalized = request.normalized()
    for path in [
        Path(normalized.background_path),
        Path(normalized.segments_path),
        Path(normalized.translation_path),
    ]:
        if not path.exists():
            raise TranslipError(f"Task E input path does not exist: {path}")
    if not normalized.task_d_report_paths:
        raise TranslipError("task_d_report_paths must contain at least one report")
    for report_path in normalized.task_d_report_paths:
        if not Path(report_path).exists():
            raise TranslipError(f"Task D report does not exist: {report_path}")
    if normalized.selected_segments_path is not None and not Path(normalized.selected_segments_path).exists():
        raise TranslipError(f"Selected segments file does not exist: {normalized.selected_segments_path}")
    if normalized.output_sample_rate <= 0:
        raise TranslipError("output_sample_rate must be greater than 0")
    if normalized.max_compress_ratio < 1.0:
        raise TranslipError("max_compress_ratio must be >= 1.0")
    return normalized


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_candidates(
    *,
    request: RenderDubRequest,
    segments_payload: dict[str, Any],
    translation_payload: dict[str, Any],
    report_payloads: list[tuple[Path, dict[str, Any]]],
    selected_payload: dict[str, Any] | None = None,
) -> tuple[list[TimelineItem], list[TimelineItem]]:
    anchor_map = {
        str(row.get("segment_id") or row.get("id")): row
        for row in segments_payload.get("segments", [])
        if isinstance(row, dict) and (row.get("segment_id") or row.get("id"))
    }
    translation_map = {
        str(row.get("segment_id")): row
        for row in translation_payload.get("segments", [])
        if isinstance(row, dict) and row.get("segment_id")
    }
    candidates: list[TimelineItem] = []
    skipped: list[TimelineItem] = []
    seen_segment_ids: set[str] = set()
    selected_map = _selected_segment_map(selected_payload)

    for report_path, payload in report_payloads:
        for row in payload.get("segments", []):
            if not isinstance(row, dict):
                continue
            segment_id = str(row.get("segment_id") or "")
            if not segment_id or segment_id in seen_segment_ids:
                continue
            anchor = anchor_map.get(segment_id)
            translation = translation_map.get(segment_id)
            selected = selected_map.get(segment_id)
            if not segment_id or anchor is None or translation is None:
                skipped.append(
                    TimelineItem(
                        segment_id=segment_id or "unknown",
                        speaker_id=str(row.get("speaker_id") or ""),
                        target_lang=request.target_lang,
                        target_text=str(row.get("target_text") or ""),
                        anchor_start=float(row.get("index") or 0.0),
                        anchor_end=float(row.get("index") or 0.0),
                        source_duration_sec=float(row.get("source_duration_sec") or 0.0),
                        anchor_source="missing_anchor",
                        generated_duration_sec=float(row.get("generated_duration_sec") or 0.0),
                        audio_path=Path(str(row.get("audio_path") or report_path)),
                        task_d_status=str(row.get("overall_status") or "failed"),
                        duration_status=str(row.get("duration_status") or "unknown"),
                        speaker_status=str(row.get("speaker_status") or "unknown"),
                        intelligibility_status=str(row.get("intelligibility_status") or "unknown"),
                        speaker_similarity=_float_or_none(row.get("speaker_similarity")),
                        text_similarity=_float_or_none(row.get("text_similarity")),
                        overall_status=str(row.get("overall_status") or "failed"),
                        task_d_report_path=report_path,
                        mix_status="skipped_missing_upstream",
                        notes=["missing_anchor_or_translation"],
                    )
                )
                continue

            row_for_mix = _apply_selected_override(row=row, selected=selected)
            timing = _resolve_anchor_timing(
                anchor=anchor,
                fallback_source_duration=float(
                    row_for_mix.get("source_duration_sec")
                    or row.get("source_duration_sec")
                    or 0.0
                ),
            )
            item = TimelineItem(
                segment_id=segment_id,
                speaker_id=str(row_for_mix.get("speaker_id") or row.get("speaker_id") or translation.get("speaker_id") or ""),
                target_lang=str(payload.get("backend", {}).get("target_lang") or request.target_lang),
                target_text=str(row_for_mix.get("target_text") or translation.get("target_text") or row.get("target_text") or ""),
                anchor_start=timing["anchor_start"],
                anchor_end=timing["anchor_end"],
                source_duration_sec=timing["source_duration_sec"],
                anchor_source=timing["anchor_source"],
                generated_duration_sec=float(row_for_mix.get("generated_duration_sec") or row.get("generated_duration_sec") or 0.0),
                audio_path=Path(str(row_for_mix.get("audio_path") or row.get("audio_path"))).expanduser().resolve(),
                task_d_status=str(row_for_mix.get("overall_status") or row.get("overall_status") or "failed"),
                duration_status=str(row_for_mix.get("duration_status") or row.get("duration_status") or "unknown"),
                speaker_status=str(row_for_mix.get("speaker_status") or row.get("speaker_status") or "unknown"),
                intelligibility_status=str(
                    row_for_mix.get("intelligibility_status") or row.get("intelligibility_status") or "unknown"
                ),
                speaker_similarity=_float_or_none(row_for_mix.get("speaker_similarity")),
                text_similarity=_float_or_none(row_for_mix.get("text_similarity")),
                overall_status=str(row_for_mix.get("overall_status") or row.get("overall_status") or "failed"),
                task_d_report_path=report_path,
                qa_flags=[str(flag) for flag in translation.get("qa_flags", [])],
                subtitle_start=timing["subtitle_start"],
                subtitle_end=timing["subtitle_end"],
                dubbing_window_policy=timing["dubbing_window_policy"],
            )
            if item.anchor_source == "dubbing_window" and item.dubbing_window_policy:
                item.notes.append(f"dubbing_window:{item.dubbing_window_policy}")
            if selected is not None:
                item.notes.append(f"selected_repair_attempt:{selected.get('selected_attempt_id')}")
            if not item.audio_path.exists():
                item.mix_status = "skipped_missing_audio"
                item.notes.append("missing_task_d_audio")
                skipped.append(item)
                continue
            if request.quality_gate == "strict" and item.overall_status == "failed":
                item.mix_status = "skipped_quality_gate"
                item.notes.append("strict_quality_gate_failed")
                skipped.append(item)
                seen_segment_ids.add(segment_id)
                continue
            if item.overall_status == "failed":
                item.notes.append("task_d_failed_upstream")
            item.quality_score = _quality_score(item)
            seen_segment_ids.add(segment_id)
            candidates.append(item)

    candidates.sort(key=_timeline_sort_key)
    skipped.sort(key=_timeline_sort_key)
    return candidates, skipped


def _resolve_anchor_timing(*, anchor: dict[str, Any], fallback_source_duration: float) -> dict[str, Any]:
    asr_start = _float_value(anchor.get("start"), default=0.0)
    asr_end = _float_value(anchor.get("end"), default=asr_start)
    if asr_end < asr_start:
        asr_start, asr_end = asr_end, asr_start

    timing = anchor.get("timing") if isinstance(anchor.get("timing"), dict) else {}
    dubbing_window = _window_from_mapping(timing.get("dubbing_window") if isinstance(timing, dict) else None)
    subtitle_window = _window_from_mapping(timing.get("subtitle_window") if isinstance(timing, dict) else None)
    if subtitle_window is None and isinstance(timing, dict):
        subtitle_window = _window_from_mapping(timing.get("ocr_window"))

    if dubbing_window is not None:
        anchor_start, anchor_end = dubbing_window
        anchor_source = "dubbing_window"
    else:
        anchor_start, anchor_end = asr_start, asr_end
        anchor_source = "asr_window"

    source_duration = max(0.0, anchor_end - anchor_start)
    if source_duration <= 0:
        source_duration = _float_value(anchor.get("duration"), default=fallback_source_duration)

    return {
        "anchor_start": anchor_start,
        "anchor_end": anchor_end,
        "source_duration_sec": source_duration,
        "anchor_source": anchor_source,
        "subtitle_start": subtitle_window[0] if subtitle_window is not None else None,
        "subtitle_end": subtitle_window[1] if subtitle_window is not None else None,
        "dubbing_window_policy": (
            str(timing.get("dubbing_window", {}).get("policy"))
            if isinstance(timing, dict) and isinstance(timing.get("dubbing_window"), dict)
            and timing.get("dubbing_window", {}).get("policy")
            else None
        ),
    }


def _window_from_mapping(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, dict) or value.get("start") is None or value.get("end") is None:
        return None
    start = _float_value(value.get("start"), default=0.0)
    end = _float_value(value.get("end"), default=start)
    if end < start:
        start, end = end, start
    if end <= start:
        return None
    return start, end


def _float_value(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _selected_segment_map(selected_payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not selected_payload:
        return {}
    return {
        str(row.get("segment_id") or ""): row
        for row in selected_payload.get("segments", [])
        if isinstance(row, dict) and row.get("segment_id") and row.get("selected_audio_path")
    }


def _apply_selected_override(*, row: dict[str, Any], selected: dict[str, Any] | None) -> dict[str, Any]:
    if selected is None:
        return row
    return {
        **row,
        "speaker_id": selected.get("speaker_id") or row.get("speaker_id"),
        "target_text": selected.get("target_text") or row.get("target_text"),
        "generated_duration_sec": selected.get("generated_duration_sec") or row.get("generated_duration_sec"),
        "duration_ratio": selected.get("duration_ratio") or row.get("duration_ratio"),
        "duration_status": selected.get("duration_status") or row.get("duration_status"),
        "speaker_similarity": selected.get("speaker_similarity"),
        "speaker_status": selected.get("speaker_status") or row.get("speaker_status"),
        "text_similarity": selected.get("text_similarity"),
        "intelligibility_status": selected.get("intelligibility_status") or row.get("intelligibility_status"),
        "overall_status": selected.get("overall_status") or row.get("overall_status"),
        "audio_path": selected.get("selected_audio_path") or row.get("audio_path"),
    }


def _apply_fit_strategy(
    *,
    request: RenderDubRequest,
    items: list[TimelineItem],
    work_dir: Path,
) -> tuple[list[TimelineItem], list[TimelineItem]]:
    planned: list[TimelineItem] = []
    skipped: list[TimelineItem] = []
    fit_dir = ensure_directory(work_dir / "fit")

    for item in items:
        strategy = _fit_strategy_for_item(item=item, request=request)
        item.fit_strategy = strategy
        if strategy == "invalid_duration":
            item.mix_status = "skipped_fit"
            item.notes.append("fit_strategy_invalid_duration")
            skipped.append(item)
            continue
        if strategy == "compress":
            tempo = max(item.generated_duration_sec / max(item.source_duration_sec, 1e-6), 1.0)
            fitted_path = compress_audio(
                input_path=item.audio_path,
                output_path=fit_dir / f"{item.segment_id}.wav",
                tempo=tempo,
                backend=request.fit_backend,
                output_sample_rate=request.output_sample_rate,
            )
        elif strategy == "overflow_unfitted":
            tempo = request.max_compress_ratio
            fitted_path = compress_audio(
                input_path=item.audio_path,
                output_path=fit_dir / f"{item.segment_id}.wav",
                tempo=tempo,
                backend=request.fit_backend,
                output_sample_rate=request.output_sample_rate,
            )
            max_dur = item.source_duration_sec * OVERFLOW_MAX_SPILL_RATIO
            actual_dur = audio_duration_sec(fitted_path)
            if actual_dur > max_dur:
                _trim_audio_inplace(fitted_path, max_dur, request.output_sample_rate)
                item.notes.append("overflow_trimmed")
            else:
                item.notes.append("overflow_compressed")
        else:
            fitted_path = compress_audio(
                input_path=item.audio_path,
                output_path=fit_dir / f"{item.segment_id}.wav",
                tempo=1.0,
                backend="atempo",
                output_sample_rate=request.output_sample_rate,
            )
        if strategy == "underflow_unfitted":
            item.notes.append("fit_underflow_passthrough")
        item.fitted_audio_path = fitted_path
        item.fitted_duration_sec = audio_duration_sec(fitted_path)
        item.placement_start = item.anchor_start
        item.placement_end = item.anchor_start + float(item.fitted_duration_sec)
        planned.append(item)

    return planned, skipped


def _fit_strategy_for_item(*, item: TimelineItem, request: RenderDubRequest) -> str:
    if item.source_duration_sec <= 0 or item.generated_duration_sec <= 0:
        return "invalid_duration"
    ratio = item.generated_duration_sec / item.source_duration_sec
    overflow_sec = item.generated_duration_sec - item.source_duration_sec
    direct_upper = 1.0 if request.fit_policy == "conservative" else 1.05
    pad_lower = 0.60 if request.fit_policy == "conservative" else 0.55
    if 0.85 <= ratio <= direct_upper:
        return "direct"
    if direct_upper < ratio <= request.max_compress_ratio:
        return "compress"
    if (
        request.fit_policy == "conservative"
        and item.source_duration_sec <= SHORT_SEGMENT_COMPRESS_MAX_SOURCE_SEC
        and 0.0 < overflow_sec <= SHORT_SEGMENT_COMPRESS_MAX_OVERFLOW_SEC
        and ratio <= SHORT_SEGMENT_COMPRESS_MAX_RATIO
    ):
        return "compress"
    if pad_lower <= ratio < 0.85:
        return "pad"
    if ratio > request.max_compress_ratio:
        return "overflow_unfitted"
    return "underflow_unfitted"


def _apply_subtitle_coverage(item: TimelineItem) -> None:
    if item.subtitle_start is None or item.subtitle_end is None:
        item.subtitle_coverage_ratio = None
        return

    subtitle_duration = max(0.001, item.subtitle_end - item.subtitle_start)
    if item.mix_status != "placed":
        coverage_ratio = 0.0
        if "subtitle_window_not_rendered" not in item.notes:
            item.notes.append("subtitle_window_not_rendered")
    elif item.placement_start is None or item.placement_end is None:
        coverage_ratio = 0.0
    else:
        overlap = max(0.0, min(item.subtitle_end, item.placement_end) - max(item.subtitle_start, item.placement_start))
        coverage_ratio = min(1.0, overlap / subtitle_duration)

    item.subtitle_coverage_ratio = round(coverage_ratio, 4)
    if coverage_ratio <= 0.0:
        if "subtitle_window_not_covered" not in item.notes:
            item.notes.append("subtitle_window_not_covered")
    elif coverage_ratio < MIN_SUBTITLE_COVERAGE_RATIO:
        if "subtitle_window_low_coverage" not in item.notes:
            item.notes.append("subtitle_window_low_coverage")


def _resolve_overlaps(items: list[TimelineItem]) -> tuple[list[TimelineItem], list[TimelineItem]]:
    placed: list[TimelineItem] = []
    skipped: list[TimelineItem] = []
    for item in sorted(items, key=_timeline_sort_key):
        conflicts = [
            existing for existing in placed
            if _interval_overlap(item.placement_start, item.placement_end, existing.placement_start, existing.placement_end)
        ]
        if not conflicts:
            item.mix_status = "placed"
            placed.append(item)
            continue
        if _try_trim_conflicts(item, conflicts):
            item.mix_status = "placed"
            placed.append(item)
            continue
        strongest = max(conflicts, key=lambda row: row.quality_score)
        if item.quality_score > strongest.quality_score + 0.05:
            for conflict in conflicts:
                placed.remove(conflict)
                conflict.mix_status = "skipped_overlap"
                conflict.notes.append(f"replaced_by:{item.segment_id}")
                skipped.append(conflict)
            item.mix_status = "placed"
            item.notes.append("overlap_replaced_previous")
            placed.append(item)
        else:
            item.mix_status = "skipped_overlap"
            item.notes.append(f"overlap_with:{strongest.segment_id}")
            skipped.append(item)
    placed.sort(key=_timeline_sort_key)
    skipped.sort(key=_timeline_sort_key)
    return placed, skipped


def _render_dub_voice(
    *,
    items: list[TimelineItem],
    total_duration_sec: float,
    output_sample_rate: int,
) -> np.ndarray:
    total_samples = max(1, int(round(total_duration_sec * output_sample_rate)))
    master = np.zeros(total_samples, dtype=np.float32)
    for item in items:
        if item.fitted_audio_path is None or item.placement_start is None:
            continue
        waveform = prepare_audio_for_mix(item.fitted_audio_path, target_sample_rate=output_sample_rate)
        waveform = apply_fade(waveform, sample_rate=output_sample_rate)
        start_idx = max(0, int(round(item.placement_start * output_sample_rate)))
        end_idx = min(total_samples, start_idx + waveform.size)
        if end_idx <= start_idx:
            item.mix_status = "skipped_out_of_range"
            item.notes.append("placement_out_of_range")
            continue
        master[start_idx:end_idx] += waveform[: end_idx - start_idx]
    return peak_limit(master)


def _render_preview_mix(
    *,
    request: RenderDubRequest,
    dub_voice_path: Path,
    dub_waveform: np.ndarray,
    background_wav_path: Path,
    background_waveform: np.ndarray,
    placed_items: list[TimelineItem],
    preview_mix_wav_path: Path,
) -> Path | None:
    if request.ducking_mode == "sidechain":
        build_sidechain_preview_mix(
            dub_voice_path=dub_voice_path,
            background_path=background_wav_path,
            output_path=preview_mix_wav_path,
            output_sample_rate=request.output_sample_rate,
            background_gain_db=request.background_gain_db,
            use_loudnorm=request.mix_profile == "enhanced",
        )
    else:
        preview_waveform = _render_static_preview_mix(
            request=request,
            dub_waveform=dub_waveform,
            background_waveform=background_waveform,
            placed_items=placed_items,
        )
        write_wav(preview_mix_wav_path, preview_waveform, sample_rate=request.output_sample_rate)

    if request.preview_format == "mp3":
        extra_path = preview_mix_wav_path.with_suffix(".mp3")
        export_audio(preview_mix_wav_path, extra_path, "mp3")
        return extra_path
    return None


def _render_static_preview_mix(
    *,
    request: RenderDubRequest,
    dub_waveform: np.ndarray,
    background_waveform: np.ndarray,
    placed_items: list[TimelineItem],
) -> np.ndarray:
    background = background_waveform.astype(np.float32).copy()
    background *= db_to_gain(request.background_gain_db)
    if request.ducking_mode == "static":
        duck_gain = db_to_gain(request.window_ducking_db)
        for item in placed_items:
            if item.placement_start is None or item.placement_end is None:
                continue
            start_idx = max(0, int(round(item.placement_start * request.output_sample_rate)))
            end_idx = min(background.size, int(round(item.placement_end * request.output_sample_rate)))
            if end_idx > start_idx:
                background[start_idx:end_idx] *= duck_gain
    preview = background + dub_waveform.astype(np.float32)
    if request.mix_profile == "enhanced":
        preview = peak_limit(preview, peak=0.9)
    return peak_limit(preview)


def _interval_overlap(start_a: float | None, end_a: float | None, start_b: float | None, end_b: float | None) -> bool:
    if start_a is None or end_a is None or start_b is None or end_b is None:
        return False
    overlap_sec = min(end_a, end_b) - max(start_a, start_b)
    return overlap_sec > OVERLAP_TOLERANCE_SEC


MAX_TRIM_FRACTION = 0.30


def _try_trim_conflicts(new_item: TimelineItem, conflicts: list[TimelineItem]) -> bool:
    if new_item.placement_start is None:
        return False
    for conflict in conflicts:
        if conflict.placement_end is None or conflict.fitted_duration_sec is None:
            return False
        trim_to = new_item.placement_start - OVERLAP_TOLERANCE_SEC
        if trim_to <= (conflict.placement_start or 0.0):
            return False
        original_dur = conflict.fitted_duration_sec
        new_dur = trim_to - (conflict.placement_start or 0.0)
        if new_dur <= 0 or (original_dur - new_dur) / original_dur > MAX_TRIM_FRACTION:
            return False
    for conflict in conflicts:
        trim_to = new_item.placement_start - OVERLAP_TOLERANCE_SEC
        conflict.placement_end = trim_to
        conflict.fitted_duration_sec = trim_to - (conflict.placement_start or 0.0)
        conflict.notes.append(f"tail_trimmed_for:{new_item.segment_id}")
    return True


def _quality_score(item: TimelineItem) -> float:
    status_weight = {"passed": 2.0, "review": 1.0}.get(item.overall_status, 0.0)
    speaker_score = max(0.0, float(item.speaker_similarity or 0.0))
    text_score = max(0.0, float(item.text_similarity or 0.0))
    duration_ratio = item.generated_duration_sec / item.source_duration_sec if item.source_duration_sec > 0 else 0.0
    duration_score = max(0.0, 1.0 - abs(1.0 - duration_ratio))
    return status_weight + text_score + (speaker_score * 0.5) + (duration_score * 0.25)


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _timeline_sort_key(item: TimelineItem) -> tuple[float, float, str]:
    return (float(item.anchor_start or 0.0), float(item.anchor_end or 0.0), item.segment_id)


def _trim_audio_inplace(path: Path, max_duration_sec: float, sample_rate: int) -> None:
    waveform = prepare_audio_for_mix(path, target_sample_rate=sample_rate)
    max_samples = int(round(max_duration_sec * sample_rate))
    if waveform.size <= max_samples:
        return
    trimmed = waveform[:max_samples]
    fade_samples = min(int(0.03 * sample_rate), max_samples // 4)
    if fade_samples > 0:
        ramp = np.linspace(1.0, 0.0, fade_samples, dtype=np.float32)
        trimmed[-fade_samples:] *= ramp
    write_wav(path, trimmed, sample_rate=sample_rate)


__all__ = ["render_dub"]
