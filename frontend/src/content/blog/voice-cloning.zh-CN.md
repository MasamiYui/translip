---
title: 借一段声音，去说它从没说过的话——音色克隆与语音合成
slug: voice-cloning
date: 2026-07-07
category: 算法
tags: [音色克隆, 语音合成, TTS, 零样本, MOSS-TTS-Nano, VoxCPM2, ECAPA, 配音]
summary: 上一站把"谁"钉成了稳定身份，评测那篇又特意说"不讲怎么配"——这一篇就来补上：怎么让一个角色，用他自己的嗓子，去说一句他从没说过、还换了语种的台词。聊零样本音色克隆怎么把"音色"当成一段提示词，怎么挑一段像样的参考，一个接口怎么挂着三台引擎、默认为什么是最"轻"的那台，以及生成完为什么一定要让机器把自己说的话再听一遍。
cover: /blog/voice-cloning/fig-voice-cloning-cover.svg
author: translip
readingTime: 15
---

# 借一段声音，去说它从没说过的话——音色克隆与语音合成

> 这是 **幕后 · 博客** 的第七篇，回到**算法线**。[第三篇](/blog/speaker-registry) 我们把"谁"钉成了一个跨片段稳定的身份 `spk_0000`，结尾留下一句话：**Task B 把"谁"钉死，Task D 才能让"谁"始终用同一把嗓子说话。** 这一篇就来兑现那把嗓子。另外，[配音评测那篇](/blog/dub-evaluation) 开头特意声明"不讲怎么配，只讲怎么判断配得好不好"——欠下的"怎么配"，也在这里还上。

## 这一站要解决的，是一个近乎魔术的问题

把前面几站的产物摆到桌面上：

- Task B 给了我们一个稳定身份，外加这个人的**几段参考语音**（每段几秒到十几秒，附带文字）；
- Task C 把他的台词翻成了目标语言，落成 `translation.en.json`——一句句**他从没用这个语种说过的话**。

Task D（CLI 的 `synthesize-speaker`）要做的事，一句话就能说清，但听起来不太可能：

> **让这个角色，用他自己的音色，把那些译好的台词一句句念出来——哪怕他这辈子没说过一个英文单词。**

这就是**音色克隆 + 语音合成**：先"借"来一个人的音色，再用这个音色去合成全新的语音。难点不在"合成一句英文"——随便一个 TTS 都会念英文；难点在**那句英文得听起来像是他**。

## 零样本克隆：把"音色"当成一段提示词

最朴素的想法，是给每个角色**训练一个专属语音模型**。但这条路在我们的场景里走不通——一部剧几十个角色，每个都要采数据、跑训练、存权重，工程量和时间都不可接受；而且很多配角全片就那么几句话，**根本不够训一个模型**。

现代 TTS 给了另一条路：**零样本（zero-shot）克隆**。模型本身只训练一次、对所有人通用；要克隆某个人，你不动模型的任何权重，只是在**推理时**塞给它一段那个人的参考音频——模型当场把这段音频里的音色"读"出来，套到你给的新文本上。

换个说法最直观：**那段参考音频，就是一句"音色提示词"。** 就像你给一个大语言模型几个例子让它照着风格往下写，你给 TTS 几秒钟某人的声音，让它照着这个音色往下念。台词是新的，语种是新的，但音色是借来的。

这件事在代码里的形状，干净得有点出乎意料。所有后端共享同一个数据契约——一个**参考包**进去，一段**带音色的音频**出来：

```python
# dubbing/backend.py —— 克隆的最小契约：参考音色 + 目标文本 → 一段音频
@dataclass(slots=True)
class ReferencePackage:
    speaker_id: str
    prepared_audio_path: Path   # 这段音频，就是"音色提示词"
    text: str                   # 参考音频对应的文字（有些后端要，有些不要）
    duration_sec: float
    score: float                # 这段参考有多"像样"（见下一节）
    selection_reason: str       # 为什么挑它——可解释，不随机

class TTSBackend(Protocol):
    def synthesize(
        self, *, reference: ReferencePackage, segment: SynthSegmentInput, output_path: Path
    ) -> SynthSegmentOutput: ...
```

