from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from ..speaker_embedding import normalize_embedding

MATCH_THRESHOLD = 0.55
REVIEW_THRESHOLD = 0.35
SECOND_MARGIN_THRESHOLD = 0.05
MAX_EXEMPLARS = 12


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _default_registry(*, backend_name: str, embedding_dim: int) -> dict[str, Any]:
    return {
        "version": 1,
        "backend": {
            "speaker_backend": backend_name,
            "embedding_dim": embedding_dim,
        },
        "speakers": [],
    }


def load_registry(path: Path | None, *, backend_name: str, embedding_dim: int) -> dict[str, Any]:
    if path is None or not path.exists():
        return _default_registry(backend_name=backend_name, embedding_dim=embedding_dim)
    return json.loads(path.read_text(encoding="utf-8"))


def write_registry(registry: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _cosine_list(a: list[float], b: list[float]) -> float:
    return float(np.dot(np.asarray(a, dtype=np.float32), np.asarray(b, dtype=np.float32)))


def _speaker_score(profile_embedding: list[float], speaker: dict[str, Any]) -> float:
    scores: list[float] = []
    prototype = speaker.get("prototype_embedding")
    if prototype:
        scores.append(_cosine_list(profile_embedding, prototype))
    for exemplar in speaker.get("exemplar_embeddings", []):
        scores.append(_cosine_list(profile_embedding, exemplar))
    return max(scores) if scores else -1.0


def _decision(score: float, second_best: float) -> str:
    if score >= MATCH_THRESHOLD and (score - second_best) >= SECOND_MARGIN_THRESHOLD:
        return "matched"
    if score >= REVIEW_THRESHOLD:
        return "review"
    return "new_speaker"


def _registry_similarity_floor(registry_speakers: list[dict[str, Any]]) -> float:
    prototypes = [speaker.get("prototype_embedding") for speaker in registry_speakers if speaker.get("prototype_embedding")]
    if len(prototypes) < 2:
        return 0.25
    values = [np.asarray(item, dtype=np.float32) for item in prototypes]
    max_similarity = -1.0
    for index, left in enumerate(values):
        for right in values[index + 1 :]:
            max_similarity = max(max_similarity, float(np.dot(left, right)))
    return max_similarity if max_similarity >= 0.0 else 0.25


def _decision_thresholds(registry_speakers: list[dict[str, Any]]) -> tuple[float, float]:
    floor = _registry_similarity_floor(registry_speakers)
    matched = max(MATCH_THRESHOLD, floor + 0.15)
    review = max(REVIEW_THRESHOLD, floor + 0.05)
    return matched, review


def match_profiles(
    profiles_payload: dict[str, Any],
    registry: dict[str, Any],
    *,
    top_k: int,
) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    registry_speakers = [speaker for speaker in registry.get("speakers", []) if speaker.get("status") != "disabled"]
    matched_threshold, review_threshold = _decision_thresholds(registry_speakers)
    for profile in profiles_payload.get("profiles", []):
        profile_embedding = profile.get("prototype_embedding")
        if not profile_embedding:
            matches.append(
                {
                    "profile_id": profile["profile_id"],
                    "decision": "new_speaker",
                    "matched_speaker_id": None,
                    "score": None,
                    "margin_to_second": None,
                    "top_k": [],
                }
            )
            continue

        scored = [
            {
                "speaker_id": speaker["speaker_id"],
                "score": round(_speaker_score(profile_embedding, speaker), 6),
                "display_name": speaker.get("display_name"),
            }
            for speaker in registry_speakers
        ]
        scored.sort(key=lambda item: item["score"], reverse=True)
        top_candidates = scored[:top_k]
        best = top_candidates[0]["score"] if top_candidates else -1.0
        second = top_candidates[1]["score"] if len(top_candidates) > 1 else -1.0
        decision = (
            "matched"
            if best >= matched_threshold and (best - second) >= SECOND_MARGIN_THRESHOLD
            else "review"
            if best >= review_threshold
            else "new_speaker"
        )
        matches.append(
            {
                "profile_id": profile["profile_id"],
                "decision": decision,
                "matched_speaker_id": top_candidates[0]["speaker_id"] if decision == "matched" and top_candidates else None,
                "score": round(best, 6) if top_candidates else None,
                "margin_to_second": round(best - second, 6) if top_candidates else None,
                "matched_threshold": round(matched_threshold, 6),
                "review_threshold": round(review_threshold, 6),
                "top_k": top_candidates,
            }
        )
    return {"matches": matches}


def _next_speaker_id(registry: dict[str, Any]) -> str:
    speaker_ids = [speaker["speaker_id"] for speaker in registry.get("speakers", [])]
    if not speaker_ids:
        return "spk_0000"
    numeric = [int(item.split("_")[1]) for item in speaker_ids if item.startswith("spk_")]
    return f"spk_{(max(numeric) + 1) if numeric else 0:04d}"


def _copy_reference_clips_to_registry(
    profile: dict[str, Any],
    speaker_id: str,
    registry_root: Path,
) -> list[str]:
    dest_dir = registry_root / "registry_clips" / speaker_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    stored_paths: list[str] = []
    for index, clip in enumerate(profile.get("reference_clips", []), start=1):
        clip_path = clip.get("path")
        if not clip_path:
            continue
        src = Path(clip_path)
        if not src.exists():
            continue
        dst = dest_dir / f"clip_{index:04d}.wav"
        shutil.copy2(src, dst)
        stored_paths.append(str(dst.relative_to(registry_root)))
    return stored_paths


def _merge_embeddings(existing: list[list[float]], new_embedding: list[float]) -> tuple[list[list[float]], list[float]]:
    exemplars = [np.asarray(item, dtype=np.float32) for item in existing]
    exemplars.append(np.asarray(new_embedding, dtype=np.float32))
    if len(exemplars) > MAX_EXEMPLARS:
        exemplars = exemplars[-MAX_EXEMPLARS:]
    matrix = np.stack(exemplars).astype(np.float32)
    prototype = normalize_embedding(matrix.mean(axis=0))
    return (
        [[round(float(value), 6) for value in item.tolist()] for item in exemplars],
        [round(float(value), 6) for value in prototype.tolist()],
    )


def apply_registry_updates(
    profiles_payload: dict[str, Any],
    matches_payload: dict[str, Any],
    registry: dict[str, Any],
    *,
    registry_root: Path | None,
    update_registry: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    profiles_by_id = {profile["profile_id"]: profile for profile in profiles_payload.get("profiles", [])}
    speakers = registry.setdefault("speakers", [])

    for match in matches_payload.get("matches", []):
        profile = profiles_by_id[match["profile_id"]]
        decision = match["decision"]
        profile_embedding = profile.get("prototype_embedding")
        if not profile_embedding:
            profile["status"] = "unmatched"
            continue

        if not update_registry:
            profile["status"] = decision
            profile["speaker_id"] = match.get("matched_speaker_id")
            continue

        if decision == "matched" and match.get("matched_speaker_id"):
            speaker = next(item for item in speakers if item["speaker_id"] == match["matched_speaker_id"])
            exemplars, prototype = _merge_embeddings(
                speaker.get("exemplar_embeddings", []),
                profile_embedding,
            )
            speaker["exemplar_embeddings"] = exemplars
            speaker["prototype_embedding"] = prototype
            speaker["updated_at"] = _now_iso()
            if registry_root is not None:
                copied = _copy_reference_clips_to_registry(profile, speaker["speaker_id"], registry_root)
                for path in copied:
                    if path not in speaker.setdefault("reference_clips", []):
                        speaker["reference_clips"].append(path)
            profile["status"] = "matched"
            profile["speaker_id"] = speaker["speaker_id"]
            continue

        if decision == "new_speaker":
            speaker_id = _next_speaker_id(registry)
            entry = {
                "speaker_id": speaker_id,
                "display_name": speaker_id,
                "status": "confirmed",
                "aliases": [],
                "prototype_embedding": profile_embedding,
                "exemplar_embeddings": [profile_embedding],
                "reference_clips": [],
                "created_at": _now_iso(),
                "updated_at": _now_iso(),
            }
            if registry_root is not None:
                entry["reference_clips"] = _copy_reference_clips_to_registry(profile, speaker_id, registry_root)
            speakers.append(entry)
            profile["status"] = "registered"
            profile["speaker_id"] = speaker_id
            match["matched_speaker_id"] = speaker_id
            continue

        profile["status"] = "review"
        profile["speaker_id"] = match.get("matched_speaker_id")

    return profiles_payload, registry
