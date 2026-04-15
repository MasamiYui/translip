from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..translation.backend import BackendSegmentInput, canonical_language_code
from .export import write_ocr_translation_bundle


@dataclass(frozen=True, slots=True)
class OcrTranslateResult:
    json_path: Path
    srt_path: Path
    manifest_path: Path


def _build_backend(
    *,
    backend_name: str,
    device: str,
    local_model: str,
    api_model: str | None,
    api_base_url: str | None,
) -> object:
    if backend_name == "local-m2m100":
        from ..translation.m2m100_backend import M2M100Backend

        return M2M100Backend(model_name=local_model, requested_device=device)
    if backend_name == "siliconflow":
        from ..translation.siliconflow_backend import SiliconFlowBackend

        return SiliconFlowBackend(base_url=api_base_url, model_name=api_model)
    raise ValueError(f"Unsupported OCR translation backend: {backend_name}")


def _resolve_source_lang(payload: dict[str, Any], requested: str | None = None) -> str:
    if requested and requested != "auto":
        return canonical_language_code(requested)
    for event in payload.get("events", []):
        if isinstance(event, dict) and event.get("language"):
            return canonical_language_code(str(event["language"]))
    return "zh"


def translate_ocr_events(
    *,
    events_path: Path,
    output_dir: Path,
    target_lang: str,
    backend_name: str,
    backend_override: object | None = None,
    source_lang: str | None = None,
    device: str = "auto",
    local_model: str = "facebook/m2m100_418M",
    api_model: str | None = None,
    api_base_url: str | None = None,
) -> OcrTranslateResult:
    payload = json.loads(events_path.read_text(encoding="utf-8"))
    events = [event for event in payload.get("events", []) if isinstance(event, dict)]
    backend = backend_override or _build_backend(
        backend_name=backend_name,
        device=device,
        local_model=local_model,
        api_model=api_model,
        api_base_url=api_base_url,
    )
    resolved_source_lang = _resolve_source_lang(payload, source_lang)
    items = [
        BackendSegmentInput(
            segment_id=str(event.get("event_id") or f"evt-{index:04d}"),
            source_text=str(event.get("text") or "").strip(),
        )
        for index, event in enumerate(events, start=1)
    ]
    outputs = backend.translate_batch(
        items=items,
        source_lang=resolved_source_lang,
        target_lang=target_lang,
    )
    translated_by_id = {output.segment_id: output.target_text.strip() for output in outputs}
    translated_events = []
    for index, event in enumerate(events, start=1):
        event_id = str(event.get("event_id") or f"evt-{index:04d}")
        translated_events.append(
            {
                **event,
                "event_id": event_id,
                "translated_text": translated_by_id.get(event_id, ""),
            }
        )
    json_path, srt_path, manifest_path = write_ocr_translation_bundle(
        output_dir=output_dir,
        target_lang=target_lang,
        backend_name=getattr(backend, "backend_name", backend_name),
        events=translated_events,
    )
    return OcrTranslateResult(
        json_path=json_path,
        srt_path=srt_path,
        manifest_path=manifest_path,
    )