注意 `ReferencePackage` 里既有音频又有 `text`。这是因为不同模型对"提示词"的胃口不一样：有的只看音频（纯听音色），有的还想顺带读一遍参考的文字（音频 + 文本一起对齐，克隆更稳）。这个差异后面会再回来。

既然音色是从参考里"借"的，那么**整套合成的天花板，从挑参考的那一刻就定下了一半**。所以这一站的第一步，根本不是合成，而是——挑一段像样的参考。

## 第一步：挑一段像样的参考

不是这个人的每一句话都配当"音色提示词"。一段一秒半的"嗯。"、一段背景嘈杂的喊叫、一段笑场——拿它去克隆，模型会忠实地把这些毛病一起学过去。所以 `reference.py` 的活儿，是从 Task B 攒下的参考片段里，**挑出条件最稳的那一段**。

它不靠玄学，靠一个**可解释的打分**：时长、文本信息量、响度三项加权，再扣掉风险分。

```python
# dubbing/reference.py —— 参考片段打分：时长 0.5 + 文本 0.3 + 响度 0.2 − 风险
total = (duration_score * 0.5) + (text_score * 0.3) + (rms_score * 0.2) - risk_penalty
reason = f"duration={duration_score:.2f},text={text_score:.2f},rms={rms_score:.2f},risk=-{risk_penalty:.2f}"
```

每一项都对着"什么是好音色样本"：

- **时长——最看重，但要的不是越长越好。** 理想区间钉在 **8–10.5 秒**：太短，音色信息不够、克隆不稳；太长，反而引入更多风格漂移和杂音。这里追求的是"条件稳定"，不是"信息尽量多"——一个干净的 timbre anchor，胜过一段冗长嘈杂的上下文。

```python
# dubbing/reference.py —— 8–10.5s 给满分，越偏离这个甜区扣得越多
IDEAL_REFERENCE_MIN_SEC = 8.0
IDEAL_REFERENCE_MAX_SEC = 10.5
HARD_REFERENCE_MIN_SEC  = 5.0     # 低于 5s 直接不要
HARD_REFERENCE_MAX_SEC  = 15.0    # 高于 15s 直接不要
```

- **文本信息量。** 参考音频对应的文字越实、字数越够，越说明这段是正经说话、而不是一声叹息或语气词。
- **响度。** RMS 落在一个舒服的中间带最好——太轻可能是远场或气声，太响可能爆音。

最有意思的是**风险分**，因为它刚刚改过一版，记录了一次认知的修正：

```python
# dubbing/reference.py —— 只有"笑/语气填充"才是坏音色样本；情绪强调反而是好素材
def _risk_penalty(text: str) -> float:
    # Only laughter/filler makes a poor timbre reference (the clone inherits the
    # laugh). Mere emphasis ("!!", "??") is normal, expressive speech and is good
    # reference material — especially for dramatic content — so it is no longer
    # penalised, and the laughter penalty is softened from a near-disqualifier to
    # a tie-breaker.
    lowered = text.lower()
    if re.search(r"(哈哈|呵呵|hahaha|lol)", lowered):
        return 0.15
    return 0.0
```

早先的逻辑会把带 `!!`、`??` 的句子当"情绪化片段"压分。后来想通了：**对剧集这种戏剧化内容，带情绪的强调恰恰是最好的音色素材**——它能让克隆出来的声音也有那股劲儿。真正会"传染"的只有笑声（克隆会把那串"哈哈"一起学走），而那也从"几乎一票否决"降成了一个**平局裁判**。挑参考这件事，宁可把判断写成可解释的分数，也不写成一句拍脑袋的"看着不行"。

![一段像样的参考，是怎么被挑出来的](/blog/voice-cloning/fig-reference-selection.svg)
*同一个人的几段候选语音，各自按"时长 + 文本 + 响度 − 风险"打分；8–10.5 秒的甜区给满分，太短/太吵/笑场的被压到后面，最高分胜出，并附一行 selection_reason。挑不出长片段时，还能把几段短的拼成一段。*

