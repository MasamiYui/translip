from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
from pathlib import Path
from typing import Any

ALGORITHM_VERSION = "ocr-guided-asr-correction-v1"

_PUNCTUATION_RE = re.compile(r"[\s\[\]（）()【】,，.。!?！？:：;；、\"'‘’“”\-—_]+")


@dataclass(frozen=True, slots=True)
class CorrectionConfig:
    enabled: bool = True
    preset: str = "standard"
    min_ocr_confidence: float = 0.85
    min_alignment_score: float = 0.55
    lead_tolerance_sec: float = 0.6
    lag_tolerance_sec: float = 0.8
    min_length_ratio: float = 0.45
    max_length_ratio: float = 2.2
    ocr_only_policy: str = "report_only"
    algorithm_version: str = ALGORITHM_VERSION

    @classmethod
    def standard(cls) -> "CorrectionConfig":
        return cls()

    @classmethod
    def conservative(cls) -> "CorrectionConfig":
        return cls(
            preset="conservative",
            min_ocr_confidence=0.92,
            min_alignment_score=0.70,
            min_length_ratio=0.65,
            max_length_ratio=1.60,
        )

    @classmethod
    def aggressive(cls) -> "CorrectionConfig":
        return cls(
            preset="aggressive",
            min_ocr_confidence=0.75,
            min_alignment_score=0.40,
            min_length_ratio=0.35,
            max_length_ratio=2.80,
        )


@dataclass(frozen=True, slots=True)
class CorrectionResult:
    corrected_payload: dict[str, Any]
    report: dict[str, Any]


@dataclass(frozen=True, slots=True)
class CorrectionArtifacts:
    corrected_segments_path: Path
    corrected_srt_path: Path
    report_path: Path
    manifest_path: Path


@dataclass(frozen=True, slots=True)
class _OcrEvent:
    event_id: str
    start: float
    end: float
    text: str
    confidence: float

    @property
    def midpoint(self) -> float:
        return (self.start + self.end) / 2

    @property
    def duration(self) -> float:
        return max(0.001, self.end - self.start)


