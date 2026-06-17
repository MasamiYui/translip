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

    result = generate_plan("把日语台词转成中文字幕", filenames=["movie.mp4"])

    assert result.type == "plan"
    plan = result.plan
    assert plan is not None
    assert len(plan.steps) == 3
    assert [s.tool_id for s in plan.steps] == ["separation", "transcription", "translation"]
    # edges auto-derived from step bindings when the model omits them
    assert {(e.source, e.target) for e in plan.edges} == {("sep", "asr"), ("asr", "mt")}
    assert plan.steps[1].inputs["file_id"].output == "voice_file"


def test_generate_plan_returns_clarification(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    clarification_payload = {
        "type": "clarification",
        "question": "你想翻译成哪种语言？",
        "options": ["中文", "英文"],
    }
    monkeypatch.setattr(
        planner, "post_chat_completion", lambda **kw: _fake_response(clarification_payload)
    )

    result = generate_plan("翻译这个视频")

    assert result.type == "clarification"
    assert result.plan is None
    assert result.clarification is not None
    assert result.clarification.question == "你想翻译成哪种语言？"
    assert result.clarification.options == ["中文", "英文"]


def test_parse_planner_response_detects_clarification_without_discriminator() -> None:
    from translip.server.assistant.planner import parse_planner_response

    result = parse_planner_response({"question": "需要先上传一个视频文件，方便上传吗？"})
    assert result.type == "clarification"
    assert result.clarification is not None


def test_build_planner_messages_injects_history_and_available_files() -> None:
    from translip.server.assistant.models import AvailableFileRef, ConversationTurn
    from translip.server.assistant.planner import build_planner_messages

    messages = build_planner_messages(
        "把刚才的人声配成英文",
        history=[
            ConversationTurn(role="user", content="提取这个视频的人声"),
            ConversationTurn(role="assistant", content="已执行，产物：voice.wav"),
        ],
        available_files=[AvailableFileRef(label="上一步产物：voice.wav", filename="voice.wav")],
    )

    roles = [m["role"] for m in messages]
    # system, then the two history turns, then the final user message
    assert roles == ["system", "user", "assistant", "user"]
    assert messages[1]["content"] == "提取这个视频的人声"
    assert "已执行，产物：voice.wav" in messages[2]["content"]
    final_user = messages[-1]["content"]
    assert "upload_index=0" in final_user
    assert "voice.wav" in final_user


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