万一这个人**压根没有一段够长的干净参考**呢？不直接放弃，而是逐级兜底：先试着把几段短的**拼接**成一段达标的（`_concatenated_fallback`），还不行就退到**软兜底**——只要有 2 秒以上的可用片段，降权后也先用着（`_soft_fallback`）。每退一级，分数都乘一个折扣，让下游知道"这段参考是将就来的"。

挑中之后还有个小手艺：把参考**裁到 11 秒以内、尾巴补 1 秒静音**再喂给模型——给它一个干净的收尾，免得克隆音一头撞上参考的硬切口。

```python
# dubbing/reference.py —— 裁到 11s 上限，尾部补 1s 静音
clipped = waveform[:max_samples] if waveform.size > max_samples else waveform
silence = np.zeros(int(REFERENCE_TAIL_SILENCE_SEC * sample_rate), dtype=np.float32)
prepared = np.concatenate([clipped.astype(np.float32), silence])
```

## 第二步：一个接口，三台引擎

参考备好了，接下来才是合成。前面那个 `TTSBackend` 协议在这里收获了它的红利：**具体用哪台引擎，是一次注册表查表，而不是一串 `if/elif`。**

```python
# dubbing/registry.py —— 加一个 TTS 后端 = 注册一行；重活儿懒加载
@TTS_BACKENDS.register("moss-tts-nano-onnx", requires_reference_audio=True,
                       metadata={"supports_parallel_workers": True})       # 默认
def _build_moss(*, device="auto", worker_count_hint=None):
    from .moss_tts_nano_backend import MossTtsNanoOnnxBackend
    return MossTtsNanoOnnxBackend(requested_device=device, worker_count_hint=worker_count_hint)

@TTS_BACKENDS.register("qwen3tts", requires_reference_audio=True)
def _build_qwen(*, device="auto", worker_count_hint=None): ...

@TTS_BACKENDS.register("voxcpm2", requires_reference_audio=True,
                       metadata={"supports_reference_retry": True})
def _build_voxcpm(*, device="auto", worker_count_hint=None): ...
```

三台引擎，挂在同一个接口下，对调用方完全可换。但它们克隆的"手法"各有脾气，差异恰好落在三个有意思的地方：**要不要参考文本、怎么管住时长、跑在什么硬件上。**

**MOSS-TTS-Nano（默认）——只听音色，不读文本。** 它给 worker 的请求里，只有目标文本和那段参考音频，**没有 `ref_text`**：

```python
# dubbing/moss_tts_nano_backend.py —— 纯音频提示词，连参考的文字都不需要
payload = {
    "text": segment.target_text,                       # 要念的新台词
    "prompt_speech": str(reference.prepared_audio_path),  # 音色提示词（只此一项）
    "max_new_frames": self.max_new_frames,             # 用帧数上限兜住时长
    ...
}
```

它管时长的办法，是一个**帧数上限** `max_new_frames`（默认 375）——念到上限就收，省得一句话越说越长收不住。

**Qwen3-TTS——音频 + 文本，还能按预算算时长。** 它有两种克隆模式：`icl`（in-context，音频连着参考文本一起喂，更稳）和 `xvec`（只抽一个音色向量，不用文本）。更妙的是它把"该念多长"算成了一笔 token 预算——音频每秒约 12 个 token，照着时长预算留 1.25 倍余量：

```python
# dubbing/qwen_tts_backend.py —— 把"该多长"翻译成 token 预算
calibrated_budget = target_sec * _QWEN_AUDIO_TOKENS_PER_SEC * _QWEN_TOKEN_HEADROOM_RATIO  # 12 tok/s × 1.25
return max(_QWEN_MIN_NEW_TOKENS, min(_QWEN_MAX_NEW_TOKENS, int(round(calibrated_budget))))
```

**VoxCPM2——音色最像，但也最重。** 给了参考文本，它走"ultimate"克隆模式（音频 + 文本）；没有就退到只看音频。它带 CFG 引导强度、扩散式的推理步数、还有"坏样本自动重试"，48 kHz 原生采样——音质纹理通常是三台里最好的，代价是它最吃算力。

