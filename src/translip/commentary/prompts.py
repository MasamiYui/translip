"""Prompt templates for the commentary-script chain (``plot_recap`` style).

Ported in spirit from NarratoAI's ``film_tv_narration`` chain, adapted to
translip's SECONDS-float timeline and single-video model — every source window is
a ``[start, end]`` pair in seconds, not an ``HH:MM:SS,mmm`` string. Three stages:

1. :func:`plot_analysis`     — understand, grounded (字幕=唯一事实源). Returns text.
2. :func:`segment_planning`  — select windows + assign OST + honor 原片占比. Returns JSON.
3. :func:`script_generation` — write narration into the planned OST=0 slots. Returns JSON.

Each returns ``{"system": ..., "user": ...}`` ready to splat into ``llm.call_*``.
"""

from __future__ import annotations

import json
from typing import Any

from .types import CommentaryOptions

# Per-genre narrative emphasis injected into planning + writing so the recap
# leans the right way (mirrors NarratoAI's drama_genre branch).
_GENRE_FOCUS: dict[str, str] = {
    "剧情": "人物选择、关系裂痕、命运压力与情绪余波",
    "悬疑": "线索、疑点、动机、误导与未揭开的真相",
    "犯罪": "线索、疑点、动机、误导与未揭开的真相",
    "动作": "目标、危险升级、身体对抗与关键抉择",
    "喜剧": "误会、反差、节奏包袱与人物可爱处",
    "科幻": "设定规则、未知威胁、世界观反差与代价",
    "奇幻": "设定规则、未知威胁、世界观反差与代价",
    "历史": "时代处境、阵营选择、牺牲与局势变化",
    "战争": "时代处境、阵营选择、牺牲与局势变化",
    "恐怖": "异常细节、压迫感、未知危险与心理悬念",
}


def _genre_focus(genre: str) -> str:
    return _GENRE_FOCUS.get(genre.strip(), f"服从用户指定的「{genre}」类型的主要看点")


def plot_analysis(story_text: str, options: CommentaryOptions) -> dict[str, str]:
    system = (
        "你是一位专业的影视解说策划和剧作分析师。你的输出不是给观众看的成片文案，"
        "而是给下游解说脚本生成器使用的、克制且结构化的剧情理解材料。"
    )
    user = (
        "# 任务\n"
        "基于下面的字幕时间轴（唯一可信事实源）和可选画面场景（辅助），梳理剧情，"
        "为后续生成高质量影视解说脚本做准备。\n\n"
        "# 铁律\n"
        "1. 字幕是唯一可信事实来源；画面场景只能辅助理解，与字幕冲突时以字幕为准。\n"
        "2. 禁止编造字幕中没有的事件、对白或人物关系。无法确定就写“字幕未明确”。\n"
        "3. 人名/称呼必须前后统一。\n"
        "4. 输出简洁、客观、可复用，避免散文化长段落。\n\n"
        "# 输出（Markdown，按此结构，不要寒暄）\n"
        "## 一、整体剧情概括\n[120-220字，只概括字幕覆盖的剧情：核心冲突、人物动机、当前悬念]\n\n"
        "## 二、人物与关系\n[统一称呼 + 身份/关系 + 当前动机，逐条列出]\n\n"
        "## 三、关键剧情段落\n[按时间顺序列出关键事件，每条标注其大致时间区间（秒）与叙事功能：铺垫/冲突升级/反转/名场面/情绪爆发等]\n\n"
        "## 四、解说创作重点\n- 开场钩子：[最适合抓人的冲突/谜题/人物困境]\n- 名场面/高光对白：[1-3条，建议保留原声的片段及其时间区间]\n- 悬念点：[留给观众的疑问]\n\n"
        "# 输入\n" + story_text
    )
    return {"system": system, "user": user}


_PLAN_OUTPUT_SPEC = """# 输出格式（只输出严格 JSON，无任何额外文字或代码块标记）
{
  "segments": [
    {
      "id": 1,
      "ost": 0,
      "src": [1.0, 6.5],
      "story_role": "开场钩子",
      "intent": "点出主角困境和反常线索，制造继续观看的疑问"
    }
  ]
}"""


