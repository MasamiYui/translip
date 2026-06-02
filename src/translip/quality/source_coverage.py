"""Pre-task-c source-speech reconciliation.

:mod:`translip.quality.dub_qa` anchors its "should be dubbed" universe on the ASR
transcript (task-c translation). So a real spoken line that VAD / diarization /
short-utterance filtering dropped *before* task-c can never be flagged undubbed —
it is structurally invisible to the evaluation. This module breaks that ceiling:
it runs a cheap VAD pass on the stage1 dialogue stem and compares the detected
speech against the ASR segment spans, surfacing windows where the audio clearly
contains speech that no transcript line covers.

Everything is best-effort: if the stem, the segments, or the VAD backend are
absent, :func:`build_source_coverage` returns ``None`` and dub_qa simply omits the
block — it never blocks the rest of the report.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..utils.io import read_json

logger = logging.getLogger(__name__)

# A transcript that covers less than this share of detected speech, or any single
# uncovered speech window at least this long, is worth the operator's attention.
SOURCE_COVERAGE_MIN_RATIO = 0.90
UNCOVERED_WINDOW_MIN_SEC = 1.0
# Tolerance when matching ASR spans to VAD speech (ASR boundaries are imprecise).
ASR_SPAN_PAD_SEC = 0.20
_VAD_SAMPLE_RATE = 16000
_MAX_REPORTED_WINDOWS = 20


def build_source_coverage(
    *,
    pipeline_root: Path,
    mix_report: dict[str, Any],
    source_lang: str = "zh",
) -> dict[str, Any] | None:
    """Reconcile detected source speech against the ASR transcript spans."""
    stem = _resolve_dialogue_stem(pipeline_root, mix_report)
    asr_spans = _load_asr_spans(pipeline_root, source_lang)
    if stem is None or not asr_spans:
        return None
    speech = _vad_speech_windows(stem)
    if speech is None:
        return None  # VAD backend unavailable — degrade silently
    result = reconcile_speech(speech_windows=speech, asr_spans=asr_spans)
    result["source_stem"] = str(stem)
    return result


def reconcile_speech(
    *,
    speech_windows: list[tuple[float, float]],
    asr_spans: list[tuple[float, float]],
) -> dict[str, Any]:
    """Pure reconciliation: which detected speech has no transcript line over it.

    ``speech_windows`` are VAD-detected speech intervals (seconds); ``asr_spans``
    are transcript segment intervals. Returns coverage stats + the uncovered
    windows long enough to matter. Kept free of I/O so it is unit-testable.
    """
    merged_asr = _merge_intervals(asr_spans, pad=ASR_SPAN_PAD_SEC)
    detected = sum(max(0.0, end - start) for start, end in speech_windows)
    uncovered: list[tuple[float, float]] = []
    for start, end in sorted(speech_windows):
        cursor = start
        for span_start, span_end in merged_asr:
            if span_end <= cursor:
                continue
            if span_start >= end:
                break
            if span_start > cursor:
                uncovered.append((cursor, min(span_start, end)))
            cursor = max(cursor, span_end)
            if cursor >= end:
                break
        if cursor < end:
            uncovered.append((cursor, end))

    uncovered_total = sum(end - start for start, end in uncovered)
    transcribed = max(0.0, detected - uncovered_total)
    coverage = round(transcribed / detected, 4) if detected > 0 else None
    long_windows = [(s, e) for s, e in uncovered if (e - s) >= UNCOVERED_WINDOW_MIN_SEC]

    low_coverage = coverage is not None and coverage < SOURCE_COVERAGE_MIN_RATIO
    status = "review" if (low_coverage or long_windows) else "ok"
    return {
        "status": status,
        "transcript_coverage": coverage,
        "detected_speech_sec": round(detected, 3),
        "transcribed_speech_sec": round(transcribed, 3),
        "uncovered_speech_sec": round(detected - transcribed, 3),
        "uncovered_window_count": len(long_windows),
        "uncovered_windows": [
            {"start": round(s, 3), "end": round(e, 3), "duration": round(e - s, 3)}
            for s, e in long_windows[:_MAX_REPORTED_WINDOWS]
        ],
        "thresholds": {
            "min_coverage": SOURCE_COVERAGE_MIN_RATIO,
            "min_window_sec": UNCOVERED_WINDOW_MIN_SEC,
        },
    }


# --------------------------------------------------------------------------- #
# Resolution / IO helpers
# --------------------------------------------------------------------------- #


def _resolve_dialogue_stem(pipeline_root: Path, mix_report: dict[str, Any]) -> Path | None:
    candidates: list[Path] = []
    input_block = mix_report.get("input") if isinstance(mix_report.get("input"), dict) else {}
    background = input_block.get("background_path") if isinstance(input_block, dict) else None
    if background:
        background_path = Path(str(background))
        suffixes = _dedupe([background_path.suffix, ".mp3", ".wav", ".flac", ".m4a", ".aac", ".opus"])
        for stem_name in ("voice", "dialogue", "dialog", "vocals"):
            for suffix in suffixes:
                candidates.append(background_path.with_name(f"{stem_name}{suffix}"))
    stage1 = Path(pipeline_root) / "stage1"
    if stage1.exists():
        for stem_name in ("voice", "dialogue", "vocals"):
            candidates.extend(sorted(stage1.glob(f"*/{stem_name}.*")))
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _load_asr_spans(pipeline_root: Path, source_lang: str) -> list[tuple[float, float]]:
    spans: list[tuple[float, float]] = []
    root = Path(pipeline_root)
    for base in ("task-a", "asr-ocr-correct"):
        directory = root / base
        if not directory.exists():
            continue
        for path in sorted(directory.rglob(f"segments.{source_lang}*.json")):
            payload = read_json(path)
            if not isinstance(payload, dict):
                continue
            for segment in payload.get("segments", []):
                if not isinstance(segment, dict):
                    continue
                start = segment.get("start")
                end = segment.get("end")
                if isinstance(start, (int, float)) and isinstance(end, (int, float)) and end > start:
                    spans.append((float(start), float(end)))
    return spans


def _vad_speech_windows(audio_path: Path) -> list[tuple[float, float]] | None:
    try:
        from faster_whisper.audio import decode_audio
        from faster_whisper.vad import VadOptions, get_speech_timestamps
    except Exception as exc:  # pragma: no cover - optional backend
        logger.warning("Source-coverage VAD backend unavailable: %s", exc)
        return None
    try:
        waveform = decode_audio(str(audio_path), sampling_rate=_VAD_SAMPLE_RATE)
        timestamps = get_speech_timestamps(waveform, vad_options=VadOptions(), sampling_rate=_VAD_SAMPLE_RATE)
    except Exception as exc:  # pragma: no cover - decode/VAD failure should not block QA
        logger.warning("Source-coverage VAD failed for %s: %s", audio_path, exc)
        return None
    return [
        (float(ts["start"]) / _VAD_SAMPLE_RATE, float(ts["end"]) / _VAD_SAMPLE_RATE)
        for ts in timestamps
        if isinstance(ts, dict) and "start" in ts and "end" in ts
    ]


def _merge_intervals(intervals: list[tuple[float, float]], *, pad: float = 0.0) -> list[tuple[float, float]]:
    if not intervals:
        return []
    padded = sorted((start - pad, end + pad) for start, end in intervals)
    merged: list[list[float]] = [list(padded[0])]
    for start, end in padded[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(start, end) for start, end in merged]


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


__all__ = [
    "SOURCE_COVERAGE_MIN_RATIO",
    "UNCOVERED_WINDOW_MIN_SEC",
    "build_source_coverage",
    "reconcile_speech",
]
