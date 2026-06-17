from __future__ import annotations

import json

import pytest

from translip.exceptions import BackendUnavailableError
from translip.server.assistant import planner
from translip.server.assistant.planner import generate_plan, plan_from_payload

_VALID_PLAN = {
    "summary": "先分离人声，再做日语转写，最后翻译成中文。",
    "steps": [
        {
            "id": "sep",
            "tool_id": "separation",
            "title": "人声分离",
            "params": {},
            "inputs": {"file_id": {"source": "upload", "upload_index": 0}},
        },
        {
            "id": "asr",
            "tool_id": "transcription",
            "title": "日语转写",
            "params": {"language": "ja"},
            "inputs": {
                "file_id": {"source": "step", "step_id": "sep", "output": "voice_file"}
            },
        },
        {
            "id": "mt",
            "tool_id": "translation",
            "title": "翻译为中文",
            "params": {"source_lang": "ja", "target_lang": "zh", "backend": "deepseek"},
            "inputs": {
                "file_id": {"source": "step", "step_id": "asr", "output": "segments_file"}
            },
        },
    ],
}


def _fake_response(payload: dict) -> dict:
    return {"choices": [{"message": {"content": json.dumps(payload)}}]}


def test_generate_plan_parses_deepseek_json(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setattr(planner, "post_chat_completion", lambda **kw: _fake_response(_VALID_PLAN))

    plan = generate_plan("把日语台词转成中文字幕", filenames=["movie.mp4"])

    assert len(plan.steps) == 3
    assert [s.tool_id for s in plan.steps] == ["separation", "transcription", "translation"]
    # edges auto-derived from step bindings when the model omits them
    assert {(e.source, e.target) for e in plan.edges} == {("sep", "asr"), ("asr", "mt")}
    assert plan.steps[1].inputs["file_id"].output == "voice_file"


def test_generate_plan_requires_api_key(monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(BackendUnavailableError):
        generate_plan("做点什么")


def test_plan_validation_rejects_unknown_tool() -> None:
    bad = {
        "summary": "x",
        "steps": [{"id": "a", "tool_id": "make-coffee", "inputs": {}}],
    }
    with pytest.raises(ValueError, match="未知工具"):
        plan_from_payload(bad)


def test_plan_validation_rejects_unknown_param() -> None:
    bad = {
        "summary": "x",
        "steps": [
            {
                "id": "sep",
                "tool_id": "separation",
                "params": {"nonexistent": 1},
                "inputs": {"file_id": {"source": "upload", "upload_index": 0}},
            }
        ],
    }
    with pytest.raises(ValueError, match="不支持参数"):
        plan_from_payload(bad)


def test_plan_validation_rejects_forward_step_reference() -> None:
    bad = {
        "summary": "x",
        "steps": [
            {
                "id": "a",
                "tool_id": "translation",
                "params": {},
                "inputs": {
                    "file_id": {"source": "step", "step_id": "later", "output": "srt_file"}
                },
            }
        ],
    }
    with pytest.raises(ValueError, match="未定义"):
        plan_from_payload(bad)
