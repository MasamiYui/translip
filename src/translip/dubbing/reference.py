from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from .backend import ReferencePackage

IDEAL_REFERENCE_MIN_SEC = 8.0
IDEAL_REFERENCE_MAX_SEC = 10.5
HARD_REFERENCE_MIN_SEC = 5.0
HARD_REFERENCE_MAX_SEC = 15.0
REFERENCE_TAIL_SILENCE_SEC = 1.0
REFERENCE_MAX_SPEECH_SEC = 11.0


@dataclass(slots=True)
class ReferenceCandidate:
    profile_id: str
    speaker_id: str
    path: Path
    text: str
    duration_sec: float
    rms: float
    score: float
    selection_reason: str


def load_profiles_payload(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def select_reference_candidates(
    *,
    profiles_payload: dict[str, Any],
    speaker_id: str,
    reference_clip_path: Path | None = None,
) -> list[ReferenceCandidate]:
    profile = _find_profile(profiles_payload, speaker_id)
    candidates = _candidate_rows(profile)
    if reference_clip_path is not None:
        normalized = reference_clip_path.expanduser().resolve()
        filtered = [candidate for candidate in candidates if candidate.path == normalized]
        if not filtered:
            raise ValueError(
                f"Reference clip override is not present in speaker profile {speaker_id}: {normalized}"
            )
        return filtered
    if not candidates:
        raise ValueError(f"No usable reference clips found for speaker {speaker_id}")
    return sorted(candidates, key=lambda item: item.score, reverse=True)


def prepare_reference_package(
    candidate: ReferenceCandidate,
    *,
    output_path: Path,
) -> ReferencePackage:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    waveform, sample_rate = sf.read(candidate.path, dtype="float32", always_2d=False)
    if waveform.ndim == 2:
        waveform = waveform.mean(axis=1)
    max_samples = int(REFERENCE_MAX_SPEECH_SEC * sample_rate)
    clipped = waveform[:max_samples] if waveform.size > max_samples else waveform
    silence = np.zeros(int(REFERENCE_TAIL_SILENCE_SEC * sample_rate), dtype=np.float32)
    prepared = np.concatenate([clipped.astype(np.float32), silence])
    sf.write(output_path, prepared, sample_rate)
    return ReferencePackage(
        speaker_id=candidate.speaker_id,
        profile_id=candidate.profile_id,
        original_audio_path=candidate.path,
        prepared_audio_path=output_path,
        text=candidate.text.strip(),
        duration_sec=round(float(len(prepared) / sample_rate), 3),
        score=round(candidate.score, 3),
        selection_reason=candidate.selection_reason,
    )


def _find_profile(profiles_payload: dict[str, Any], speaker_id: str) -> dict[str, Any]:
    for profile in profiles_payload.get("profiles", []):
        if isinstance(profile, dict) and str(profile.get("speaker_id")) == speaker_id:
            return profile
    raise ValueError(f"Speaker id not found in speaker profiles: {speaker_id}")


def _candidate_rows(profile: dict[str, Any]) -> list[ReferenceCandidate]:
    speaker_id = str(profile.get("speaker_id") or "")
    profile_id = str(profile.get("profile_id") or "")
    candidates: list[ReferenceCandidate] = []
    for raw in profile.get("reference_clips", []):
        if not isinstance(raw, dict):
            continue
        raw_path = raw.get("path")
        raw_text = str(raw.get("text") or "").strip()
        if not raw_path or not raw_text:
            continue
        duration_sec = float(raw.get("duration") or 0.0)
        if duration_sec < HARD_REFERENCE_MIN_SEC or duration_sec > HARD_REFERENCE_MAX_SEC:
            continue
        rms = float(raw.get("rms") or 0.0)
        score, selection_reason = _score_reference(
            duration_sec=duration_sec,
            text=raw_text,
            rms=rms,
        )
        candidates.append(
            ReferenceCandidate(
                profile_id=profile_id,
                speaker_id=speaker_id,
                path=Path(raw_path).expanduser().resolve(),
                text=raw_text,
                duration_sec=round(duration_sec, 3),
                rms=rms,
                score=score,
                selection_reason=selection_reason,
            )
        )
    return candidates


def _score_reference(*, duration_sec: float, text: str, rms: float) -> tuple[float, str]:
    duration_score = _duration_score(duration_sec)
    text_score = _text_score(text)
    rms_score = _rms_score(rms)
    risk_penalty = _risk_penalty(text)
    total = (duration_score * 0.5) + (text_score * 0.3) + (rms_score * 0.2) - risk_penalty
    reason = (
        f"duration={duration_score:.2f},text={text_score:.2f},"
        f"rms={rms_score:.2f},risk=-{risk_penalty:.2f}"
    )
    return round(total, 4), reason


def _duration_score(duration_sec: float) -> float:
    if IDEAL_REFERENCE_MIN_SEC <= duration_sec <= IDEAL_REFERENCE_MAX_SEC:
        return 1.0
    if HARD_REFERENCE_MIN_SEC <= duration_sec < IDEAL_REFERENCE_MIN_SEC:
        return 0.7
    if IDEAL_REFERENCE_MAX_SEC < duration_sec <= 12.0:
        return 0.8
    if 12.0 < duration_sec <= HARD_REFERENCE_MAX_SEC:
        overflow = duration_sec - 12.0
        return max(0.1, 0.6 - (overflow * 0.18))
    return 0.0


def _text_score(text: str) -> float:
    compact = re.sub(r"\s+", "", text)
    if len(compact) >= 16:
        return 1.0
    if len(compact) >= 8:
        return 0.8
    if len(compact) >= 4:
        return 0.55
    return 0.2


def _rms_score(rms: float) -> float:
    if 0.02 <= rms <= 0.25:
        return 1.0
    if 0.01 <= rms <= 0.35:
        return 0.7
    if 0.005 <= rms <= 0.5:
        return 0.4
    return 0.1


def _risk_penalty(text: str) -> float:
    patterns = [
        r"[!！?？~]{2,}",
        r"(哈哈|呵呵|hahaha|lol)",
    ]
    lowered = text.lower()
    return 0.35 if any(re.search(pattern, lowered) for pattern in patterns) else 0.0
