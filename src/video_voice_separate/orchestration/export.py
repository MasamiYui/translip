from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ..types import PipelineRequest
from ..utils.files import ensure_directory


def write_json(payload: dict[str, Any], output_path: Path) -> Path:
    ensure_directory(output_path.parent)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output_path


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def build_request_payload(request: PipelineRequest) -> dict[str, Any]:
    return _jsonable(asdict(request))


def build_pipeline_manifest(
    *,
    request: PipelineRequest,
    job_id: str,
    stages: list[dict[str, Any]],
    final_artifacts: dict[str, Any],
    status: str,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "request": build_request_payload(request),
        "stages": [_jsonable(stage) for stage in stages],
        "final_artifacts": _jsonable(final_artifacts),
        "status": status,
        "error": error,
    }


def build_pipeline_report(
    *,
    request: PipelineRequest,
    job_id: str,
    stages: list[dict[str, Any]],
    final_artifacts: dict[str, Any],
    status: str,
) -> dict[str, Any]:
    cached_count = sum(1 for stage in stages if stage.get("status") == "cached")
    failed_stage = next((stage.get("stage_name") for stage in stages if stage.get("status") == "failed"), None)
    return {
        "job_id": job_id,
        "status": status,
        "request": build_request_payload(request),
        "summary": {
            "stage_count": len(stages),
            "cached_count": cached_count,
            "failed_stage": failed_stage,
        },
        "stages": [_jsonable(stage) for stage in stages],
        "final_artifacts": _jsonable(final_artifacts),
    }


__all__ = [
    "build_pipeline_manifest",
    "build_pipeline_report",
    "build_request_payload",
    "write_json",
]
