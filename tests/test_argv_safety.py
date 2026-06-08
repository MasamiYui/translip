from __future__ import annotations

import pytest

from translip.orchestration.argv_safety import (
    ArgvValidationError,
    validate_lang,
    validate_model,
    validate_path_identifier,
    validate_url,
)
from translip.orchestration.commands import (
    build_task_c_command,
    build_task_d_command,
)
from translip.types import PipelineRequest


@pytest.mark.parametrize("value", ["en", "zh", "ja", "yue", "zh-CN", "en_US", "auto"])
def test_validate_lang_accepts_codes(value: str) -> None:
    assert validate_lang(value, field="lang") == value


@pytest.mark.parametrize("value", ["", "--output-dir", "en;rm", "english language", "../zh", "12"])
def test_validate_lang_rejects_garbage(value: str) -> None:
    with pytest.raises(ArgvValidationError):
        validate_lang(value, field="lang")


@pytest.mark.parametrize(
    "value",
    ["https://api.deepseek.com", "http://localhost:8000/v1", "https://x.y/v1/chat"],
)
def test_validate_url_accepts(value: str) -> None:
    assert validate_url(value, field="url") == value


@pytest.mark.parametrize(
    "value",
    ["", "ftp://x", "javascript:alert(1)", "--api-base-url", "https://a b/c", "http://"],
)
def test_validate_url_rejects(value: str) -> None:
    with pytest.raises(ArgvValidationError):
        validate_url(value, field="url")


@pytest.mark.parametrize("value", ["deepseek-v4-pro", "gpt-4o", "org/model", "vendor:tag", "m_1.2"])
def test_validate_model_accepts(value: str) -> None:
    assert validate_model(value, field="model") == value


@pytest.mark.parametrize("value", ["", "-flag", "a b", "rm -rf", "../x"])
def test_validate_model_rejects(value: str) -> None:
    with pytest.raises(ArgvValidationError):
        validate_model(value, field="model")


@pytest.mark.parametrize("value", ["SPEAKER_00", "persona-1", "主角", "narrator.v2"])
def test_validate_path_identifier_accepts(value: str) -> None:
    assert validate_path_identifier(value, field="speaker_id") == value


@pytest.mark.parametrize(
    "value",
    ["", ".", "..", "../etc", "a/b", "a\\b", "-flag", "with space", "a..b"],
)
def test_validate_path_identifier_rejects(value: str) -> None:
    with pytest.raises(ArgvValidationError):
        validate_path_identifier(value, field="speaker_id")


def _request(tmp_path) -> PipelineRequest:
    return PipelineRequest(input_path=tmp_path / "in.mp4", output_root=tmp_path / "out")


def test_build_task_d_rejects_traversal_speaker_id(tmp_path) -> None:
    request = _request(tmp_path)
    with pytest.raises(ArgvValidationError):
        build_task_d_command(request, speaker_id="../../etc", segment_ids=None)


def test_build_task_d_rejects_bad_segment_id(tmp_path) -> None:
    request = _request(tmp_path)
    with pytest.raises(ArgvValidationError):
        build_task_d_command(request, speaker_id="SPEAKER_00", segment_ids=["ok", "--evil"])


def test_build_task_d_accepts_clean(tmp_path) -> None:
    request = _request(tmp_path)
    command = build_task_d_command(request, speaker_id="SPEAKER_00", segment_ids=["s1"])
    assert "synthesize-speaker" in command
    assert "SPEAKER_00" in command


def test_build_task_c_rejects_argument_injection_base_url(tmp_path) -> None:
    request = _request(tmp_path)
    request.api_base_url = "--output-dir=/tmp/evil"
    with pytest.raises(ArgvValidationError):
        build_task_c_command(request)


def test_build_task_c_accepts_clean(tmp_path) -> None:
    request = _request(tmp_path)
    request.api_base_url = "https://api.deepseek.com"
    request.api_model = "deepseek-v4-pro"
    command = build_task_c_command(request)
    assert "translate-script" in command
