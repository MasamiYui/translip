"""Unit tests for tunable defaults introduced in Sprint 1 / Sprint 2.

These values are imported into :mod:`translip.types`, the orchestration request
parser and the rendering runner. Pinning them here guards against regressions
that would silently weaken the dubbing-quality fixes tracked in
``2026-04-25-dubbing-pipeline-optimization-plan.zh-CN.md``.
"""

from __future__ import annotations

import pytest

from translip import config, types


def test_max_compress_ratio_raised_to_1_6() -> None:
    assert config.DEFAULT_RENDER_MAX_COMPRESS_RATIO == 1.6
    assert config.DEFAULT_RENDER_MAX_COMPRESS_RATIO > 1.45, (
        "Sprint 1 explicitly raises max_compress_ratio above the legacy 1.45 to "
        "recover overflow-unfitted segments",
    )


def test_render_request_default_uses_config_value() -> None:
    request = types.RenderDubRequest(
        background_path="bg.wav",
        segments_path="segments.json",
        translation_path="translation.json",
        task_d_report_paths=["report.json"],
    )
    assert request.max_compress_ratio == config.DEFAULT_RENDER_MAX_COMPRESS_RATIO


def test_pipeline_request_default_uses_config_value() -> None:
    request = types.PipelineRequest(input_path="video.mp4")
    assert request.max_compress_ratio == config.DEFAULT_RENDER_MAX_COMPRESS_RATIO


def test_orchestration_request_respects_default(tmp_path) -> None:
    from translip.orchestration.request import build_pipeline_request

    video = tmp_path / "video.mp4"
    video.write_bytes(b"placeholder")
    resolved = build_pipeline_request({"input": str(video)})
    assert resolved.max_compress_ratio == config.DEFAULT_RENDER_MAX_COMPRESS_RATIO


def test_tts_duration_hard_ratio_is_sensible() -> None:
    ratio = config.DEFAULT_TTS_GENERATED_DURATION_HARD_RATIO
    assert 1.2 <= ratio <= 2.0, "hard duration ratio must be tight enough to catch pathological TTS"


def test_voice_bank_minimum_reference_knobs_are_positive() -> None:
    assert config.DEFAULT_VOICE_BANK_MIN_REFERENCE_CLIPS >= 1
    assert config.DEFAULT_VOICE_BANK_MIN_REFERENCE_DURATION_SEC > 0


def test_task_d_usable_bounds_are_monotonic() -> None:
    min_u = config.DEFAULT_TASK_D_USABLE_MIN_DURATION_SEC
    max_u = config.DEFAULT_TASK_D_USABLE_MAX_DURATION_SEC
    min_p = config.DEFAULT_TASK_D_PREFERRED_MIN_DURATION_SEC
    max_p = config.DEFAULT_TASK_D_PREFERRED_MAX_DURATION_SEC
    assert min_u < max_u
    assert min_p < max_p
    assert min_u <= min_p
    assert max_p <= max_u


if __name__ == "__main__":  # pragma: no cover - debug helper
    pytest.main([__file__, "-v"])