> **同一个"克隆"，三种实现。** 有的把音色当纯听觉提示（MOSS），有的要文本帮它对齐（Qwen `icl`、VoxCPM ultimate），有的把"该念多长"算成 token 预算、有的算成帧数上限。`runner.py` 一概不管这些细节——它只认 `synthesize()` 这一个口子。这正是上面那个 Protocol 抽象买来的东西：**换引擎不用改流程。**

![一个接口，三台引擎：要不要文本、怎么管时长、跑在哪](/blog/voice-cloning/fig-three-backends.svg)
*同一个 ReferencePackage + 目标文本，进任意一台引擎都能出音频。差异落在三处：是否需要参考文本、用什么旋钮兜住时长、以及跑在 CPU 还是 GPU。MOSS 最轻、纯本地，被选作默认。*

而**默认那台，偏偏是参数量最小的 MOSS-Nano**——这不是随手定的。

它的好处全长在"本地优先"那条线上（就是 [上一篇决策](/blog/local-first) 反复讲的那条）：100M 的 ONNX 模型，`resolved_device` 干脆**写死 CPU**——不挑显卡、不碰云、一台普通笔记本就能跑完整条配音。而且它能开**多 worker 并行**（注册元数据里那个 `supports_parallel_workers`），一句句台词分给一池子进程同时合成。

为了让"本地小模型"不至于慢得难受，这台后端还藏了一个工程小心思——**常驻 worker 池**：加载一次模型要好几秒，与其每句话都重启一遍，不如让进程**活着**、模型**留在内存里**，一句接一句地喂。池子启动时还有个并发技巧：先把所有 worker 进程都拉起来（这一步不阻塞），再让它们**一起**加载模型，而不是一个个排队等——

```python
# dubbing/moss_tts_nano_backend.py —— 先全部拉起，再并发加载，省掉串行的暖机
workers = [self._spawn_worker() for _ in range(self.pool_size)]   # 非阻塞地起进程
for worker in workers:
    worker.wait_ready()                                            # 再并发等模型就绪
    pool.put(worker)
```

这也呼应了 [流水线编排那篇](/blog/pipeline-orchestration) 的味道：重活儿关在独立子进程里，主流程只管发文本、收音频。

当然，得诚实地说出它的天花板：**100M 的小模型，音色像不像是有上限的。** 对音色要求更高的片子，你可以一行 `--backend voxcpm2` 切到更重、更像、但更吃算力的引擎。默认值是替绝大多数"先跑通、跑在本机"的场景定的——什么时候该覆盖它，这把选择权一直留在你手里。

## 第三步：让机器把自己说的话，再听一遍

合成出一段音频，**绝不等于**这段配音可用。生成模型会出各种幺蛾子：音色飘了、把词吞了、一句话拖得老长、甚至吐出一段近乎静音。所以每合成一句，Task D 都立刻给它做一次**三轴体检**，而且——关键——**让机器亲自把这段音频再"听"一遍来验收**，而不是信口说一句"我念好了"。

```python
# dubbing/metrics.py —— 每段配音过三关，取最差的那一关定生死
overall = _overall_status(speaker_status, intelligibility_status, duration_status)
#   speaker        音色像不像原参考      ECAPA 余弦   ≥0.45 过 / ≥0.25 存疑 / 否则败
#   intelligibility 词念全了没           backread ASR ≥0.9 过 / ≥0.7 存疑 / 否则败
#   duration       时长合不合理          generated/source  0.7–1.35 过
```

三关里，**第二关最像一记回马枪**。怎么知道合成音"有没有把词念全、念对"？办法朴素得近乎狡黠：**把刚生成的音频，重新做一次 ASR，转回文字，再跟原本要它念的目标文本比一比**——

```python
# dubbing/metrics.py —— backread：把合成音再转写一遍，和目标文本算相似度
backread_text = _backread_text(generated_audio_path, target_lang=..., model_name=...)
text_similarity = difflib.SequenceMatcher(a=norm(target_text), b=norm(backread_text)).ratio()
```

