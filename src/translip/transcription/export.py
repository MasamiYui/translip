from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..pipeline.manifest import now_iso
from ..types import MediaInfo, TranscriptionRequest, TranscriptionSegment


def segments_payload(
    *,
    request: TranscriptionRequest,
    media_info: MediaInfo,
    segments: list[TranscriptionSegment],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "input": {
            "path": str(request.input_path),
            "duration_sec": round(media_info.duration_sec, 3),
            "sample_rate": media_info.sample_rate,
            "channels": media_info.channels,
            "format_name": media_info.format_name,
        },
        "model": {
            "asr_backend": metadata.get("asr_backend"),
            "asr_model": metadata.get("asr_model"),
            "asr_device": metadata.get("asr_device"),
            "speaker_backend": metadata.get("speaker_backend"),
            "speaker_device": metadata.get("speaker_device"),
            "detected_language": metadata.get("detected_language"),
        },
        "stats": {
            "segment_count": len(segments),
            "speaker_count": len({segment.speaker_label for segment in segments}),
        },
        "segments": [
            {
                "id": segment.segment_id,
                "start": round(segment.start, 3),
                "end": round(segment.end, 3),
                "duration": round(segment.duration, 3),
                "speaker_label": segment.speaker_label,
                "text": segment.text,
                "language": segment.language,
            }
            for segment in segments
        ],
    }


def write_segments_json(payload: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path


def _srt_timestamp(seconds: float) -> str:
    millis = int(round(seconds * 1000))
    hours, remainder = divmod(millis, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, ms = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def write_segments_srt(segments: list[TranscriptionSegment], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for index, segment in enumerate(segments, start=1):
        lines.extend(
            [
                str(index),
                f"{_srt_timestamp(segment.start)} --> {_srt_timestamp(segment.end)}",
                f"[{segment.speaker_label}] {segment.text}",
                "",
            ]
        )
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def build_transcription_manifest(
    *,
    request: TranscriptionRequest,
    media_info: MediaInfo | None,
    segments_path: Path,
    srt_path: Path | None,
    started_at: str,
    finished_at: str,
    elapsed_sec: float,
    metadata: dict[str, Any],
    error: str | None = None,
) -> dict[str, Any]:
    speaker_count = metadata.get("speaker_count", 0)
    segment_count = metadata.get("segment_count", 0)
    return {
        "job_id": segments_path.parent.name,
        "input": {
            "path": str(request.input_path),
            "media_type": media_info.media_type if media_info else None,
            "audio_stream_index": request.audio_stream_index,
            "duration_sec": round(media_info.duration_sec, 3) if media_info else None,
            "sample_rate": media_info.sample_rate if media_info else None,
            "channels": media_info.channels if media_info else None,
            "format_name": media_info.format_name if media_info else None,
        },
        "request": {
            "language": request.language,
            "asr_model": request.asr_model,
            "device": request.device,
            "write_srt": request.write_srt,
            "vad_filter": request.vad_filter,
            "vad_min_silence_duration_ms": request.vad_min_silence_duration_ms,
            "beam_size": request.beam_size,
            "best_of": request.best_of,
            "temperature": request.temperature,
            "condition_on_previous_text": request.condition_on_previous_text,
        },
        "resolved": {
            "asr_backend": metadata.get("asr_backend"),
            "asr_device": metadata.get("asr_device"),
            "detected_language": metadata.get("detected_language"),
            "speaker_backend": metadata.get("speaker_backend"),
            "speaker_device": metadata.get("speaker_device"),
            "segment_count": segment_count,
            "speaker_count": speaker_count,
        },
        "artifacts": {
            "segments_json": str(segments_path),
            "segments_srt": str(srt_path) if srt_path else None,
        },
        "timing": {
            "started_at": started_at,
            "finished_at": finished_at,
            "elapsed_sec": round(elapsed_sec, 3),
        },
        "status": "failed" if error else "succeeded",
        "error": error,
    }


def write_manifest(manifest: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path


__all__ = [
    "build_transcription_manifest",
    "now_iso",
    "segments_payload",
    "write_manifest",
    "write_segments_json",
    "write_segments_srt",
]
