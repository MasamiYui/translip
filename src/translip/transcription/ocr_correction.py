from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
from pathlib import Path
from typing import Any, Callable

from ..subtitles.parse import parse_subtitle_file

ALGORITHM_VERSION = "ocr-guided-asr-correction-v1"

_SUBTITLE_SUFFIXES = {".srt", ".vtt"}

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
    llm_arbitration: str = "off"
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
class ArbitrationRequest:
    segment_id: str
    asr_text: str
    ocr_text: str
    start: float
    end: float
    speaker_label: str | None


@dataclass(frozen=True, slots=True)
class ArbitrationVerdict:
    decision: str  # "use_asr" | "use_ocr" | "merge"
    text: str
    reason: str


# Resolves an ambiguous (review) segment. Returns None to defer to deterministic behavior.
Arbitrator = Callable[[ArbitrationRequest], "ArbitrationVerdict | None"]


@dataclass(frozen=True, slots=True)
class CorrectionArtifacts:
    corrected_segments_path: Path
    corrected_srt_path: Path
    clean_srt_path: Path
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


def _is_subtitle(path: Path) -> bool:
    return path.suffix.lower() in _SUBTITLE_SUFFIXES


def load_segments_payload(path: Path) -> dict[str, Any]:
    """Load ASR segments from JSON, or parse an SRT/VTT subtitle into the segments shape.

    Subtitles carry no diarization, so a missing speaker prefix falls back to a single
    speaker. The ``[LABEL] text`` prefix this project writes is parsed back out.
    """
    if not _is_subtitle(path):
        return load_json_payload(path)
    cues = parse_subtitle_file(path)
    segments = [
        {
            "id": f"seg-{cue.index:04d}",
            "start": cue.start,
            "end": cue.end,
            "duration": round(max(0.0, cue.end - cue.start), 3),
            "speaker_label": cue.speaker_label or "SPEAKER_00",
            "text": cue.text,
        }
        for cue in cues
    ]
    return {
        "input": {"path": str(path), "source_format": path.suffix.lower().lstrip(".")},
        "segments": segments,
    }


def load_ocr_payload(path: Path) -> dict[str, Any]:
    """Load OCR events from JSON, or parse an SRT/VTT subtitle into the events shape.

    Subtitles carry no per-event confidence, so it defaults to 1.0 — meaning the OCR
    confidence gate is effectively bypassed for subtitle-sourced input.
    """
    if not _is_subtitle(path):
        return load_json_payload(path)
    cues = parse_subtitle_file(path)
    events = [
        {
            "event_id": f"evt-{cue.index:04d}",
            "start": cue.start,
            "end": cue.end,
            "text": cue.text,
            "confidence": 1.0,
        }
        for cue in cues
    ]
    return {
        "source": {"path": str(path), "source_format": path.suffix.lower().lstrip(".")},
        "events": events,
    }


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


def _first_number(raw: dict[str, Any], *keys: str, default: float = 0.0) -> float:
    for key in keys:
        value = raw.get(key)
        if value is not None:
            return float(value)
    return default


def _normalize_event(raw: dict[str, Any], index: int) -> _OcrEvent | None:
    text = str(raw.get("text") or "").strip()
    if not text:
        return None
    # Accept both the OCR-events schema (start/end) and the detection schema (start_time/end_time).
    start = _first_number(raw, "start", "start_time", default=0.0)
    end = _first_number(raw, "end", "end_time", default=start)
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
    raw_events = ocr_payload.get("events") or ocr_payload.get("results") or []
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


def _is_faithful(candidate: str, *sources: str) -> bool:
    """True when every meaningful character of ``candidate`` also appears in some source."""
    candidate_chars = set(_clean_text(candidate))
    if not candidate_chars:
        return False
    allowed: set[str] = set()
    for source in sources:
        allowed |= set(_clean_text(source))
    return candidate_chars <= allowed


def _arbitration_request(segment: dict[str, Any], asr_text: str, ocr_text: str) -> ArbitrationRequest:
    start = float(segment.get("start", 0.0))
    return ArbitrationRequest(
        segment_id=str(segment.get("id") or ""),
        asr_text=asr_text,
        ocr_text=ocr_text,
        start=start,
        end=float(segment.get("end", start)),
        speaker_label=segment.get("speaker_label"),
    )


def _apply_arbitration(
    verdict: ArbitrationVerdict | None,
    asr_text: str,
    ocr_text: str,
) -> tuple[str, str] | None:
    """Map a verdict to (decision_label, text). None defers to the deterministic review path.

    ``use_asr``/``use_ocr`` reuse our own known-good text; ``merge`` trusts the model's text
    only after it passes the faithfulness check (no characters outside the two sources).
    """
    if verdict is None:
        return None
    if verdict.decision == "use_asr":
        return "llm_use_asr", asr_text
    if verdict.decision == "use_ocr":
        return "llm_use_ocr", ocr_text
    if verdict.decision == "merge" and _is_faithful(verdict.text, asr_text, ocr_text):
        return "llm_merge", verdict.text.strip()
    return None


