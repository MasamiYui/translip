"""Style profile registries that drive Phase-1 commentary customization.

These are *prompt-side* knobs — none of them changes the LLM call count, the
fact-source contract, or the OST-interleaved timeline. They only influence the
wording, density, and persona of the narration the chain produces.

Five registries:

* :data:`MODE_PROFILES`        — script structure (mode / commentary_style).
* :data:`TONE_PROFILES`        — narrator persona.
* :data:`PACING_PROFILES`      — segment density and chars-per-second.
* :data:`PERSPECTIVE_PROFILES` — narrative person (third/first/second/...).
* :data:`AUDIENCE_PROFILES`    — platform-specific language conventions.

Every registry has a ``DEFAULT_*`` key that is the safe fallback the chain
uses when the request asks for an unknown id.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModeProfile:
    """One commentary mode (script structure)."""

    id: str
    label_zh: str
    label_en: str
    summary: str  # one-line description injected into prompts
    structure_hint: str  # bullet rules for plot_analysis stage
    plan_focus: str  # what segment_planning should prioritize
    writing_focus: str  # what script_generation should emphasize


@dataclass(frozen=True, slots=True)
class ToneProfile:
    """One narrator persona."""

    id: str
    label_zh: str
    label_en: str
    voice_brief: str  # 1-sentence persona for the writer
    do_examples: tuple[str, ...]  # short do-style phrases
    avoid: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PacingProfile:
    """Density preset that shapes the planner + the writer."""

    id: str
    label_zh: str
    label_en: str
    avg_segment_sec: float
    cps_zh: float  # narration chars per second (zh; en uses 0.45 × this).
    sentence_style: str  # short | natural | long
    silence_tolerance_sec: float


@dataclass(frozen=True, slots=True)
class PerspectiveProfile:
    id: str
    label_zh: str
    label_en: str
    instruction: str
    example: str


@dataclass(frozen=True, slots=True)
class AudienceProfile:
    id: str
    label_zh: str
    label_en: str
    language_brief: str
    allow_phrases: tuple[str, ...]
    banned_phrases: tuple[str, ...]


# ---------------------------------------------------------------------------
# Modes — script structure
# ---------------------------------------------------------------------------

DEFAULT_MODE_ID = "plot_recap"
MODE_PROFILES: dict[str, ModeProfile] = {
    "plot_recap": ModeProfile(
        id="plot_recap",
        label_zh="剧情解说",
        label_en="Plot Recap",
        summary="按时间顺序复述剧情，开场抛钩子，高潮点保留原声",
        structure_hint="梳理时序剧情：核心冲突→人物动机→关键转折→当前悬念",
        plan_focus="按因果链选片段，先抛钩子、再交代关系、最后给悬念",
        writing_focus="承上启下，把每段“为什么会这样”讲清楚，少灌信息",
    ),
    "plot_tease": ModeProfile(
        id="plot_tease",
        label_zh="悬念预告",
        label_en="Plot Tease",
        summary="短视频/预告片风格：只留钩子和反差，结局不剧透",
        structure_hint="挑出 2-4 个最反差的画面/对白，列出可制造悬念的疑问",
        plan_focus="只选悬念片段，避开揭示型片段，结尾必须留疑问",
        writing_focus="多反问句、短句、强钩子；禁止剧透结局",
    ),
    "analysis": ModeProfile(
        id="analysis",
        label_zh="影视解读",
        label_en="Analysis",
        summary="影评/纪录片风格：论点 + 论据 + 升华",
        structure_hint="提炼 1-3 个核心论点，每个论点找出可佐证的片段与对白",
        plan_focus="按“论点-论据-反例-升华”顺序选片段，原声留给关键证据",
        writing_focus="每段一个论点，逻辑词清晰；避免感性形容，引用具体细节",
    ),
    "roast": ModeProfile(
        id="roast",
        label_zh="吐槽锐评",
        label_en="Roast",
        summary="喜剧/吐槽向：反讽、段子节奏、毒舌但不恶意",
        structure_hint="挑出剧情中“离谱/反差/无厘头”的点，列出可吐槽的素材",
        plan_focus="挑反差最大的片段；OST=1 留给“尴尬现场”原声",
        writing_focus="多用反讽、明喻、反差；禁止人身攻击与冒犯性梗",
    ),
    "reaction": ModeProfile(
        id="reaction",
        label_zh="实时反应",
        label_en="Reaction",
        summary="综艺/直播切片风格：情绪化短句 + 表情包语言",
        structure_hint="按情绪曲线梳理（惊讶/笑场/破防/反转）",
        plan_focus="OST=1 留给最有梗的现场原声；OST=0 主要做情绪推动",
        writing_focus="多语气词与拟声词；句短情绪重；可使用网络流行语",
    ),
    "tutorial": ModeProfile(
        id="tutorial",
        label_zh="教学科普",
        label_en="Tutorial",
        summary="知识/科普风格：步骤化讲解，要点强调",
        structure_hint="把内容拆成步骤/概念点，列出可示范的片段",
        plan_focus="按“概念→示范→易错点→总结”选片段；OST=1 留给关键演示",
        writing_focus="使用第一/我们；每段一个要点；先结论后展开；多用过渡词",
    ),
}


# ---------------------------------------------------------------------------
# Tones — narrator persona
# ---------------------------------------------------------------------------

DEFAULT_TONE_ID = "objective"
TONE_PROFILES: dict[str, ToneProfile] = {
    "objective": ToneProfile(
        id="objective",
        label_zh="冷静客观",
        label_en="Objective",
        voice_brief="冷静、克制、纪录片旁白般的口吻；避免主观形容",
        do_examples=("不偏不倚地陈述事件", "用事实和数据说话"),
        avoid=("强烈情绪词", "网络流行语", "夸张感叹"),
    ),
    "passionate": ToneProfile(
        id="passionate",
        label_zh="激情感染",
        label_en="Passionate",
        voice_brief="带感染力、抑扬顿挫；像体育解说推情绪",
        do_examples=("强动词、强节奏感", "用反复推动高潮"),
        avoid=("平淡陈述", "过度细节"),
    ),
    "humorous": ToneProfile(
        id="humorous",
        label_zh="幽默轻松",
        label_en="Humorous",
        voice_brief="幽默、自嘲、轻松；像老 4/木鱼水心轻松向",
        do_examples=("反差段子", "自我调侃", "口语化短句"),
        avoid=("冷酷讽刺", "人身攻击"),
    ),
    "sarcastic": ToneProfile(
        id="sarcastic",
        label_zh="毒舌锐评",
        label_en="Sarcastic",
        voice_brief="毒舌、阴阳怪气；像 B 站锐评 up",
        do_examples=("反讽、阴阳词", "把镜头里的离谱点放大"),
        avoid=("脏话", "歧视性表达", "人身攻击"),
    ),
    "suspenseful": ToneProfile(
        id="suspenseful",
        label_zh="悬疑神秘",
        label_en="Suspenseful",
        voice_brief="压低声线、神秘；像悬疑频道",
        do_examples=("留白与反问", "暗示未知威胁", "用细节制造不安"),
        avoid=("直接给答案", "过度情绪化"),
    ),
    "chill": ToneProfile(
        id="chill",
        label_zh="慵懒治愈",
        label_en="Chill",
        voice_brief="慵懒、ASMR 感、深夜电台口吻",
        do_examples=("长句呼吸感", "温柔承接", "用比喻软化冲突"),
        avoid=("强动词", "网络梗"),
    ),
    "dramatic": ToneProfile(
        id="dramatic",
        label_zh="戏剧夸张",
        label_en="Dramatic",
        voice_brief="戏剧化、夸张、译制片配音腔",
        do_examples=("强对比", "戏剧化定语", "把日常事件抬到史诗高度"),
        avoid=("平铺直叙"),
    ),
    "professional": ToneProfile(
        id="professional",
        label_zh="严肃专业",
        label_en="Professional",
        voice_brief="严肃、行业专家；像财经/科技解读",
        do_examples=("术语准确", "结论先行", "引用数据"),
        avoid=("感叹号", "网络流行语", "情绪化形容"),
    ),
}


# ---------------------------------------------------------------------------
# Pacing — segment density
# ---------------------------------------------------------------------------

DEFAULT_PACING_ID = "balanced"
PACING_PROFILES: dict[str, PacingProfile] = {
    "sparse": PacingProfile(
        id="sparse",
        label_zh="克制留白",
        label_en="Sparse",
        avg_segment_sec=12.0,
        cps_zh=3.8,
        sentence_style="short",
        silence_tolerance_sec=1.2,
    ),
    "balanced": PacingProfile(
        id="balanced",
        label_zh="标准",
        label_en="Balanced",
        avg_segment_sec=8.0,
        cps_zh=4.8,
        sentence_style="natural",
        silence_tolerance_sec=0.6,
    ),
    "dense": PacingProfile(
        id="dense",
        label_zh="密集快节奏",
        label_en="Dense",
        avg_segment_sec=5.0,
        cps_zh=5.5,
        sentence_style="long",
        silence_tolerance_sec=0.2,
    ),
}


# ---------------------------------------------------------------------------
# Perspective — narrative person
# ---------------------------------------------------------------------------

DEFAULT_PERSPECTIVE_ID = "third_person"
PERSPECTIVE_PROFILES: dict[str, PerspectiveProfile] = {
    "third_person": PerspectiveProfile(
        id="third_person",
        label_zh="第三人称（默认）",
        label_en="Third-person",
        instruction="使用第三人称客观叙述（“他/她/他们”），避免代入角色",
        example="他没想到的是，那扇门后藏着更大的秘密。",
    ),
    "first_person_narrator": PerspectiveProfile(
        id="first_person_narrator",
        label_zh="第一人称（解说者）",
        label_en="First-person (Narrator)",
        instruction="使用解说者第一人称（“我/我们”），像在和观众一起看",
        example="我们来看这一幕——主角的表情已经说明了一切。",
    ),
    "first_person_protagonist": PerspectiveProfile(
        id="first_person_protagonist",
        label_zh="第一人称（主角视角）",
        label_en="First-person (Protagonist)",
        instruction="使用主角内心独白的第一人称（“我”），代入主角情绪",
        example="我此刻只想转身离开，可脚下却像生了根。",
    ),
    "second_person": PerspectiveProfile(
        id="second_person",
        label_zh="第二人称（对观众）",
        label_en="Second-person",
        instruction="使用第二人称直接对观众发问（“你/你以为”），强化互动",
        example="你以为故事到这就结束了？真正的反转才刚刚开始。",
    ),
    "god_view": PerspectiveProfile(
        id="god_view",
        label_zh="上帝视角",
        label_en="Omniscient",
        instruction="使用全知视角，可提前暗示尚未揭晓的命运转折",
        example="命运的齿轮已经开始转动，只是他还没意识到。",
    ),
}


# ---------------------------------------------------------------------------
# Audience — platform language conventions
# ---------------------------------------------------------------------------

DEFAULT_AUDIENCE_ID = "generic"
AUDIENCE_PROFILES: dict[str, AudienceProfile] = {
    "generic": AudienceProfile(
        id="generic",
        label_zh="通用",
        label_en="Generic",
        language_brief="保持中立、可读性优先；面向广泛观众",
        allow_phrases=(),
        banned_phrases=(),
    ),
    "bilibili": AudienceProfile(
        id="bilibili",
        label_zh="B 站",
        label_en="bilibili",
        language_brief="允许 ACGN 用语和适度梗，整体偏年轻、有梗",
        allow_phrases=("注意看", "下饭", "名场面", "整活"),
        banned_phrases=("家人们谁懂啊", "真的，我哭死"),
    ),
    "douyin": AudienceProfile(
        id="douyin",
        label_zh="抖音/短视频",
        label_en="Douyin / Short-form",
        language_brief="短句、强钩子、前 3 秒抓人；句尾留悬念",
        allow_phrases=("注意看", "这个男人叫小帅", "下一秒就翻车"),
        banned_phrases=("众所周知", "如众所知"),
    ),
    "xiaohongshu": AudienceProfile(
        id="xiaohongshu",
        label_zh="小红书",
        label_en="Xiaohongshu",
        language_brief="软种草、情绪共鸣、口语化短句；可带轻情绪标签",
        allow_phrases=("真的爱了", "氛围感拉满", "破防"),
        banned_phrases=("注意看", "整活"),
    ),
    "youtube_long": AudienceProfile(
        id="youtube_long",
        label_zh="YouTube 长视频",
        label_en="YouTube Long-form",
        language_brief="完整起承转合，允许铺垫与回扣；克制使用流行语",
        allow_phrases=("回到刚才的镜头", "我们稍后会回到这里"),
        banned_phrases=("家人们", "整活"),
    ),
    "wechat_video": AudienceProfile(
        id="wechat_video",
        label_zh="微信视频号",
        label_en="WeChat Channels",
        language_brief="中产语境、克制、温和；避免过度网络化表达",
        allow_phrases=(),
        banned_phrases=("整活", "破防", "原来如此简单"),
    ),
    "professional_b2b": AudienceProfile(
        id="professional_b2b",
        label_zh="专业 B 端",
        label_en="Professional / B2B",
        language_brief="术语严谨、结论先行、避免娱乐化表达",
        allow_phrases=(),
        banned_phrases=("整活", "破防", "下饭", "名场面"),
    ),
}


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------


def resolve_mode(value: str | None) -> ModeProfile:
    return MODE_PROFILES.get((value or "").strip() or DEFAULT_MODE_ID, MODE_PROFILES[DEFAULT_MODE_ID])


def resolve_tone(value: str | None) -> ToneProfile:
    return TONE_PROFILES.get((value or "").strip() or DEFAULT_TONE_ID, TONE_PROFILES[DEFAULT_TONE_ID])


def resolve_pacing(value: str | None) -> PacingProfile:
    return PACING_PROFILES.get((value or "").strip() or DEFAULT_PACING_ID, PACING_PROFILES[DEFAULT_PACING_ID])


def resolve_perspective(value: str | None) -> PerspectiveProfile:
    return PERSPECTIVE_PROFILES.get(
        (value or "").strip() or DEFAULT_PERSPECTIVE_ID, PERSPECTIVE_PROFILES[DEFAULT_PERSPECTIVE_ID]
    )


def resolve_audience(value: str | None) -> AudienceProfile:
    return AUDIENCE_PROFILES.get(
        (value or "").strip() or DEFAULT_AUDIENCE_ID, AUDIENCE_PROFILES[DEFAULT_AUDIENCE_ID]
    )


def chars_per_second(pacing: PacingProfile, language: str) -> float:
    """Language-aware spoken pacing used by both the planner and the writer."""
    lang = (language or "zh").strip().lower()
    if lang.startswith("zh") or lang.startswith("ja"):
        return pacing.cps_zh
    # Romance / English-like: ~0.45 chars/sec relative to zh CJK density.
    return round(pacing.cps_zh * 0.45, 2)


__all__ = [
    "AUDIENCE_PROFILES",
    "AudienceProfile",
    "DEFAULT_AUDIENCE_ID",
    "DEFAULT_MODE_ID",
    "DEFAULT_PACING_ID",
    "DEFAULT_PERSPECTIVE_ID",
    "DEFAULT_TONE_ID",
    "MODE_PROFILES",
    "ModeProfile",
    "PACING_PROFILES",
    "PERSPECTIVE_PROFILES",
    "PacingProfile",
    "PerspectiveProfile",
    "TONE_PROFILES",
    "ToneProfile",
    "chars_per_second",
    "resolve_audience",
    "resolve_mode",
    "resolve_pacing",
    "resolve_perspective",
    "resolve_tone",
]
