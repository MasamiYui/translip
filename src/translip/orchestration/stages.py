from __future__ import annotations

from ..types import PipelineStageName

STAGE_ORDER: list[PipelineStageName] = [
    "stage1",
    "task-a",
    "task-b",
    "task-c",
    "task-d",
    "task-e",
]

STAGE_WEIGHTS: dict[PipelineStageName, float] = {
    "stage1": 0.10,
    "task-a": 0.10,
    "task-b": 0.10,
    "task-c": 0.15,
    "task-d": 0.35,
    "task-e": 0.20,
}


def validate_stage_name(stage_name: str) -> PipelineStageName:
    if stage_name not in STAGE_ORDER:
        raise ValueError(f"Unsupported pipeline stage: {stage_name}")
    return stage_name  # type: ignore[return-value]


def resolve_stage_sequence(
    run_from_stage: str,
    run_to_stage: str,
) -> list[PipelineStageName]:
    start = STAGE_ORDER.index(validate_stage_name(run_from_stage))
    end = STAGE_ORDER.index(validate_stage_name(run_to_stage))
    if start > end:
        raise ValueError("run_from_stage must be before or equal to run_to_stage")
    return STAGE_ORDER[start : end + 1]


__all__ = ["STAGE_ORDER", "STAGE_WEIGHTS", "resolve_stage_sequence", "validate_stage_name"]
