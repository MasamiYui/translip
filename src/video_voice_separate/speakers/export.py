from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..pipeline.manifest import now_iso
from ..types import MediaInfo, SpeakerRegistryRequest


def write_json(payload: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output_path


def build_speaker_manifest(
    *,
    request: SpeakerRegistryRequest,
    media_info: MediaInfo | None,
    profiles_path: Path,
    matches_path: Path,
    registry_snapshot_path: Path,
    started_at: str,
    finished_at: str,
    elapsed_sec: float,
    stats: dict[str, Any],
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "job_id": profiles_path.parent.name,
        "input": {
            "audio_path": str(request.audio_path),
            "segments_path": str(request.segments_path),
            "registry_path": str(request.registry_path) if request.registry_path else None,
            "duration_sec": round(media_info.duration_sec, 3) if media_info else None,
            "sample_rate": media_info.sample_rate if media_info else None,
            "channels": media_info.channels if media_info else None,
            "format_name": media_info.format_name if media_info else None,
        },
        "request": {
            "device": request.device,
            "top_k": request.top_k,
            "update_registry": request.update_registry,
        },
        "resolved": stats,
        "artifacts": {
            "speaker_profiles": str(profiles_path),
            "speaker_matches": str(matches_path),
            "speaker_registry": str(registry_snapshot_path),
        },
        "timing": {
            "started_at": started_at,
            "finished_at": finished_at,
            "elapsed_sec": round(elapsed_sec, 3),
        },
        "status": "failed" if error else "succeeded",
        "error": error,
    }


__all__ = ["build_speaker_manifest", "now_iso", "write_json"]
