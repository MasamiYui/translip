from __future__ import annotations

import json
import math
import re
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from ..config import (
    DEFAULT_VOICE_BANK_MIN_REFERENCE_CLIPS,
    DEFAULT_VOICE_BANK_MIN_REFERENCE_DURATION_SEC,
)
from ..pipeline.manifest import now_iso
from ..utils.files import ensure_directory

IDEAL_REFERENCE_MIN_SEC = 8.0
IDEAL_REFERENCE_MAX_SEC = 10.5
HARD_REFERENCE_MAX_SEC = 15.0
COMPOSITE_TARGET_SEC = 9.0
COMPOSITE_MAX_PART_SEC = 3.2
COMPOSITE_GAP_SEC = 0.25


@dataclass(slots=True)
class VoiceBankRequest:
    profiles_path: Path | str
    output_dir: Path | str
    target_lang: str = "en"
    task_d_report_paths: list[Path | str] | None = None
    max_references_per_speaker: int = 7
    include_composites: bool = True

    def normalized(self) -> "VoiceBankRequest":
        return VoiceBankRequest(
            profiles_path=Path(self.profiles_path).expanduser().resolve(),
            output_dir=Path(self.output_dir).expanduser().resolve(),
            target_lang=self.target_lang,
            task_d_report_paths=[
                Path(path).expanduser().resolve()
                for path in (self.task_d_report_paths or [])
            ],
            max_references_per_speaker=int(self.max_references_per_speaker),
            include_composites=bool(self.include_composites),
        )


@dataclass(slots=True)
class VoiceBankArtifacts:
    voice_bank_path: Path
    report_path: Path
    manifest_path: Path


@dataclass(slots=True)
class VoiceBankResult:
    request: VoiceBankRequest
    artifacts: VoiceBankArtifacts
    voice_bank: dict[str, Any]
    manifest: dict[str, Any]


def build_voice_bank(request: VoiceBankRequest) -> VoiceBankResult:
    normalized = _validate_request(request)
    started_at = now_iso()
    started_monotonic = time.monotonic()
    output_dir = ensure_directory(Path(normalized.output_dir))
    voice_bank_path = output_dir / f"voice_bank.{normalized.target_lang}.json"
    report_path = output_dir / f"voice_bank_report.{normalized.target_lang}.md"
    manifest_path = output_dir / "voice-bank-manifest.json"

    profiles_payload = _read_json(Path(normalized.profiles_path))
    report_payloads = [_read_json(Path(path)) for path in normalized.task_d_report_paths or []]
    reference_metrics = _collect_reference_metrics(report_payloads)
    speakers = []
    for profile in profiles_payload.get("profiles", []):
        if not isinstance(profile, dict):
            continue
        speakers.append(
            _speaker_bank(
                profile=profile,
                output_dir=output_dir,
                reference_metrics=reference_metrics,
                max_references=normalized.max_references_per_speaker,
                include_composites=normalized.include_composites,
            )
        )

    voice_bank = {
        "version": "voice-bank-v1",
        "created_at": now_iso(),
        "input": {
            "profiles_path": str(normalized.profiles_path),
            "task_d_report_paths": [str(path) for path in normalized.task_d_report_paths or []],
        },
        "target_lang": normalized.target_lang,
        "stats": _bank_stats(speakers=speakers, report_count=len(report_payloads)),
        "speakers": speakers,
    }
    apply_cross_speaker_fallback(voice_bank)
    _write_json(voice_bank, voice_bank_path)
    report_text = _build_markdown_report(voice_bank)
    report_path.write_text(report_text, encoding="utf-8")

    manifest = {
        "input": voice_bank["input"],
        "request": {
            "target_lang": normalized.target_lang,
            "max_references_per_speaker": normalized.max_references_per_speaker,
            "include_composites": normalized.include_composites,
        },
        "artifacts": {
            "voice_bank": str(voice_bank_path),
            "report": str(report_path),
        },
        "stats": voice_bank["stats"],
        "timing": {
            "started_at": started_at,
            "finished_at": now_iso(),
            "elapsed_sec": round(time.monotonic() - started_monotonic, 3),
        },
        "status": "succeeded",
        "error": None,
    }
    _write_json(manifest, manifest_path)
    return VoiceBankResult(
        request=normalized,
        artifacts=VoiceBankArtifacts(
            voice_bank_path=voice_bank_path,
            report_path=report_path,
            manifest_path=manifest_path,
        ),
        voice_bank=voice_bank,
        manifest=manifest,
    )


