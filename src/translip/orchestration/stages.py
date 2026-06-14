from __future__ import annotations

from ..types import PipelineStageName

STAGE_ORDER: list[PipelineStageName] = [
    "separation",
    "transcription",
    "asr-ocr-correct",
    "speaker-registry",
    "translation",
    "synthesis",
    "render",
    "delivery",
]

STAGE_WEIGHTS: dict[PipelineStageName, float] = {
    "separation": 0.10,
    "transcription": 0.10,
    "asr-ocr-correct": 0.05,
    "speaker-registry": 0.10,
    "translation": 0.15,
    "synthesis": 0.35,
    "render": 0.20,
    "delivery": 0.0,
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