def segment_planning(story_text: str, plot: str, options: CommentaryOptions) -> dict[str, str]:
    system = (
        "你是一位影视解说剪辑规划师。你的任务是从字幕时间轴中选择可剪辑片段并标注用途，"
        "不写解说台词。必须严格输出 JSON，不要 Markdown 或额外说明。"
    )
    user = (
        "# 目标\n"
        "规划一条观众能顺着看懂的解说故事线。先想清“人物处境→事件触发→关系/信息变化→新危机→悬念”的因果链，再选片段。\n\n"
        f"# 影视类型\n{options.genre}（叙事重点：{_genre_focus(options.genre)}）\n\n"
        f"# 目标原片占比\n约 {options.original_sound_ratio}%（OST=1 原声片段的总时长占比，按各片段时长估算）\n\n"
        "# 剧情理解材料\n" + plot + "\n\n"
        "# 字幕时间轴（src 时间区间必须来自这里，单位：秒）\n" + story_text + "\n\n"
        "# 规划规则\n"
        "1. src 为 [起始秒, 结束秒]，必须落在字幕时间轴范围内；片段之间不得时间重叠；按故事顺序排列。\n"
        "2. OST=1 表示保留原声（用于关键对白、情绪爆发、真相揭露、名场面、反转），单段优先 3-10 秒；OST=0 表示该片段后续配解说。\n"
        "3. 第一段必须是 OST=0 解说开场钩子，不能直接放原声。开头用“人物困境 + 反常信息 + 悬念问题”。\n"
        "4. 禁止连续 3 个或更多 OST=1；每 1-2 个原声片段后必须安排 OST=0 承接剧情。\n"
        "5. 让 OST=1 总时长占比尽量接近目标原片占比；占比为 0 时不要输出任何 OST=1。\n"
        "6. 每个片段都要推动主线、解释动机、制造转折或承接原声；不要选与剧情无关的片段。\n"
        "7. 结尾优先选能留下新问题/新危险/人物选择的片段。\n\n"
        + _PLAN_OUTPUT_SPEC
    )
    return {"system": system, "user": user}


_SCRIPT_OUTPUT_SPEC = """# 输出格式（只输出严格 JSON，无任何额外文字或代码块标记）
{
  "items": [
    { "id": 1, "narration": "他以为这只是一次普通问询，可桌上的证据却把矛头指向了自己。", "picture": "男主站在审讯室门口，神情紧张地看向证据袋" }
  ]
}"""


def script_generation(
    story_text: str,
    plot: str,
    plan: list[dict[str, Any]],
    options: CommentaryOptions,
) -> dict[str, str]:
    # Hand the planner's structure to the writer as JSON; it may only fill text.
    plan_json = json.dumps(
        [
            {"id": seg["id"], "ost": seg["ost"], "src": [seg["start"], seg["end"]], "story_role": seg.get("story_role", "")}
            for seg in plan
        ],
        ensure_ascii=False,
    )
    system = (
        "你是一位影视解说文案写手。你必须严格按 JSON 输出，只能为每个片段补充 narration 和 picture，"
        "不能改动上游规划的 id、ost、src。"
    )
    user = (
        f"# 任务\n为已规划好的片段补写解说文案。解说台词语言：{options.language}。"
        f"影视类型：{options.genre}（叙事重点：{_genre_focus(options.genre)}）。\n\n"
        "# 已规划片段（逐项照抄 id，不得增删合并）\n" + plan_json + "\n\n"
        "# 剧情理解材料\n" + plot + "\n\n"
        "# 字幕时间轴（事实源，narration 必须基于此，禁止虚构）\n" + story_text + "\n\n"
        "# 写作规则\n"
        "1. 只为每个片段补 narration 和 picture 两个字段，输出 items 的数量、顺序、id 必须与已规划片段完全一致。\n"
        "2. ost=1 的片段是保留原声片段，其 narration 必须留空字符串 \"\"（不要写解说）。\n"
        "3. ost=0 的 narration 用指定语言书写，必须严格基于剧情与字幕，不虚构字幕外的具体事件。\n"
        "4. 叙事连续性：每个 ost=0 narration 尽量回答“上一段发生了什么、人物为何这么做、这段带来什么新信息或新危机”，多用承接句、少用孤立信息句。\n"
        "5. 第一段是开场钩子，直接点出冲突/疑点/人物困境，强力抓人。\n"
        "6. 解说密度服从画面时长：按“narration 字数 / 5 ≈ 片段秒数”估算；片段短就少说、不要灌信息。优先短句，单句只表达一个信息点。\n"
        "7. picture 简述该片段画面中人物、动作、情绪与关键道具，便于后期识别素材。\n"
        "8. 不要解释规则，不要输出 Markdown 或代码块。\n\n"
        + _SCRIPT_OUTPUT_SPEC
    )
    return {"system": system, "user": user}
