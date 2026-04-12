from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from ..pipeline.manifest import now_iso
from ..types import DubbingRequest


def write_json(payload: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output_path


def render_demo_audio(segment_paths: list[Path], output_path: Path, *, gap_sec: float = 0.2) -> Path | None:
    if not segment_paths:
        return None
    sample_rate: int | None = None
    parts: list[np.ndarray] = []
    for index, segment_path in enumerate(segment_paths):
        waveform, sr = sf.read(segment_path, dtype="float32", always_2d=False)
        if waveform.ndim == 2:
            waveform = waveform.mean(axis=1)
        if sample_rate is None:
            sample_rate = sr
        elif sr != sample_rate:
            raise ValueError("All synthesized segments must share the same sample rate")
        parts.append(waveform.astype(np.float32))
        if index != len(segment_paths) - 1:
            parts.append(np.zeros(int(gap_sec * sample_rate), dtype=np.float32))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(output_path, np.concatenate(parts), sample_rate)
    return output_path


def build_dubbing_report(
    *,
    request: DubbingRequest,
    target_lang: str,
    backend_name: str,
    resolved_model: str,
    resolved_device: str,
    reference: dict[str, Any],
    segments: list[dict[str, Any]],
) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    for segment in segments:
        status = str(segment["overall_status"])
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "input": {
            "translation_path": str(request.translation_path),
            "profiles_path": str(request.profiles_path),
        },
        "backend": {
            "tts_backend": backend_name,
            "model": resolved_model,
            "device": resolved_device,
            "target_lang": target_lang,
        },
        "speaker_id": request.speaker_id,
        "reference": reference,
        "stats": {
            "segment_count": len(segments),
            "overall_status_counts": status_counts,
        },
        "segments": segments,
    }


def build_dubbing_manifest(
    *,
    request: DubbingRequest,
    target_lang: str,
    report_path: Path,
    demo_audio_path: Path | None,
    started_at: str,
    finished_at: str,
    elapsed_sec: float,
    resolved: dict[str, Any],
    stats: dict[str, Any],
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "job_id": report_path.parent.name,
        "input": {
            "translation_path": str(request.translation_path),
            "profiles_path": str(request.profiles_path),
            "reference_clip_path": str(request.reference_clip_path) if request.reference_clip_path else None,
        },
        "request": {
            "speaker_id": request.speaker_id,
            "backend": request.backend,
            "device": request.device,
            "segment_ids": request.segment_ids,
            "max_segments": request.max_segments,
            "keep_intermediate": request.keep_intermediate,
            "backread_model": request.backread_model,
        },
        "resolved": resolved | stats | {"target_lang": target_lang},
        "artifacts": {
            "report_json": str(report_path),
            "demo_audio": str(demo_audio_path) if demo_audio_path is not None else None,
        },
        "timing": {
            "started_at": started_at,
            "finished_at": finished_at,
            "elapsed_sec": round(elapsed_sec, 3),
        },
        "status": "failed" if error else "succeeded",
        "error": error,
    }


__all__ = [
    "build_dubbing_manifest",
    "build_dubbing_report",
    "now_iso",
    "render_demo_audio",
    "write_json",
]