def _validate_request(request: VoiceBankRequest) -> VoiceBankRequest:
    normalized = request.normalized()
    if not Path(normalized.profiles_path).exists():
        raise FileNotFoundError(f"Speaker profiles file does not exist: {normalized.profiles_path}")
    for path in normalized.task_d_report_paths or []:
        if not Path(path).exists():
            raise FileNotFoundError(f"Task D report file does not exist: {path}")
    if normalized.max_references_per_speaker <= 0:
        raise ValueError("max_references_per_speaker must be greater than 0")
    return normalized


def _speaker_bank(
    *,
    profile: dict[str, Any],
    output_dir: Path,
    reference_metrics: dict[str, dict[str, Any]],
    max_references: int,
    include_composites: bool,
) -> dict[str, Any]:
    speaker_id = str(profile.get("speaker_id") or "")
    profile_id = str(profile.get("profile_id") or profile.get("source_label") or "unknown")
    source_refs = [
        _source_reference(profile=profile, raw=raw, index=index, reference_metrics=reference_metrics)
        for index, raw in enumerate(profile.get("reference_clips", []), start=1)
        if isinstance(raw, dict)
    ]
    source_refs = [ref for ref in source_refs if ref is not None]
    references = sorted(source_refs, key=lambda item: float(item["quality_score"]), reverse=True)
    if include_composites and len(source_refs) >= 2:
        composite = _composite_reference(
            profile=profile,
            references=source_refs,
            output_dir=output_dir,
            reference_metrics=reference_metrics,
        )
        if composite is not None:
            references.append(composite)
            references = sorted(references, key=lambda item: float(item["quality_score"]), reverse=True)

    references = references[:max_references]
    recommended = _recommended_reference(references)
    usable_source_count = _count_usable_source_references(references)
    bank_status = _bank_status(
        profile=profile,
        references=references,
        recommended=recommended,
        usable_source_count=usable_source_count,
    )
    return {
        "speaker_id": speaker_id or None,
        "profile_id": profile_id,
        "source_label": profile.get("source_label"),
        "display_name": profile.get("display_name") or profile.get("source_label") or speaker_id or profile_id,
        "bank_status": bank_status,
        "segment_count": int(profile.get("segment_count") or 0),
        "total_speech_sec": _round_float(profile.get("total_speech_sec")),
        "reference_clip_count": int(profile.get("reference_clip_count") or len(profile.get("reference_clips", []))),
        "usable_source_reference_count": usable_source_count,
        "min_reference_clip_requirement": DEFAULT_VOICE_BANK_MIN_REFERENCE_CLIPS,
        "cross_speaker_fallback": None,
        "recommended_reference_id": recommended.get("reference_id") if recommended else None,
        "recommended_reference_path": recommended.get("audio_path") if recommended else None,
        "references": references,
    }