这一步我们叫它 **backread（回读）**。它专治一类隐蔽的毛病：音色明明挺像、时长也正常，但模型偷偷把半句话**吞**了，或者念成了一串含混的音。这种"听着是那个人、但根本没把台词说清楚"的失败，单看音色相似度完全无感——可你让它把自己念的再转写一遍，缺的字、糊的词，当场对不上。**让生成器去通过一道它自己也要参与的听写测验，比让它自我感觉良好可靠得多。**

第一关的**音色**，复用的正是 [Task B](/blog/speaker-registry) 那套 ECAPA 声纹——把合成音和参考各编成一个 192 维向量，算余弦。口径和"认人"那一站完全一致：同一把尺子，量到底。

> **细心的你可能发现：这三关，正是配音评测那篇里"摊开成一排仪器"的同一批信号。** 没错——只是位置不同。这里是**逐句的源头闸门**：不合格的句子，在 Task D 当场就被拦下、记下原因，根本不让它往时间线那一棒传。而[评测那篇](/blog/dub-evaluation) 是**事后的全片复盘**，把这些信号摊开给人看。同一组测量，一个把门，一个亮灯。

![生成完不算数，得让机器把自己说的话再听一遍](/blog/voice-cloning/fig-backread-gate.svg)
*一段合成音出来，立刻过三关：ECAPA 量音色、backread 把它重新转写回文字量可懂度、时长比量松紧。取最差的一关定 overall。不合格不是终点——还能换条参考、或重试一次。*

**不行就再来一次：一场小小的参考赛。** 体检不合格，Task D 不会认命。它会重试，而且重试得有章法：

- 吐出来一段近乎**静音**？同一条参考，再合成一两次（采样有随机性，下一次也许就正常了）。
- 音色/可懂度**偏弱**、而这台后端又支持换参考（VoxCPM2 的 `supports_reference_retry`）？那就**换下一条参考片段**再试——也许是这段提示词不够好，换一段就稳了。

所有尝试都留痕，最后**按分数挑出最好的那一次**胜出，其余的连同它们的得分一起写进报告：

```python
# dubbing/runner.py —— 所有尝试里，分数最高的那次胜出
selected = max(successful_attempts, key=lambda a: _attempt_score(a["_evaluation"]))
selected["status"] = "selected"
```

这是一种克制的 best-effort：**尽力多试几次、把最好的留下，但绝不假装每一句都完美**——每一次尝试的分数都摊在报告里，可复核。

## 一句"好。"，得借邻居的语气

还有一类句子，会专门给 TTS 添堵：**极短句**。一句孤零零的"好。"、"是吗？"、"走。"——单独丢给模型去合成，它往往念得别扭、甚至直接发飘，因为太短了，没有任何上下文撑起一个自然的语气。

Task D 的对策很像配音演员的本能：**别让这句话单独念，让它借一口邻居的气。** 几句相邻的、共享同一个上下文单元的短句，会被**合并成一段**一起合成（2–4 句、跨度不超过 8 秒），让模型在连贯的语流里把它们自然地念出来；之后再**按各自的时长比例切回**一句句独立的音频：

```python
# dubbing/runner.py —— 极短句合并成一个"单元"一起合成，再按时长切回去
def _should_synthesize_as_unit(rows) -> bool:
    if len(rows) < 2 or len(rows) > 4:          # 2–4 句才合并
        return False
    if float(rows[-1]["end"]) - float(rows[0]["start"]) > 8.0:  # 跨度别太大
        return False
    return any(_row_needs_dubbing_unit(row) for row in rows)     # 里头确有短到需要"搭伴"的
```

念的时候连贯、自然，切回去又保住了每句独立的 `segment_id`——下游的时间线回填，依旧拿到一句一段、边界清清楚楚的音频。**这是少数几个"为了让机器念得像人，先把题目改得像人会说话"的地方。**

![一句"好。"单独念会发飘，借邻居一口气就自然了](/blog/voice-cloning/fig-unit-synthesis.svg)
*极短句单独合成容易别扭甚至发飘；把相邻的几句短句并成一个单元一起念（语气连贯），再按时长比例切回独立片段——既要了自然的语流，又保住了一句一段的边界。*

