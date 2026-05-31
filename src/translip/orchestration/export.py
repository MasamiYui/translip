from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from ..types import PipelineRequest
from ..utils.files import ensure_directory
from ..utils.io import write_json as _write_json_impl


def write_json(payload: dict[str, Any], output_path: Path) -> Path:
    ensure_directory(output_path.parent)
    return _write_json_impl(payload, output_path, atomic=False, trailing_newline=True)


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


def _normalize_stage_rows(stages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized_rows: list[dict[str, Any]] = []
    for row in stages:
        normalized = dict(row)
        node_name = str(normalized.get("node_name") or normalized.get("stage_name") or "")
        if node_name:
            normalized.setdefault("node_name", node_name)
            normalized.setdefault("stage_name", node_name)
        normalized_rows.append(normalized)
    return normalized_rows


def build_pipeline_manifest(
    *,
    request: PipelineRequest,
    job_id: str,
    stages: list[dict[str, Any]],
    final_artifacts: dict[str, Any],
    status: str,
    error: str | None = None,
) -> dict[str, Any]:
    normalized_rows = _normalize_stage_rows(stages)
    return {
        "job_id": job_id,
        "template_id": request.template_id,
        "request": build_request_payload(request),
        "stages": [_jsonable(stage) for stage in normalized_rows],
        "nodes": [_jsonable(stage) for stage in normalized_rows],
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
    normalized_rows = _normalize_stage_rows(stages)
    cached_count = sum(1 for stage in normalized_rows if stage.get("status") == "cached")
    failed_stage = next(
        (
            stage.get("node_name") or stage.get("stage_name")
            for stage in normalized_rows
            if stage.get("status") == "failed"
        ),
        None,
    )
    return {
        "job_id": job_id,
        "template_id": request.template_id,
        "status": status,
        "request": build_request_payload(request),
        "summary": {
            "stage_count": len(normalized_rows),
            "node_count": len(normalized_rows),
            "cached_count": cached_count,
            "failed_stage": failed_stage,
        },
        "stages": [_jsonable(stage) for stage in normalized_rows],
        "nodes": [_jsonable(stage) for stage in normalized_rows],
        "final_artifacts": _jsonable(final_artifacts),
    }


__all__ = [
    "build_pipeline_manifest",
    "build_pipeline_report",
    "build_request_payload",
    "write_json",
]