def correct_asr_segments_with_ocr(
    *,
    segments_payload: dict[str, Any],
    ocr_payload: dict[str, Any],
    config: CorrectionConfig,
    arbitrator: Arbitrator | None = None,
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
    arbitrated_count = 0

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
        reason: str | None = None
        arbitration_record: dict[str, Any] | None = None
        if should_replace:
            corrected["text"] = merged_text
            decision = "merge_ocr" if len(high_confidence_candidates) > 1 else "use_ocr"
            needs_review = False
            corrected_count += 1
            used_event_ids.update(event.event_id for event in high_confidence_candidates)
        elif candidates and not high_confidence_candidates:
            corrected["text"] = original_text
            decision = "use_asr"
            needs_review = False
            reason = "low_ocr_confidence"
            kept_asr_count += 1
        elif high_confidence_candidates:
            # Ambiguous "review" bucket: high-confidence OCR that failed alignment/length.
            # Only here do we ask the LLM to arbitrate (when one is provided).
            verdict = arbitrator(_arbitration_request(segment, original_text, merged_text)) if arbitrator else None
            outcome = _apply_arbitration(verdict, original_text, merged_text)
            if outcome is not None:
                decision, corrected["text"] = outcome
                needs_review = False
                arbitrated_count += 1
                arbitration_record = {"decision": verdict.decision, "reason": verdict.reason, "applied": True}
                if decision == "llm_use_asr":
                    kept_asr_count += 1
                else:
                    corrected_count += 1
                    used_event_ids.update(event.event_id for event in high_confidence_candidates)
            else:
                corrected["text"] = original_text
                decision = "review"
                needs_review = True
                reason = "weak_alignment_or_length_mismatch"
                review_count += 1
                if verdict is not None:
                    arbitration_record = {"decision": verdict.decision, "reason": verdict.reason, "applied": False}
        else:
            corrected["text"] = original_text
            decision = "use_asr"
            needs_review = False
            reason = "no_ocr_candidate"
            kept_asr_count += 1

        replaced_with_ocr = should_replace or decision in {"llm_use_ocr", "llm_merge"}
        timing_metadata = (
            _build_timing_metadata(
                segment=segment,
                events=high_confidence_candidates,
                config=config,
            )
            if replaced_with_ocr
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
        if arbitration_record is not None:
            report_row["arbitration"] = arbitration_record
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
        "llm_arbitration": config.llm_arbitration,
        "corrected_count": corrected_count,
        "review_count": review_count,
        "arbitrated_count": arbitrated_count,
        "ocr_only_count": ocr_only_count,
    }
    report = {
        "summary": {
            "segment_count": segment_count,
            "corrected_count": corrected_count,
            "kept_asr_count": kept_asr_count,
            "review_count": review_count,
            "arbitrated_count": arbitrated_count,
            "ocr_only_count": ocr_only_count,
            "auto_correction_rate": round(corrected_count / segment_count, 3) if segment_count else 0.0,
            "review_rate": round(review_count / segment_count, 3) if segment_count else 0.0,
            "llm_arbitration": config.llm_arbitration,
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


def _write_srt(
    segments: list[dict[str, Any]],
    output_path: Path,
    *,
    include_speaker: bool = True,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for index, segment in enumerate(segments, start=1):
        text = segment.get("text") or ""
        if include_speaker:
            speaker_label = segment.get("speaker_label") or "SPEAKER_00"
            text = f"[{speaker_label}] {text}"
        lines.extend(
            [
                str(index),
                f"{_srt_timestamp(float(segment.get('start', 0.0)))} --> {_srt_timestamp(float(segment.get('end', 0.0)))}",
                text,
                "",
            ]
        )
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def write_correction_artifacts(result: CorrectionResult, *, output_dir: Path) -> CorrectionArtifacts:
    output_dir.mkdir(parents=True, exist_ok=True)
    corrected_segments_path = output_dir / "segments.zh.corrected.json"
    corrected_srt_path = output_dir / "segments.zh.corrected.srt"
    clean_srt_path = output_dir / "segments.zh.corrected.clean.srt"
    report_path = output_dir / "correction-report.json"
    manifest_path = output_dir / "correction-manifest.json"

    corrected_segments = result.corrected_payload.get("segments") or []
    corrected_segments_path.write_text(
        json.dumps(result.corrected_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_srt(corrected_segments, corrected_srt_path)
    _write_srt(corrected_segments, clean_srt_path, include_speaker=False)
    report_path.write_text(
        json.dumps(result.report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "status": "succeeded",
        "artifacts": {
            "corrected_segments": str(corrected_segments_path),
            "corrected_srt": str(corrected_srt_path),
            "corrected_clean_srt": str(clean_srt_path),
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
        clean_srt_path=clean_srt_path,
        report_path=report_path,
        manifest_path=manifest_path,
    )


__all__ = [
    "ALGORITHM_VERSION",
    "ArbitrationRequest",
    "ArbitrationVerdict",
    "Arbitrator",
    "CorrectionArtifacts",
    "CorrectionConfig",
    "CorrectionResult",
    "correct_asr_segments_with_ocr",
    "load_json_payload",
    "load_ocr_payload",
    "load_segments_payload",
    "write_correction_artifacts",
]