## 一次 synthesize-speaker 的完整流程

把这些串起来，一次 Task D 是这样流动的：吃上游两站的产物，挑参考、逐句合成（带重试）、逐句体检，最后落下一份音频 + 报告 + 一段试听 demo。

![Task D 端到端：从译好的台词，到一句句带音色、自检过的配音](/blog/voice-cloning/fig-task-d-flow.svg)
*从 translation + speaker_profiles，到选参考 → 逐句合成（参考赛）→ 三轴自检 → 写回 speaker_segments / demo / manifest。不合格的句子在这一棒就被拦下，绝不偷偷溜进时间线。*

落到磁盘上的产物契约：

```text
output-synthesis/voice/spk_0000/
├── speaker_segments.en.json   # 每句：音频路径 + 音色/可懂度/时长三轴评估 + 所有尝试
├── speaker_demo.en.wav        # 把这个人的句子拼一段，方便你直接试听
├── segments/<segment_id>.wav  # 一句一段的配音音频（下一站的直接输入）
└── synthesis-manifest.json       # 后端 / 设备 / 参考选择 / 各状态计数
```

一个最小调用（吃上 Task B 的画像和 Task C 的译文，给某个 `speaker_id` 逐句配音）：

```bash
uv run translip synthesize-speaker \
  --translation ./output-translation/voice/translation.en.json \
  --profiles    ./output-speaker-registry/voice/speaker_profiles.json \
  --speaker-id  spk_0000 \
  --backend     moss-tts-nano-onnx \
  --output-dir  ./output-synthesis --device auto
```

挑谁来配、配哪几句，也都是可解释的：`planning.py` 只挑**可克隆**的说话人（手动标了 `non_cloneable` 的——比如那其实是背景人声——一律跳过，尊重[说话人复核里](/blog/speaker-registry)那个"人在环中"的决定），段落则优先 **1–6 秒**、不带"源句过短"标记的，把最稳的句子先配上。

## 几条"为什么这么做"

把这一站的取舍收拢一下：

- **音色是借的，所以挑参考是第一等大事。** 整条克隆的天花板，一半在挑参考那一刻就定了。所以宁可把"哪段参考好"写成一个可解释的分数（时长 / 文本 / 响度 − 风险），也不随机抓一段——`selection_reason` 让每一次选择都说得清。
- **一个接口，三台引擎，默认选最"轻"的那台。** 用 Protocol 把"怎么克隆"和"跑什么流程"解耦，换后端不改流程。默认 MOSS-Nano 是为"先跑通、跑在本机、不碰云"定的；音色要更像，显式切 VoxCPM2——选择权在你。
- **生成完必自检，而且让机器亲自再听一遍。** ECAPA 量音色、backread 把合成音重新转写量可懂度、时长比量松紧，取最差定生死。质量门控**前置**在 Task D，不合格的句子当场拦下，绝不顺手塞进时间线。
- **尽力重试，但不假装完美。** 静音就重来、弱了就换参考、最好的尝试胜出——每一次尝试连同分数都留痕。best-effort，但可复核。
- **为了让机器念得像人，先把题目改得像人会说话。** 极短句借邻居一口气一起念、再切回去，自然了，边界也没丢。

## 小结

Task D 把[上一站钉死的身份](/blog/speaker-registry)，变成了一把真正能开口的嗓子：先挑一段最像样的参考、把"音色"当成一句提示词喂给零样本 TTS，再让生成的每一句都过一道"机器亲自回听"的三轴体检——不合格就重试，最好的留下，不行的当场拦住。一个接口下挂着三台脾气各异的引擎，默认那台最轻、最本地，天花板也最诚实地写在那里。

但配出来的句子，还远不能直接交差：它们长短不一——这句拖过了头、那句又太赶——而且是一条**干**的人声，没有原片的环境和背景。下一篇算法，我们走到流水线的最后一棒 **Task E：时间线贴合与混音**——怎么把这些长短不齐的句子，**塞回原片那一格格的时间线**（拉伸、压缩、还是干脆让一让），再和分离出来的背景**重新混**成一条能交付的声音。
