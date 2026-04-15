from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..translation.backend import output_tag_for_language
from ..utils.files import ensure_directory


def _seconds_to_srt_time(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds % 1) * 1000))
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _write_json(output_path: Path, payload: dict[str, Any]) -> Path:
    ensure_directory(output_path.parent)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output_path


def write_ocr_translation_bundle(
    *,
    output_dir: Path,
    target_lang: str,
    backend_name: str,
    events: list[dict[str, Any]],
) -> tuple[Path, Path, Path]:
    output_dir = ensure_directory(output_dir)
    output_tag = output_tag_for_language(target_lang)
    json_path = output_dir / f"ocr_subtitles.{output_tag}.json"
    srt_path = output_dir / f"ocr_subtitles.{output_tag}.srt"
    manifest_path = output_dir / "ocr-translate-manifest.json"

    payload = {
        "target_lang": target_lang,
        "backend_name": backend_name,
        "events": events,
    }
    _write_json(json_path, payload)

    srt_blocks = []
    for index, event in enumerate(events, start=1):
        text = str(event.get("translated_text") or event.get("text") or "").strip()
        srt_blocks.append(
            "\n".join(
                [
                    str(index),
                    f"{_seconds_to_srt_time(float(event['start']))} --> {_seconds_to_srt_time(float(event['end']))}",
                    text,
                ]
            )
        )
    srt_path.write_text("\n\n".join(srt_blocks) + ("\n" if srt_blocks else ""), encoding="utf-8")

    _write_json(
        manifest_path,
        {
            "status": "succeeded",
            "target_lang": target_lang,
            "backend_name": backend_name,
            "artifacts": {
                "json_path": str(json_path),
                "srt_path": str(srt_path),
            },
            "event_count": len(events),
        },
    )
    return json_path, srt_path, manifest_path