def _source_reference(
    *,
    profile: dict[str, Any],
    raw: dict[str, Any],
    index: int,
    reference_metrics: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    path = str(raw.get("path") or "").strip()
    text = str(raw.get("text") or "").strip()
    duration = float(raw.get("duration") or raw.get("duration_sec") or 0.0)
    if not path or not text or duration <= 0.0:
        return None
    rms = float(raw.get("rms") or 0.0)
    risk_flags = _reference_risk_flags(duration_sec=duration, text=text, rms=rms)
    base_score, score_parts = _heuristic_reference_score(duration_sec=duration, text=text, rms=rms, risk_flags=risk_flags)
    metrics = reference_metrics.get(_norm_path(path), {})
    benchmark_score = _benchmark_reference_score(metrics)
    quality_score = _combined_quality_score(base_score=base_score, benchmark_score=benchmark_score, metrics=metrics)
    reference_id = f"{profile.get('profile_id') or 'profile'}_clip_{index:04d}"
    return {
        "reference_id": reference_id,
        "type": "source_clip",
        "audio_path": str(Path(path).expanduser().resolve()),
        "duration_sec": round(duration, 3),
        "text": text,
        "rms": round(rms, 6),
        "segment_ids": [str(item) for item in raw.get("segment_ids", [])] if isinstance(raw.get("segment_ids"), list) else [],
        "start": _round_float(raw.get("start")),
        "end": _round_float(raw.get("end")),
        "quality_score": quality_score,
        "heuristic_score": round(base_score, 4),
        "benchmark_score": benchmark_score,
        "score_parts": score_parts,
        "benchmark": metrics,
        "risk_flags": risk_flags,
        "selection_reason": _selection_reason(score_parts=score_parts, benchmark_score=benchmark_score, risk_flags=risk_flags),
    }


def _composite_reference(
    *,
    profile: dict[str, Any],
    references: list[dict[str, Any]],
    output_dir: Path,
    reference_metrics: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    selected = sorted(
        [ref for ref in references if "missing_file" not in ref.get("risk_flags", [])],
        key=lambda item: float(item["heuristic_score"]),
        reverse=True,
    )[:4]
    if len(selected) < 2:
        return None

    parts: list[np.ndarray] = []
    text_parts: list[str] = []
    sample_rate: int | None = None
    total_audio_sec = 0.0
    used_ids: list[str] = []
    for ref in selected:
        path = Path(str(ref["audio_path"]))
        try:
            waveform, sr = sf.read(path, dtype="float32", always_2d=False)
        except Exception:
            continue
        if waveform.ndim == 2:
            waveform = waveform.mean(axis=1)
        if sample_rate is None:
            sample_rate = int(sr)
        if int(sr) != sample_rate:
            continue
        if parts:
            gap = np.zeros(int(COMPOSITE_GAP_SEC * sample_rate), dtype=np.float32)
            parts.append(gap)
            total_audio_sec += COMPOSITE_GAP_SEC
        max_samples = int(COMPOSITE_MAX_PART_SEC * sample_rate)
        piece = waveform[:max_samples].astype(np.float32)
        parts.append(piece)
        total_audio_sec += len(piece) / sample_rate
        text_parts.append(str(ref.get("text") or ""))
        used_ids.append(str(ref.get("reference_id") or path.stem))
        if total_audio_sec >= COMPOSITE_TARGET_SEC:
            break

    if len(parts) < 2 or sample_rate is None:
        return None
    profile_id = str(profile.get("profile_id") or profile.get("source_label") or "unknown")
    speaker_dir = ensure_directory(output_dir / "reference_bank" / profile_id)
    output_path = speaker_dir / "composite_0001.wav"
    audio = np.concatenate(parts)
    sf.write(output_path, audio, sample_rate)
    duration = float(len(audio) / sample_rate)
    text = " ".join(part for part in text_parts if part).strip()
    rms = float(math.sqrt(float(np.mean(np.square(audio))))) if audio.size else 0.0
    risk_flags = _reference_risk_flags(duration_sec=duration, text=text, rms=rms)
    risk_flags.append("composite_text_alignment_approx")
    base_score, score_parts = _heuristic_reference_score(duration_sec=duration, text=text, rms=rms, risk_flags=risk_flags)
    metrics = reference_metrics.get(_norm_path(output_path), {})
    benchmark_score = _benchmark_reference_score(metrics)
    quality_score = _combined_quality_score(base_score=base_score * 0.78, benchmark_score=benchmark_score, metrics=metrics)
    return {
        "reference_id": f"{profile_id}_composite_0001",
        "type": "composite",
        "audio_path": str(output_path.resolve()),
        "duration_sec": round(duration, 3),
        "text": text,
        "rms": round(rms, 6),
        "source_reference_ids": used_ids,
        "source_clip_count": len(used_ids),
        "quality_score": quality_score,
        "heuristic_score": round(base_score, 4),
        "benchmark_score": benchmark_score,
        "score_parts": score_parts,
        "benchmark": metrics,
        "risk_flags": risk_flags,
        "selection_reason": _selection_reason(score_parts=score_parts, benchmark_score=benchmark_score, risk_flags=risk_flags),
    }


def _collect_reference_metrics(report_payloads: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    rows: dict[str, list[dict[str, Any]]] = {}
    for payload in report_payloads:
        segments = payload.get("segments", payload if isinstance(payload, list) else [])
        if not isinstance(segments, list):
            continue
        for segment in segments:
            if not isinstance(segment, dict):
                continue
            for attempt in _attempt_rows(segment):
                ref_path = str(attempt.get("reference_path") or "")
                if not ref_path:
                    continue
                rows.setdefault(_norm_path(ref_path), []).append(attempt)
    return {path: _aggregate_attempts(attempts) for path, attempts in rows.items()}


def _attempt_rows(segment: dict[str, Any]) -> list[dict[str, Any]]:
    attempts = segment.get("attempts")
    if isinstance(attempts, list) and attempts:
        return [attempt for attempt in attempts if isinstance(attempt, dict)]
    return [
        {
            "reference_path": segment.get("reference_path"),
            "status": "selected",
            "selected": True,
            "duration_ratio": segment.get("duration_ratio"),
            "duration_status": segment.get("duration_status"),
            "speaker_similarity": segment.get("speaker_similarity"),
            "speaker_status": segment.get("speaker_status"),
            "text_similarity": segment.get("text_similarity"),
            "intelligibility_status": segment.get("intelligibility_status"),
            "overall_status": segment.get("overall_status"),
        }
    ]


def _aggregate_attempts(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    def values(key: str) -> list[float]:
        out = []
        for attempt in attempts:
            value = attempt.get(key)
            if value is None:
                continue
            try:
                out.append(float(value))
            except (TypeError, ValueError):
                continue
        return out

    status_counts = _status_counts(attempt.get("overall_status") for attempt in attempts)
    duration_counts = _status_counts(attempt.get("duration_status") for attempt in attempts)
    speaker_counts = _status_counts(attempt.get("speaker_status") for attempt in attempts)
    intelligibility_counts = _status_counts(attempt.get("intelligibility_status") for attempt in attempts)
    speaker_values = values("speaker_similarity")
    text_values = values("text_similarity")
    ratio_values = values("duration_ratio")
    return {
        "attempt_count": len(attempts),
        "selected_count": sum(1 for attempt in attempts if bool(attempt.get("selected")) or str(attempt.get("status")) == "selected"),
        "overall_status_counts": status_counts,
        "duration_status_counts": duration_counts,
        "speaker_status_counts": speaker_counts,
        "intelligibility_status_counts": intelligibility_counts,
        "avg_speaker_similarity": _mean(speaker_values),
        "avg_text_similarity": _mean(text_values),
        "avg_duration_ratio": _mean(ratio_values),
        "median_duration_ratio": _median(ratio_values),
    }


def _heuristic_reference_score(
    *,
    duration_sec: float,
    text: str,
    rms: float,
    risk_flags: list[str],
) -> tuple[float, dict[str, float]]:
    duration = _duration_score(duration_sec)
    text_score = _text_score(text)
    rms_score = _rms_score(rms)
    risk_penalty = min(0.45, 0.08 * len([flag for flag in risk_flags if flag != "long_reference_will_be_trimmed"]))
    total = duration * 0.42 + text_score * 0.28 + rms_score * 0.20 + (1.0 - risk_penalty) * 0.10
    return round(max(0.0, min(1.0, total)), 4), {
        "duration": round(duration, 4),
        "text": round(text_score, 4),
        "rms": round(rms_score, 4),
        "risk": round(1.0 - risk_penalty, 4),
    }


def _duration_score(duration_sec: float) -> float:
    if IDEAL_REFERENCE_MIN_SEC <= duration_sec <= IDEAL_REFERENCE_MAX_SEC:
        return 1.0
    if 5.0 <= duration_sec < IDEAL_REFERENCE_MIN_SEC:
        return 0.72
    if IDEAL_REFERENCE_MAX_SEC < duration_sec <= 12.0:
        return 0.86
    if 12.0 < duration_sec <= HARD_REFERENCE_MAX_SEC:
        return 0.66
    if 2.0 <= duration_sec < 5.0:
        return 0.42
    return 0.1


def _text_score(text: str) -> float:
    compact = re.sub(r"\s+", "", text)
    if len(compact) >= 24:
        return 1.0
    if len(compact) >= 16:
        return 0.86
    if len(compact) >= 8:
        return 0.66
    if len(compact) >= 4:
        return 0.42
    return 0.15


def _rms_score(rms: float) -> float:
    if 0.02 <= rms <= 0.22:
        return 1.0
    if 0.01 <= rms <= 0.32:
        return 0.76
    if 0.005 <= rms <= 0.45:
        return 0.48
    return 0.16


def _reference_risk_flags(*, duration_sec: float, text: str, rms: float) -> list[str]:
    flags: list[str] = []
    if duration_sec < 2.0:
        flags.append("too_short_for_auto_clone")
    elif duration_sec < 5.0:
        flags.append("short_reference")
    if duration_sec > 11.0:
        flags.append("long_reference_will_be_trimmed")
    if duration_sec > HARD_REFERENCE_MAX_SEC:
        flags.append("too_long_for_auto_clone")
    if rms <= 0.005:
        flags.append("low_rms")
    if rms >= 0.45:
        flags.append("high_rms")
    lowered = text.lower()
    if re.search(r"[!！?？~]{2,}", lowered) or re.search(r"(哈哈|呵呵|hahaha|lol)", lowered):
        flags.append("expressive_or_laughter")
    return flags


def _benchmark_reference_score(metrics: dict[str, Any]) -> float | None:
    attempt_count = int(metrics.get("attempt_count") or 0)
    if attempt_count <= 0:
        return None
    overall_counts = metrics.get("overall_status_counts") if isinstance(metrics.get("overall_status_counts"), dict) else {}
    duration_counts = metrics.get("duration_status_counts") if isinstance(metrics.get("duration_status_counts"), dict) else {}
    speaker_counts = metrics.get("speaker_status_counts") if isinstance(metrics.get("speaker_status_counts"), dict) else {}
    intelligibility_counts = metrics.get("intelligibility_status_counts") if isinstance(metrics.get("intelligibility_status_counts"), dict) else {}
    status_score = _weighted_status_score(overall_counts)
    duration_score = _weighted_status_score(duration_counts)
    speaker_score = _weighted_status_score(speaker_counts)
    intelligibility_score = _weighted_status_score(intelligibility_counts)
    speaker_similarity = float(metrics.get("avg_speaker_similarity") or 0.0)
    text_similarity = float(metrics.get("avg_text_similarity") or 0.0)
    score = (
        status_score * 0.26
        + duration_score * 0.18
        + speaker_score * 0.18
        + intelligibility_score * 0.14
        + min(1.0, speaker_similarity / 0.45) * 0.14
        + text_similarity * 0.10
    )
    confidence = min(1.0, attempt_count / 8.0)
    return round(score * confidence, 4)


def _combined_quality_score(
    *,
    base_score: float,
    benchmark_score: float | None,
    metrics: dict[str, Any],
) -> float:
    if benchmark_score is None:
        return round(base_score, 4)
    attempt_count = int(metrics.get("attempt_count") or 0)
    benchmark_weight = min(0.62, 0.28 + attempt_count * 0.035)
    return round(base_score * (1.0 - benchmark_weight) + benchmark_score * benchmark_weight, 4)


def _recommended_reference(references: list[dict[str, Any]]) -> dict[str, Any] | None:
    usable = [
        ref
        for ref in references
        if "too_short_for_auto_clone" not in ref.get("risk_flags", [])
        and "too_long_for_auto_clone" not in ref.get("risk_flags", [])
        and "low_rms" not in ref.get("risk_flags", [])
    ]
    if not usable:
        return references[0] if references else None
    source_usable = [
        ref
        for ref in usable
        if "composite_text_alignment_approx" not in ref.get("risk_flags", [])
        or ref.get("benchmark_score") is not None
    ]
    if source_usable:
        usable = source_usable
    return max(usable, key=lambda ref: float(ref.get("quality_score") or 0.0))


def _count_usable_source_references(references: list[dict[str, Any]]) -> int:
    """Count clips that satisfy the min_reference_clips hygiene bar.

    A "usable" clip must be:
        * of type 'source_clip' (composites don't count),
        * duration >= DEFAULT_VOICE_BANK_MIN_REFERENCE_DURATION_SEC, and
        * free of hard-failure risk flags (too_short / low_rms / missing_file).
    """

    count = 0
    min_duration = DEFAULT_VOICE_BANK_MIN_REFERENCE_DURATION_SEC
    hard_flags = {
        "too_short_for_auto_clone",
        "too_long_for_auto_clone",
        "low_rms",
        "missing_file",
    }
    for ref in references:
        if not isinstance(ref, dict):
            continue
        if str(ref.get("type")) != "source_clip":
            continue
        if float(ref.get("duration_sec") or 0.0) < min_duration:
            continue
        risk_flags = set(ref.get("risk_flags") or [])
        if risk_flags & hard_flags:
            continue
        count += 1
    return count


def _bank_status(
    *,
    profile: dict[str, Any],
    references: list[dict[str, Any]],
    recommended: dict[str, Any] | None,
    usable_source_count: int = 0,
) -> str:
    if not profile.get("speaker_id"):
        return "needs_speaker_review"
    if not references:
        return "missing_reference"
    if recommended is None:
        return "needs_manual_reference"
    # Sprint 2: below the 3-usable-clips floor, we flag the speaker so
    # downstream dubbing can prefer a cross-speaker fallback reference
    # instead of cloning on a thin pool.
    if usable_source_count < DEFAULT_VOICE_BANK_MIN_REFERENCE_CLIPS:
        return "needs_more_references"
    if any(flag in recommended.get("risk_flags", []) for flag in ["short_reference", "composite_text_alignment_approx"]):
        return "review"
    return "available"


def apply_cross_speaker_fallback(voice_bank: dict[str, Any]) -> dict[str, Any]:
    """Annotate speakers that fall below min-clips with a fallback speaker.

    Runs *after* :func:`build_voice_bank` and mutates the nested speakers in
    place. For every speaker whose ``bank_status`` is ``needs_more_references``
    we pick the best ``available`` speaker as a fallback, and stamp its
    ``recommended_reference_*`` into a new ``cross_speaker_fallback`` dict.

    Rationale: in task-20260425-023015 spk_0002 had only 6 long segments and
    virtually no usable clone reference. Instead of failing silently, we fall
    back to another speaker's voice — imperfect but recoverable, and the UI
    can surface the override to the reviewer.
    """

    speakers = [
        speaker
        for speaker in voice_bank.get("speakers", [])
        if isinstance(speaker, dict)
    ]
    donors = [
        speaker
        for speaker in speakers
        if speaker.get("bank_status") == "available"
        and speaker.get("recommended_reference_path")
    ]
    if not donors:
        return voice_bank

    def _donor_score(donor: dict[str, Any]) -> tuple[int, float, float]:
        refs = donor.get("references", [])
        recommended_id = donor.get("recommended_reference_id")
        recommended_score = 0.0
        for ref in refs:
            if isinstance(ref, dict) and ref.get("reference_id") == recommended_id:
                recommended_score = float(ref.get("quality_score") or 0.0)
                break
        return (
            int(donor.get("usable_source_reference_count") or 0),
            float(donor.get("total_speech_sec") or 0.0),
            recommended_score,
        )

    donors_sorted = sorted(donors, key=_donor_score, reverse=True)

    for speaker in speakers:
        status = speaker.get("bank_status")
        if status not in ("needs_more_references", "missing_reference", "needs_manual_reference"):
            continue
        speaker_id = speaker.get("speaker_id") or speaker.get("profile_id")
        # Avoid picking the same speaker as donor for itself.
        candidates = [
            donor
            for donor in donors_sorted
            if (donor.get("speaker_id") or donor.get("profile_id")) != speaker_id
        ]
        if not candidates:
            continue
        donor = candidates[0]
        speaker["cross_speaker_fallback"] = {
            "donor_speaker_id": donor.get("speaker_id"),
            "donor_profile_id": donor.get("profile_id"),
            "donor_display_name": donor.get("display_name"),
            "reference_id": donor.get("recommended_reference_id"),
            "reference_path": donor.get("recommended_reference_path"),
            "reason": f"bank_status={status},donor_usable_clips={donor.get('usable_source_reference_count')}",
        }
    return voice_bank


def _selection_reason(
    *,
    score_parts: dict[str, float],
    benchmark_score: float | None,
    risk_flags: list[str],
) -> str:
    reason = (
        f"duration={score_parts['duration']:.2f},text={score_parts['text']:.2f},"
        f"rms={score_parts['rms']:.2f},risk={score_parts['risk']:.2f}"
    )
    if benchmark_score is not None:
        reason += f",benchmark={benchmark_score:.2f}"
    if risk_flags:
        reason += f",flags={','.join(risk_flags)}"
    return reason


def _bank_stats(*, speakers: list[dict[str, Any]], report_count: int) -> dict[str, Any]:
    references = [
        ref
        for speaker in speakers
        for ref in speaker.get("references", [])
        if isinstance(ref, dict)
    ]
    status_counts = _status_counts(speaker.get("bank_status") for speaker in speakers)
    return {
        "speaker_count": len(speakers),
        "speaker_with_id_count": sum(1 for speaker in speakers if speaker.get("speaker_id")),
        "reference_count": len(references),
        "source_reference_count": sum(1 for ref in references if ref.get("type") == "source_clip"),
        "composite_reference_count": sum(1 for ref in references if ref.get("type") == "composite"),
        "recommended_reference_count": sum(1 for speaker in speakers if speaker.get("recommended_reference_id")),
        "task_d_report_count": report_count,
        "bank_status_counts": status_counts,
    }


def _build_markdown_report(voice_bank: dict[str, Any]) -> str:
    stats = voice_bank["stats"]
    lines = [
        "# Voice Bank 生成报告",
        "",
        f"生成时间：{voice_bank['created_at']}",
        "",
        "## 汇总",
        "",
        f"- speaker 数：{stats['speaker_count']}",
        f"- 有 speaker_id 的 speaker：{stats['speaker_with_id_count']}",
        f"- reference 总数：{stats['reference_count']}",
        f"- source reference：{stats['source_reference_count']}",
        f"- composite reference：{stats['composite_reference_count']}",
        f"- 已推荐 reference 的 speaker：{stats['recommended_reference_count']}",
        f"- 纳入 Task D report 数：{stats['task_d_report_count']}",
        "",
        "## Speaker Reference 推荐",
        "",
        "| speaker | 状态 | 段数 | 语音时长 | reference | 推荐 reference | 推荐分 | 风险 |",
        "| --- | --- | ---: | ---: | ---: | --- | ---: | --- |",
    ]
    for speaker in voice_bank.get("speakers", []):
        refs = [ref for ref in speaker.get("references", []) if isinstance(ref, dict)]
        recommended = next(
            (ref for ref in refs if ref.get("reference_id") == speaker.get("recommended_reference_id")),
            None,
        )
        lines.append(
            "| {speaker} | {status} | {segments} | {speech} | {ref_count} | {recommended} | {score} | {risks} |".format(
                speaker=speaker.get("speaker_id") or speaker.get("source_label") or speaker.get("profile_id"),
                status=speaker.get("bank_status"),
                segments=speaker.get("segment_count") or 0,
                speech=speaker.get("total_speech_sec") or 0,
                ref_count=len(refs),
                recommended=(recommended or {}).get("reference_id") or "-",
                score=(recommended or {}).get("quality_score") or "-",
                risks=", ".join((recommended or {}).get("risk_flags") or []) or "-",
            )
        )
    lines.extend(
        [
            "",
            "## 后续动作",
            "",
            "1. 对 `available` speaker，可直接把推荐 reference 纳入 repair candidate grid。",
            "2. 对 `review` speaker，应在 Dubbing Review UI 中试听推荐 reference 和 composite reference。",
            "3. 对 `needs_speaker_review` 或 `missing_reference`，优先做人工 speaker 映射或上传 reference。",
            "4. 下一步可用同一份 voice bank 跑 `qwen3tts` 小样本 benchmark，再决定是否启用模型 fallback。",
            "",
        ]
    )
    return "\n".join(lines)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, list):
        return {"segments": payload}
    return {}


def _write_json(payload: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _status_counts(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        if value is None:
            continue
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _weighted_status_score(counts: dict[str, int]) -> float:
    total = sum(counts.values())
    if total <= 0:
        return 0.0
    return (
        counts.get("passed", 0) * 1.0
        + counts.get("review", 0) * 0.55
        + counts.get("failed", 0) * 0.0
    ) / total


def _norm_path(path: str | Path) -> str:
    return str(Path(path).expanduser().resolve())


def _mean(values: list[float]) -> float | None:
    return round(float(statistics.fmean(values)), 4) if values else None


def _median(values: list[float]) -> float | None:
    return round(float(statistics.median(values)), 4) if values else None


def _round_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return None


__all__ = [
    "VoiceBankArtifacts",
    "VoiceBankRequest",
    "VoiceBankResult",
    "apply_cross_speaker_fallback",
    "build_voice_bank",
]
