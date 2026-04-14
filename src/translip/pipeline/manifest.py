from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ..types import MediaInfo, RouteDecision, SeparationRequest


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def build_manifest(
    request: SeparationRequest,
    media_info: MediaInfo | None,
    route: RouteDecision,
    voice_path: Path,
    background_path: Path,
    started_at: str,
    finished_at: str,
    elapsed_sec: float,
    backends: dict[str, str],
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "job_id": voice_path.parent.name,
        "input": {
            "path": str(Path(request.input_path)),
            "media_type": media_info.media_type if media_info else None,
            "audio_stream_index": request.audio_stream_index,
            "duration_sec": round(media_info.duration_sec, 3) if media_info else None,
            "sample_rate": media_info.sample_rate if media_info else None,
            "channels": media_info.channels if media_info else None,
            "format_name": media_info.format_name if media_info else None,
        },
        "request": {
            "mode": request.mode,
            "output_format": request.output_format,
            "quality": request.quality,
            "music_model": request.music_model,
            "enhance_voice": request.enhance_voice,
            "device": request.device,
        },
        "resolved": {
            "route": route.route,
            "reason": route.reason,
            "metrics": route.metrics,
            **backends,
        },
        "artifacts": {
            "voice": str(voice_path),
            "background": str(background_path),
        },
        "timing": {
            "started_at": started_at,
            "finished_at": finished_at,
            "elapsed_sec": round(elapsed_sec, 3),
        },
        "status": "failed" if error else "succeeded",
        "error": error,
    }


def write_manifest(manifest: dict[str, Any], manifest_path: Path) -> Path:
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest_path
