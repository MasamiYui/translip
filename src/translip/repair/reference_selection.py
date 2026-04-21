from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..dubbing.reference import ReferenceCandidate, select_reference_candidates


@dataclass(slots=True)
class ReferencePlan:
    speaker_id: str
    current_reference_path: str | None
    recommended_reference_path: str | None
    speaker_failed_count: int
    repair_item_count: int
    candidates: list[dict[str, Any]]

    def to_payload(self) -> dict[str, Any]:
        return {
            "speaker_id": self.speaker_id,
            "current_reference_path": self.current_reference_path,
            "recommended_reference_path": self.recommended_reference_path,
            "speaker_failed_count": self.speaker_failed_count,
            "repair_item_count": self.repair_item_count,
            "candidates": self.candidates,
        }


def build_reference_plan(
    *,
    profiles_payload: dict[str, Any],
    speaker_id: str,
    repair_items: list[dict[str, Any]],
    current_reference_path: str | None,
) -> ReferencePlan:
    try:
        candidates = select_reference_candidates(profiles_payload=profiles_payload, speaker_id=speaker_id)
    except ValueError:
        candidates = []

    speaker_failed_count = sum(
        1 for item in repair_items if "speaker_failed" in set(item.get("failure_reasons", []))
    )
    scored = [_candidate_payload(candidate, current_reference_path=current_reference_path) for candidate in candidates]
    recommended = _recommended_reference(scored, current_reference_path=current_reference_path)
    return ReferencePlan(
        speaker_id=speaker_id,
        current_reference_path=current_reference_path,
        recommended_reference_path=recommended,
        speaker_failed_count=speaker_failed_count,
        repair_item_count=len(repair_items),
        candidates=scored,
    )


def _candidate_payload(candidate: ReferenceCandidate, *, current_reference_path: str | None) -> dict[str, Any]:
    path = str(candidate.path)
    return {
        "path": path,
        "profile_id": candidate.profile_id,
        "duration_sec": candidate.duration_sec,
        "text": candidate.text,
        "rms": candidate.rms,
        "quality_score": candidate.score,
        "selection_reason": candidate.selection_reason,
        "is_current": _same_path(path, current_reference_path),
    }


def _recommended_reference(candidates: list[dict[str, Any]], *, current_reference_path: str | None) -> str | None:
    if not candidates:
        return None
    alternatives = [row for row in candidates if not row.get("is_current")]
    if alternatives and candidates[0].get("is_current"):
        return str(alternatives[0]["path"])
    return str(candidates[0]["path"])


def _same_path(path_a: str | None, path_b: str | None) -> bool:
    if not path_a or not path_b:
        return False
    return Path(path_a).expanduser().resolve() == Path(path_b).expanduser().resolve()


__all__ = ["ReferencePlan", "build_reference_plan"]
