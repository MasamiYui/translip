"""DeepSeek-backed planner: natural language -> atomic-tool call chain.

Given a user request (and any uploaded attachments) the planner asks DeepSeek to
emit a JSON plan that wires existing atomic tools together. It reuses the exact
same OpenAI-compatible HTTP + parsing helpers as the translation backend
(``translation/llm_utils.py``) so behaviour stays consistent across the codebase.
A valid ``DEEPSEEK_API_KEY`` is required — there is no offline fallback.
"""

from __future__ import annotations

import json
import os
from typing import Any

from ...config import DEFAULT_DEEPSEEK_MODEL, resolve_deepseek_base_url
from ...exceptions import BackendUnavailableError
from ...translation.llm_utils import (
    extract_message_content,
    parse_json_payload,
    post_chat_completion,
)
from ..atomic_tools.registry import TOOL_REGISTRY
from .catalog import build_tool_catalog, is_file_param, model_field_names
from .models import AssistantPlan, PlanStep, StepEdge

_SYSTEM_PROMPT = """\
你是 translip（本地视频配音/字幕流水线）的智能编排助手。用户用自然语言描述需求，\
你要把需求拆解成一条「原子能力调用链路」，只能使用下面给出的工具（tool_id）。

可用工具目录（JSON）：
{catalog}

规则：
1. 只输出一个 JSON 对象，不要任何解释文字、不要 markdown 代码块。
2. JSON 结构：
{{
  "summary": "用一两句中文向非技术用户解释你将怎么做",
  "steps": [
    {{
      "id": "短的英文步骤标识，如 sep/asr/mt",
      "tool_id": "必须来自工具目录",
      "title": "给链路图节点用的简短中文名",
      "rationale": "这一步为什么需要（简短中文）",
      "params": {{ "非文件参数名": 值 }},
      "inputs": {{
        "文件参数名(如 file_id / voice_file_id)": {{
          "source": "upload" 或 "step",
          "upload_index": 数字(source=upload 时，对应用户上传的第几个文件，从0开始),
          "step_id": "上一步的 id(source=step 时)",
          "output": "上一步 outputs 里的键名(source=step 时，如 voice_file/segments_file)"
        }}
      }}
    }}
  ],
  "edges": [ {{ "source": "上游步骤id", "target": "下游步骤id" }} ]
}}
3. 文件参数（file_id、*_file_id）必须放在 inputs 里用 binding 指定来源；其余参数放在 params。
4. 上一步的产物用 source="step" + step_id + output 绑定；output 必须是该工具 outputs 中存在的键。
5. 用户上传的文件用 source="upload" + upload_index 绑定。
6. 参数名必须是该工具真实存在的参数；不确定的可选参数就省略，使用其默认值。
7. 语言代码用简短形式（如 ja=日语, zh=中文, en=英语）。

示例：用户说「把这个视频里的日语台词转成中文字幕」（上传了 1 个视频）：
{{
  "summary": "我会先分离出人声，再做日语语音转写，最后用 DeepSeek 翻译成中文字幕。",
  "steps": [
    {{"id":"sep","tool_id":"separation","title":"人声分离","rationale":"去掉背景音，提升转写准确率","params":{{}},"inputs":{{"file_id":{{"source":"upload","upload_index":0}}}}}},
    {{"id":"asr","tool_id":"transcription","title":"日语转写","rationale":"把日语语音转成带时间轴的文本","params":{{"language":"ja"}},"inputs":{{"file_id":{{"source":"step","step_id":"sep","output":"voice_file"}}}}}},
    {{"id":"mt","tool_id":"translation","title":"翻译为中文","rationale":"把日语字幕翻译成中文","params":{{"source_lang":"ja","target_lang":"zh","backend":"deepseek"}},"inputs":{{"file_id":{{"source":"step","step_id":"asr","output":"segments_file"}}}}}}
  ],
  "edges": [ {{"source":"sep","target":"asr"}}, {{"source":"asr","target":"mt"}} ]
}}
"""


def _deepseek_api_key() -> str:
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise BackendUnavailableError(
            "未配置 DeepSeek API Key。请在「设置」中配置 DEEPSEEK_API_KEY 后再使用智能助手。"
        )
    return key


def _build_messages(message: str, filenames: list[str]) -> list[dict[str, str]]:
    catalog_json = json.dumps(build_tool_catalog(), ensure_ascii=False, indent=2)
    system = _SYSTEM_PROMPT.format(catalog=catalog_json)
    attachments = (
        "\n".join(f"- upload_index={i}: {name}" for i, name in enumerate(filenames))
        if filenames
        else "（无上传文件）"
    )
    user = f"用户需求：\n{message}\n\n已上传文件：\n{attachments}\n\n请输出 JSON 计划。"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _coerce_plan(payload: dict[str, Any]) -> AssistantPlan:
    plan = AssistantPlan.model_validate(payload)
    if not plan.steps:
        raise ValueError("计划为空：没有任何步骤。")
    _validate_plan(plan)
    if not plan.edges:
        plan.edges = _derive_edges(plan)
    return plan


def _validate_plan(plan: AssistantPlan) -> None:
    seen_ids: set[str] = set()
    for step in plan.steps:
        if step.tool_id not in TOOL_REGISTRY:
            raise ValueError(f"未知工具：{step.tool_id}")
        if step.id in seen_ids:
            raise ValueError(f"步骤 id 重复：{step.id}")
        seen_ids.add(step.id)
        valid_fields = model_field_names(step.tool_id)
        if valid_fields:
            for key in step.params:
                if key not in valid_fields or is_file_param(key):
                    raise ValueError(f"{step.tool_id} 不支持参数：{key}")
            for key in step.inputs:
                if key not in valid_fields or not is_file_param(key):
                    raise ValueError(f"{step.tool_id} 不支持文件输入：{key}")
        for param_name, binding in step.inputs.items():
            if binding.source == "step":
                if binding.step_id not in seen_ids:
                    raise ValueError(
                        f"步骤 {step.id} 的输入 {param_name} 引用了未定义/靠后的步骤：{binding.step_id}"
                    )


def _derive_edges(plan: AssistantPlan) -> list[StepEdge]:
    edges: list[StepEdge] = []
    for step in plan.steps:
        for binding in step.inputs.values():
            if binding.source == "step" and binding.step_id:
                edges.append(StepEdge(source=binding.step_id, target=step.id))
    return edges


def generate_plan(
    message: str,
    *,
    filenames: list[str] | None = None,
    timeout_sec: int = 60,
) -> AssistantPlan:
    """Plan a tool chain for ``message``. Raises BackendUnavailableError if no key."""
    if not message.strip():
        raise ValueError("请输入你的需求。")
    api_key = _deepseek_api_key()
    payload = {
        "model": DEFAULT_DEEPSEEK_MODEL,
        "temperature": 0,
        "messages": _build_messages(message, filenames or []),
        "response_format": {"type": "json_object"},
    }
    response = post_chat_completion(
        url=f"{resolve_deepseek_base_url().rstrip('/')}/chat/completions",
        api_key=api_key,
        payload=payload,
        timeout_sec=timeout_sec,
    )
    content = extract_message_content(response)
    data = parse_json_payload(content)
    return _coerce_plan(data)


# Exposed for unit tests that want to validate a raw planner JSON payload without
# hitting the network.
def plan_from_payload(payload: dict[str, Any]) -> AssistantPlan:
    return _coerce_plan(payload)


def build_planner_messages(message: str, filenames: list[str] | None = None) -> list[dict[str, str]]:
    return _build_messages(message, filenames or [])