def load_json_payload(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _clean_text(text: str) -> str:
    return _PUNCTUATION_RE.sub("", str(text or ""))


def _length_ratio(source: str, candidate: str) -> float:
    source_len = len(_clean_text(source))
    candidate_len = len(_clean_text(candidate))
    if source_len == 0:
        return 1.0 if candidate_len == 0 else float("inf")
    return candidate_len / source_len


def _text_similarity(source: str, candidate: str) -> float:
    left = _clean_text(source)
    right = _clean_text(candidate)
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    matches = sum((min(left.count(char), right.count(char)) for char in set(left)))
    return matches / max(len(left), len(right))


def _overlap_seconds(start_a: float, end_a: float, start_b: float, end_b: float) -> float:
    return max(0.0, min(end_a, end_b) - max(start_a, start_b))


def _alignment_score(segment: dict[str, Any], events: list[_OcrEvent]) -> float:
    if not events:
        return 0.0
    segment_start = float(segment.get("start", 0.0))
    segment_end = float(segment.get("end", segment_start))
    segment_duration = max(0.001, segment_end - segment_start)
    total_overlap = sum(_overlap_seconds(segment_start, segment_end, event.start, event.end) for event in events)
    ocr_duration = sum(event.duration for event in events)
    return round(min(1.0, max(total_overlap / segment_duration, total_overlap / max(0.001, ocr_duration))), 3)


def _round_sec(value: float) -> float:
    return round(float(value), 3)


def _time_window(start: float, end: float) -> dict[str, float]:
    start = _round_sec(start)
    end = _round_sec(max(end, start))
    return {
        "start": start,
        "end": end,
        "duration": _round_sec(max(0.0, end - start)),
    }


def _build_timing_metadata(
    *,
    segment: dict[str, Any],
    events: list[_OcrEvent],
    config: CorrectionConfig,
) -> dict[str, Any] | None:
    if not events:
        return None

    segment_start = float(segment.get("start", 0.0))
    segment_end = float(segment.get("end", segment_start))
    if segment_end < segment_start:
        segment_start, segment_end = segment_end, segment_start

    ocr_start = min(event.start for event in events)
    ocr_end = max(event.end for event in events)
    ocr_quality_score = round(sum(event.confidence for event in events) / len(events), 3)

    warnings: list[str] = []
    policy = "asr_anchor"
    dubbing_start = segment_start
    dubbing_end = segment_end

    if ocr_start - segment_start > config.lead_tolerance_sec:
        dubbing_start = max(segment_start, ocr_start - config.lead_tolerance_sec)
        policy = "late_ocr_anchor"
        warnings.append("asr_start_precedes_ocr_window")
    if ocr_end - segment_end > config.lag_tolerance_sec:
        dubbing_end = ocr_end
        policy = "ocr_extended_anchor" if policy == "asr_anchor" else f"{policy}+ocr_extended_anchor"
        warnings.append("ocr_window_extends_after_asr")
    elif ocr_end > segment_end:
        dubbing_end = ocr_end

    if dubbing_end <= dubbing_start:
        dubbing_end = max(dubbing_start + 0.001, ocr_end, segment_end)
        warnings.append("dubbing_window_clamped")

    subtitle_window = _time_window(ocr_start, ocr_end)
    return {
        "source": "ocr_correction",
        "asr_window": _time_window(segment_start, segment_end),
        "ocr_window": {
            **subtitle_window,
            "event_ids": [event.event_id for event in events],
            "confidence": ocr_quality_score,
        },
        "subtitle_window": subtitle_window,
        "dubbing_window": {
            **_time_window(dubbing_start, dubbing_end),
            "policy": policy,
        },
        "warnings": warnings,
    }


def _normalize_event(raw: dict[str, Any], index: int) -> _OcrEvent | None:
    text = str(raw.get("text") or "").strip()
    if not text:
        return None
    start = float(raw.get("start", 0.0))
    end = float(raw.get("end", start))
    if end < start:
        start, end = end, start
    return _OcrEvent(
        event_id=str(raw.get("event_id") or raw.get("id") or f"evt-{index:04d}"),
        start=start,
        end=end,
        text=text,
        confidence=float(raw.get("confidence", 1.0)),
    )


def _load_events(ocr_payload: dict[str, Any]) -> list[_OcrEvent]:
    raw_events = ocr_payload.get("events") or []
    events = [_normalize_event(raw, index) for index, raw in enumerate(raw_events, start=1)]
    return sorted((event for event in events if event is not None), key=lambda event: (event.start, event.end))


def _candidate_events(segment: dict[str, Any], events: list[_OcrEvent], used_event_ids: set[str]) -> list[_OcrEvent]:
    segment_start = float(segment.get("start", 0.0))
    segment_end = float(segment.get("end", segment_start))
    candidates: list[_OcrEvent] = []
    for event in events:
        if event.event_id in used_event_ids:
            continue
        overlaps = _overlap_seconds(segment_start, segment_end, event.start, event.end) > 0
        midpoint_inside = segment_start <= event.midpoint <= segment_end
        if overlaps or midpoint_inside:
            candidates.append(event)
    return candidates


def _build_disabled_result(segments_payload: dict[str, Any], config: CorrectionConfig) -> CorrectionResult:
    corrected_payload = dict(segments_payload)
    corrected_payload["segments"] = [dict(segment) for segment in segments_payload.get("segments") or []]
    corrected_payload["correction"] = {
        "enabled": False,
        "algorithm_version": config.algorithm_version,
        "source": "ocr",
        "preset": config.preset,
        "corrected_count": 0,
        "review_count": 0,
        "ocr_only_count": 0,
    }
    report = {
        "summary": {
            "segment_count": len(corrected_payload["segments"]),
            "corrected_count": 0,
            "kept_asr_count": len(corrected_payload["segments"]),
            "review_count": 0,
            "ocr_only_count": 0,
            "auto_correction_rate": 0.0,
            "review_rate": 0.0,
            "fallback_reason": "disabled",
            "algorithm_version": config.algorithm_version,
        },
        "segments": [],
        "ocr_only_events": [],
    }
    return CorrectionResult(corrected_payload=corrected_payload, report=report)


def correct_asr_segments_with_ocr(
    *,
    segments_payload: dict[str, Any],
    ocr_payload: dict[str, Any],
    config: CorrectionConfig,
) -> CorrectionResult:
    if not config.enabled:
        return _build_disabled_result(segments_payload, config)

    events = _load_events(ocr_payload)
    segments = [dict(segment) for segment in segments_payload.get("segments") or []]
    corrected_segments: list[dict[str, Any]] = []
    report_segments: list[dict[str, Any]] = []
    used_event_ids: set[str] = set()

    corrected_count = 0
    kept_asr_count = 0
    review_count = 0

    for segment in segments:
        original_text = str(segment.get("text") or "")
        candidates = _candidate_events(segment, events, used_event_ids)
        high_confidence_candidates = [
            event for event in candidates if event.confidence >= config.min_ocr_confidence
        ]
        merged_text = "".join(event.text for event in high_confidence_candidates)
        alignment_score = _alignment_score(segment, high_confidence_candidates)
        ocr_quality_score = (
            round(sum(event.confidence for event in high_confidence_candidates) / len(high_confidence_candidates), 3)
            if high_confidence_candidates
            else 0.0
        )
        text_similarity_score = round(_text_similarity(original_text, merged_text), 3) if merged_text else 0.0
        length_ratio = _length_ratio(original_text, merged_text) if merged_text else 0.0
        length_ok = config.min_length_ratio <= length_ratio <= config.max_length_ratio
        should_replace = bool(
            high_confidence_candidates
            and alignment_score >= config.min_alignment_score
            and length_ok
        )

        corrected = dict(segment)
        if should_replace:
            corrected["text"] = merged_text
            decision = "merge_ocr" if len(high_confidence_candidates) > 1 else "use_ocr"
            needs_review = False
            corrected_count += 1
            used_event_ids.update(event.event_id for event in high_confidence_candidates)
        else:
            corrected["text"] = original_text
            decision = "use_asr"
            needs_review = False
            kept_asr_count += 1
            if candidates and not high_confidence_candidates:
                reason = "low_ocr_confidence"
            elif high_confidence_candidates:
                reason = "weak_alignment_or_length_mismatch"
                decision = "review"
                needs_review = True
                review_count += 1
                kept_asr_count -= 1
            else:
                reason = "no_ocr_candidate"

        if should_replace:
            reason = None

        timing_metadata = (
            _build_timing_metadata(
                segment=segment,
                events=high_confidence_candidates,
                config=config,
            )
            if should_replace
            else None
        )
        if timing_metadata is not None:
            existing_timing = corrected.get("timing") if isinstance(corrected.get("timing"), dict) else {}
            corrected["timing"] = {
                **existing_timing,
                **timing_metadata,
            }

        corrected_segments.append(corrected)
        report_row = {
            "segment_id": str(segment.get("id") or ""),
            "start": float(segment.get("start", 0.0)),
            "end": float(segment.get("end", segment.get("start", 0.0))),
            "speaker_label": segment.get("speaker_label"),
            "original_asr_text": original_text,
            "corrected_text": corrected["text"],
            "decision": decision,
            "ocr_event_ids": [event.event_id for event in high_confidence_candidates],
            "alignment_score": alignment_score,
            "ocr_quality_score": ocr_quality_score,
            "text_similarity_score": text_similarity_score,
            "length_ratio": round(length_ratio, 3) if length_ratio != float("inf") else None,
            "reason": reason,
            "needs_review": needs_review,
        }
        if timing_metadata is not None:
            report_row["timing"] = timing_metadata
        report_segments.append(report_row)

    segment_windows = [(float(segment.get("start", 0.0)), float(segment.get("end", 0.0))) for segment in segments]
    ocr_only_events = []
    for event in events:
        if event.event_id in used_event_ids or event.confidence < config.min_ocr_confidence:
            continue
        if any(start <= event.midpoint <= end for start, end in segment_windows):
            continue
        ocr_only_events.append(
            {
                "event_id": event.event_id,
                "start": event.start,
                "end": event.end,
                "text": event.text,
                "decision": "ocr_only",
                "action": "reported_only",
                "needs_review": True,
            }
        )

    segment_count = len(corrected_segments)
    ocr_only_count = len(ocr_only_events)
    corrected_payload = dict(segments_payload)
    corrected_payload["segments"] = corrected_segments
    corrected_payload["correction"] = {
        "enabled": True,
        "algorithm_version": config.algorithm_version,
        "source": "ocr",
        "preset": config.preset,
        "report_path": "asr-ocr-correct/voice/correction-report.json",
        "corrected_count": corrected_count,
        "review_count": review_count,
        "ocr_only_count": ocr_only_count,
    }
    report = {
        "summary": {
            "segment_count": segment_count,
            "corrected_count": corrected_count,
            "kept_asr_count": kept_asr_count,
            "review_count": review_count,
            "ocr_only_count": ocr_only_count,
            "auto_correction_rate": round(corrected_count / segment_count, 3) if segment_count else 0.0,
            "review_rate": round(review_count / segment_count, 3) if segment_count else 0.0,
            "fallback_reason": None,
            "algorithm_version": config.algorithm_version,
        },
        "segments": report_segments,
        "ocr_only_events": ocr_only_events,
    }
    return CorrectionResult(corrected_payload=corrected_payload, report=report)


def _srt_timestamp(seconds: float) -> str:
    millis = int(round(seconds * 1000))
    hours, remainder = divmod(millis, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, ms = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def _write_srt(segments: list[dict[str, Any]], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for index, segment in enumerate(segments, start=1):
        speaker_label = segment.get("speaker_label") or "SPEAKER_00"
        lines.extend(
            [
                str(index),
                f"{_srt_timestamp(float(segment.get('start', 0.0)))} --> {_srt_timestamp(float(segment.get('end', 0.0)))}",
                f"[{speaker_label}] {segment.get('text') or ''}",
                "",
            ]
        )
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def write_correction_artifacts(result: CorrectionResult, *, output_dir: Path) -> CorrectionArtifacts:
    output_dir.mkdir(parents=True, exist_ok=True)
    corrected_segments_path = output_dir / "segments.zh.corrected.json"
    corrected_srt_path = output_dir / "segments.zh.corrected.srt"
    report_path = output_dir / "correction-report.json"
    manifest_path = output_dir / "correction-manifest.json"

    corrected_segments_path.write_text(
        json.dumps(result.corrected_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_srt(result.corrected_payload.get("segments") or [], corrected_srt_path)
    report_path.write_text(
        json.dumps(result.report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "status": "succeeded",
        "artifacts": {
            "corrected_segments": str(corrected_segments_path),
            "corrected_srt": str(corrected_srt_path),
            "report": str(report_path),
        },
        "config": {
            "algorithm_version": result.report["summary"].get("algorithm_version", ALGORITHM_VERSION),
            "enabled": result.corrected_payload.get("correction", {}).get("enabled", True),
            "preset": result.corrected_payload.get("correction", {}).get("preset", "standard"),
            "ocr_only_policy": "report_only",
        },
        "summary": result.report.get("summary", {}),
        "timing": {
            "finished_at": datetime.now(timezone.utc).isoformat(),
        },
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return CorrectionArtifacts(
        corrected_segments_path=corrected_segments_path,
        corrected_srt_path=corrected_srt_path,
        report_path=report_path,
        manifest_path=manifest_path,
    )


__all__ = [
    "ALGORITHM_VERSION",
    "CorrectionArtifacts",
    "CorrectionConfig",
    "CorrectionResult",
    "correct_asr_segments_with_ocr",
    "load_json_payload",
    "write_correction_artifacts",
]
