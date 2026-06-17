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
from .models import (
    AssistantPlan,
    AvailableFileRef,
    Clarification,
    ConversationTurn,
    PlanResult,
    PlanStep,
    StepEdge,
)

_SYSTEM_PROMPT = """\
你是 translip（本地视频配音/字幕流水线）的智能编排助手。用户用自然语言描述需求，\
你要把需求拆解成一条「原子能力调用链路」，只能使用下面给出的工具（tool_id）。

可用工具目录（JSON）：
{catalog}

规则：
1. 只输出一个 JSON 对象，不要任何解释文字、不要 markdown 代码块。
2. 如果信息不足以规划——例如：需要文件但用户没有上传、目标语言/翻译方向不明确、需求过于宽泛无法确定要做什么——\
则**不要硬猜**，而是输出一个澄清对象向用户提问：
{{
  "type": "clarification",
  "question": "用中文提出一个清晰的问题",
  "options": ["可点选的简短选项1", "选项2"]   // 可选；没有合适选项就给空数组
}}
3. 信息足够时，输出计划对象（type 可省略或写 "plan"）：
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
4. 文件参数（file_id、*_file_id）必须放在 inputs 里用 binding 指定来源；其余参数放在 params。
5. 同一计划里上一步的产物用 source="step" + step_id + output 绑定；output 必须是该工具 outputs 中存在的键。
6. source="upload" + upload_index 引用「可用文件」列表里的第 N 个文件——它既可能是用户本轮上传的，也可能是本会话**之前运行产出的产物**。没有任何可用文件却需要文件时，按规则 2 提出澄清。
7. 结合「对话历史」理解追问与指代：如「刚才/上次/那个结果」通常指最近一次运行的产物，应在「可用文件」里挑对应项用 upload_index 引用；「再来一份/换成…」表示在上一轮设定基础上调整。
8. 参数名必须是该工具真实存在的参数；不确定的可选参数就省略，使用其默认值。
9. 语言代码用简短形式（如 ja=日语, zh=中文, en=英语）。

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


def _available_files_block(
    available_files: list[AvailableFileRef], filenames: list[str]
) -> str:
    if available_files:
        return "\n".join(
            f"- upload_index={i}: {ref.label} (文件名 {ref.filename})"
            for i, ref in enumerate(available_files)
        )
    if filenames:
        return "\n".join(f"- upload_index={i}: {name}" for i, name in enumerate(filenames))
    return "（无可用文件）"


def _build_messages(
    message: str,
    filenames: list[str],
    history: list[ConversationTurn] | None = None,
    available_files: list[AvailableFileRef] | None = None,
) -> list[dict[str, str]]:
    catalog_json = json.dumps(build_tool_catalog(), ensure_ascii=False, indent=2)
    system = _SYSTEM_PROMPT.format(catalog=catalog_json)
    files_block = _available_files_block(available_files or [], filenames)
    user = (
        f"用户需求：\n{message}\n\n"
        f"可用文件（用 source=upload + upload_index 引用）：\n{files_block}\n\n"
        "请输出 JSON。"
    )
    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    for turn in history or []:
        content = turn.content.strip()
        if content:
            messages.append({"role": turn.role, "content": content})
    messages.append({"role": "user", "content": user})
    return messages


def _coerce_plan(payload: dict[str, Any]) -> AssistantPlan:
    plan = AssistantPlan.model_validate(payload)
    if not plan.steps:
        raise ValueError("计划为空：没有任何步骤。")
    _validate_plan(plan)
    if not plan.edges:
        plan.edges = _derive_edges(plan)
    return plan


def _looks_like_clarification(payload: dict[str, Any]) -> bool:
    if payload.get("type") == "clarification":
        return True
    # Tolerate models that emit a clarification without the discriminator.
    if isinstance(payload.get("clarification"), dict):
        return True
    has_question = bool(str(payload.get("question") or "").strip())
    return has_question and not payload.get("steps")


def _coerce_clarification(payload: dict[str, Any]) -> Clarification:
    raw = payload.get("clarification") if isinstance(payload.get("clarification"), dict) else payload
    clarification = Clarification.model_validate(raw)
    if not clarification.question.strip():
        raise ValueError("澄清问题为空。")
    return clarification


def parse_planner_response(payload: dict[str, Any]) -> PlanResult:
    """Turn a raw planner JSON object into a plan-or-clarification result."""
    if _looks_like_clarification(payload):
        return PlanResult(type="clarification", clarification=_coerce_clarification(payload))
    return PlanResult(type="plan", plan=_coerce_plan(payload))


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
    history: list[ConversationTurn] | None = None,
    available_files: list[AvailableFileRef] | None = None,
    timeout_sec: int = 60,
) -> PlanResult:
    """Plan a tool chain for ``message`` (or ask for clarification).

    ``history`` and ``available_files`` give the planner multi-turn context and
    the pool of files (uploads + prior-run artifacts) it may bind to.
    Raises BackendUnavailableError if no DeepSeek key is configured.
    """
    if not message.strip():
        raise ValueError("请输入你的需求。")
    api_key = _deepseek_api_key()
    payload = {
        "model": DEFAULT_DEEPSEEK_MODEL,
        "temperature": 0,
        "messages": _build_messages(message, filenames or [], history, available_files),
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
    return parse_planner_response(data)


# Exposed for unit tests that want to validate a raw planner JSON payload without
# hitting the network.
def plan_from_payload(payload: dict[str, Any]) -> AssistantPlan:
    return _coerce_plan(payload)


def build_planner_messages(
    message: str,
    filenames: list[str] | None = None,
    history: list[ConversationTurn] | None = None,
    available_files: list[AvailableFileRef] | None = None,
) -> list[dict[str, str]]:
    return _build_messages(message, filenames or [], history, available_files)
