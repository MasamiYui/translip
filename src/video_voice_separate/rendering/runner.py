from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from ..exceptions import VideoVoiceSeparateError
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


@dataclass(slots=True)
class TimelineItem:
    segment_id: str
    speaker_id: str
    target_lang: str
    target_text: str
    anchor_start: float
    anchor_end: float
    source_duration_sec: float
    generated_duration_sec: float
    audio_path: Path
    task_d_status: str
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

    def to_payload(self) -> dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "speaker_id": self.speaker_id,
            "target_lang": self.target_lang,
            "target_text": self.target_text,
            "anchor_start": round(self.anchor_start, 3),
            "anchor_end": round(self.anchor_end, 3),
            "source_duration_sec": round(self.source_duration_sec, 3),
            "generated_duration_sec": round(self.generated_duration_sec, 3),
            "fitted_duration_sec": round(self.fitted_duration_sec, 3) if self.fitted_duration_sec is not None else None,
            "fit_strategy": self.fit_strategy,
            "placement_start": round(self.placement_start, 3) if self.placement_start is not None else None,
            "placement_end": round(self.placement_end, 3) if self.placement_end is not None else None,
            "task_d_status": self.task_d_status,
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
        )
        planned_items, skipped_fit = _apply_fit_strategy(
            request=normalized_request,
            items=candidates,
            work_dir=work_dir,
        )
        skipped_items.extend(skipped_fit)
        placed_items, skipped_overlap = _resolve_overlaps(planned_items)
        skipped_items.extend(skipped_overlap)

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
            raise VideoVoiceSeparateError(f"Task E input path does not exist: {path}")
    if not normalized.task_d_report_paths:
        raise VideoVoiceSeparateError("task_d_report_paths must contain at least one report")
    for report_path in normalized.task_d_report_paths:
        if not Path(report_path).exists():
            raise VideoVoiceSeparateError(f"Task D report does not exist: {report_path}")
    if normalized.output_sample_rate <= 0:
        raise VideoVoiceSeparateError("output_sample_rate must be greater than 0")
    if normalized.max_compress_ratio < 1.0:
        raise VideoVoiceSeparateError("max_compress_ratio must be >= 1.0")
    return normalized


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_candidates(
    *,
    request: RenderDubRequest,
    segments_payload: dict[str, Any],
    translation_payload: dict[str, Any],
    report_payloads: list[tuple[Path, dict[str, Any]]],
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

    for report_path, payload in report_payloads:
        for row in payload.get("segments", []):
            if not isinstance(row, dict):
                continue
            segment_id = str(row.get("segment_id") or "")
            if not segment_id or segment_id in seen_segment_ids:
                continue
            anchor = anchor_map.get(segment_id)
            translation = translation_map.get(segment_id)
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
                        generated_duration_sec=float(row.get("generated_duration_sec") or 0.0),
                        audio_path=Path(str(row.get("audio_path") or report_path)),
                        task_d_status=str(row.get("speaker_status") or "unknown"),
                        speaker_similarity=_float_or_none(row.get("speaker_similarity")),
                        text_similarity=_float_or_none(row.get("text_similarity")),
                        overall_status=str(row.get("overall_status") or "failed"),
                        task_d_report_path=report_path,
                        mix_status="skipped_missing_upstream",
                        notes=["missing_anchor_or_translation"],
                    )
                )
                continue

            item = TimelineItem(
                segment_id=segment_id,
                speaker_id=str(row.get("speaker_id") or translation.get("speaker_id") or ""),
                target_lang=str(payload.get("backend", {}).get("target_lang") or request.target_lang),
                target_text=str(translation.get("target_text") or row.get("target_text") or ""),
                anchor_start=float(anchor.get("start") or 0.0),
                anchor_end=float(anchor.get("end") or 0.0),
                source_duration_sec=float(anchor.get("duration") or row.get("source_duration_sec") or 0.0),
                generated_duration_sec=float(row.get("generated_duration_sec") or 0.0),
                audio_path=Path(str(row.get("audio_path"))).expanduser().resolve(),
                task_d_status=str(row.get("speaker_status") or "unknown"),
                speaker_similarity=_float_or_none(row.get("speaker_similarity")),
                text_similarity=_float_or_none(row.get("text_similarity")),
                overall_status=str(row.get("overall_status") or "failed"),
                task_d_report_path=report_path,
                qa_flags=[str(flag) for flag in translation.get("qa_flags", [])],
            )
            if not item.audio_path.exists():
                item.mix_status = "skipped_missing_audio"
                item.notes.append("missing_task_d_audio")
                skipped.append(item)
                continue
            if item.overall_status == "failed":
                item.notes.append("task_d_failed_upstream")
            item.quality_score = _quality_score(item)
            seen_segment_ids.add(segment_id)
            candidates.append(item)

    candidates.sort(key=_timeline_sort_key)
    skipped.sort(key=_timeline_sort_key)
    return candidates, skipped


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
        else:
            fitted_path = compress_audio(
                input_path=item.audio_path,
                output_path=fit_dir / f"{item.segment_id}.wav",
                tempo=1.0,
                backend="atempo",
                output_sample_rate=request.output_sample_rate,
            )
        if strategy == "overflow_unfitted":
            item.notes.append("fit_overflow_passthrough")
        elif strategy == "underflow_unfitted":
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
    direct_upper = 1.20 if request.fit_policy == "conservative" else 1.25
    pad_lower = 0.60 if request.fit_policy == "conservative" else 0.55
    if 0.85 <= ratio <= direct_upper:
        return "direct"
    if direct_upper < ratio <= request.max_compress_ratio:
        return "compress"
    if pad_lower <= ratio < 0.85:
        return "pad"
    if ratio > request.max_compress_ratio:
        return "overflow_unfitted"
    return "underflow_unfitted"


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


__all__ = ["render_dub"]
