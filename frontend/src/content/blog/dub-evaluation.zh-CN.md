---
title: 不要一个更聪明的分数——配音质量，要看得见的证据
slug: dub-evaluation
date: 2026-06-04
category: 决策
tags: [配音评测, 质量, 音色, 可视化, ECAPA, 梅尔频谱, 决策记录]
summary: 这是博客的第二篇决策记录——聊一个具体而棘手的问题：一段配音到底配得好不好，这件事能不能交给一个分数。我们的答案是不能。讲讲为什么先要把账算诚实（漏配不藏、存疑不折叠、覆盖率锚在译文全集），再把那个数字摊开成一排看得见的仪器——音色三态热条、ECAPA embedding 散点、音高轮廓、梅尔频谱、说话人雷达——让机器只管标记，把裁决连同证据一起交回给人。
cover: /blog/dub-evaluation/fig-dub-evaluation-cover.svg
author: translip
readingTime: 15
---

# 不要一个更聪明的分数——配音质量，要看得见的证据

> 这是 **幕后 · 博客** 的第六篇，也是第二篇**决策记录**。上一篇决策聊"本地优先"，落点是一种态度：让重要的事情**显式、可见、可审计**。这一篇把同一种态度用到一个具体而棘手的问题上——一段配音，到底配得好不好；以及，这件事能不能交给一个分数。

## 这一篇不讲"怎么配"，讲"怎么判断配得好不好"

前面的算法篇，每一篇都在讲一站如何把数据往前推：分离、转写、认人、翻译、配音、混音。配音是这条流水线的最后一棒。但"推完了"不等于"推好了"——一条片子跑完，你手里是一个成片，和一个挥之不去的问题：**它到底行不行？**

最自然的冲动，是给它打个分。translip 一开始也是这么做的：`dub_benchmark` 读完混音报告，吐一个 0–100 的分，外加一个 `deliverable / review / blocked` 的交付状态。它不是没用——但很快你就会撞上它的天花板。

> **一个分数是分诊信号，不是解释。它能告诉你"这条片子大概有问题"，却答不出"哪几句、为什么、有多糟"——而后者才是你真正要动手去修的东西。**

所以配音评测在 translip 里经历了两次"诚实化"。第一次，把**账**算诚实——别让分数虚高、别让问题段隐身。第二次，也是这篇的主角，把那一个数字**摊开**成一排看得见的仪器：与其给你一个更聪明的分数，不如把测量信号本身交到你眼前。

![从一个分数，到一排看得见的仪器](/blog/dub-evaluation/fig-score-to-instruments.svg)
*上：一个 0–100 的分，是分诊信号，不是解释——它说"有问题"，但说不清哪几句、为什么。下：五件仪器，每一件回答一个具体的问题。评测的重心，从"下判决"挪到"出证据"。*

## 起点：一个诚实、但只会读盘的分数

第二次诚实化的成果，是评测页背后的 `dub_qa`。它的活儿，一句话能讲清：

```python
# quality/dub_qa.py —— 它不测量，它把各阶段的产物按 segment_id 拼回来
# joins the per-stage artifacts back together by ``segment_id`` to answer
# the operator's concrete questions:
#   * which segments were never dubbed (left out of the final mix)?
#   * which have a timbre / speaker mismatch?
#   * which dropped words (the synthesized audio doesn't read back the translation)?
#   * which are paced badly / inaudible / poorly translated?
#
# Nothing here runs ML models except the optional translation judge;
# everything else is a cheap on-disk join.
```

它做对的最大一件事，是**段落全集锚定在译文上，而不是混音报告上**。这个区别听起来很学究，但它堵住了一个真实的盲点：

```python
# quality/dub_qa.py —— 该被配的一切 = 译文全集 ∪ 渲染器报告过的
# The universe is everything that *should* be dubbed: every translated
# segment, plus anything the renderer reported. A translated segment that
# never reached the mix (e.g. its speaker was dropped before synthesis) is
# an undubbed line — the exact "有些地方没配" failure operators want to find.
```

为什么重要？因为一个说话人可能在配音前就被丢掉了（采样太少、被标了 `non_cloneable`），它那几句译文**根本不会出现在混音报告里**——不在 `placed`，也不在 `skipped`，就这么凭空消失。如果评测的分母跟着混音报告走，它会一脸诚恳地报告 `coverage = 100%`，而实际上半条片子的台词没配上。把分母锚到译文全集，这些"译了却没配"的台词才会现形为 `undubbed`。

在这个诚实的全集之上，`dub_qa` 给每一段贴最多七类问题标签：

```python
# quality/dub_qa.py —— 每段最多贴这七类问题
ISSUE_UNDUBBED        = "undubbed"           # 漏配：译了，却没进最终混音
ISSUE_TIMBRE          = "timbre_mismatch"    # 音色不像原角色
ISSUE_DROPOUT         = "dropout"            # 吞字：合成音读不回译文
ISSUE_PACING          = "pacing"            # 节奏：过度拉伸/压缩
ISSUE_INTELLIGIBILITY = "low_intelligibility"
ISSUE_INAUDIBLE       = "inaudible"          # 被背景盖住，字幕窗里听不清
ISSUE_TRANSLATION     = "bad_translation"    # 译文差（可选 LLM 裁判）
```

到这里，评测是诚实的。但它有一个根上的局限，那行注释自己已经招了：**它只读盘，不测量**。除了那个可选的翻译裁判，它不碰一个字节的音频——它读的是上游（synthesis 配音、render 混音）早就算好的状态字段，再卡个阈值贴标签。于是它的盲点，全都继承自上游：**上游把一个微妙的差别压成一个 `ok / failed`，它就只能跟着说 `ok / failed`。**

而有一个维度，被压成一个 `ok / failed` 时，丢掉的信息最多——音色。

## 音色：最不该被一个数字概括的维度

"这段配音，像不像原来那个角色的声音？"——这是配音里最要命的问题，也是最不该被一个标量草草了结的问题。原因有三层：

1. **跨语种本来就压分。** 我们用 ECAPA-TDNN 给说话人嵌入向量、算余弦相似度。可中文原声和英文配音，声学上天然就差一截，余弦分被这种语种差异本身拉低——不是配音不像，是尺子在跨语种这段不准。
2. **参照物可疑。** 逐段的 `speaker_similarity` 比的是配音 vs. TTS 自己的克隆 prompt。这测的是"TTS 有没有还原它自己的 prompt"，离"像不像原角色"还隔着一层。
3. **0.25–0.45 本就是一条模糊地带。** 在这条带里，光凭一个数字根本判不了死活。

旧的做法，是装作阈值能了结这一切：只有相似度 `< 0.25` 才标 `failed`，0.25–0.45 这条**存疑带**被静默丢弃。在一条真实任务上，27 段配音里有 17 段落在这条带里——而界面上只显示"音色不符 1"。十七段悬而未决的音色，被一个阈值抹成了沉默。

新的做法，不再假装那个阈值能替你拍板。`WaveformCompare`——原本只是原片/配音两条波形——多了一条**音色三态热条**，沿着同一条时间轴，把每段的余弦分摊开成三种颜色：

```ts
// components/evaluation/WaveformCompare.tsx —— 不再非黑即白，而是三态 + 无数据
function timbreBucket(score: number | null | undefined): TimbreBucket {
  if (typeof score !== 'number' || Number.isNaN(score)) return 'unknown'
  if (score >= 0.45) return 'good'      // 相符
  if (score >= 0.25) return 'review'    // 存疑 —— 不再被丢掉，而是被看见
  return 'bad'                          // 不符
}
```

界面上的图例，把这三态写得明明白白：

```text
■ 相符 ≥ 0.45     ■ 存疑 0.25–0.45     ■ 不符 < 0.25     ▢ 无数据
```

关键不在于把"存疑"也算成不合格——那只是把一种武断换成另一种。关键在于**让它现形**：哪几段悬而未决、悬在时间轴的哪个位置，一目了然，然后把最后那一下，交给你的耳朵去裁决。这就是态度从"判决"到"证据"的第一步。

![音色：把被丢掉的"存疑带"摆上台面](/blog/dub-evaluation/fig-timbre-three-states.svg)
*同一条余弦相似度的轴，旧逻辑只在 <0.25 处亮一盏红灯，中间那条宽阔的"存疑带"整段沉默；新的三态热条把它沿时间轴摊开——红/琥珀/绿一字排开，存疑段第一次有了自己的颜色。*

## 三把"看得见"的仪器

但热条说到底，还是建立在那个被压扁的余弦分上。要真正回答"像不像"，得绕开标量，回到**音频本身**去测。这正是这批新代码做的事——三个模块，亲自测量，各回答一个余弦分回答不了的问题。

它们有一个共同的形状：都是 `dub_qa` 写完报告**之后**才跑的 best-effort"富集器"，一个都不会挡住报告：

```python
# quality/dub_qa.py —— 报告先落盘，再尽力富集；任何一个挂了都不影响报告
try:
    from .dub_embeddings import enrich_report_with_embeddings
    enrich_report_with_embeddings(report, pipeline_root=root)   # 192 维音色向量
except Exception as exc:  # never fail the report write
    report["embedding_meta"] = {"status": "error", "reason": str(exc)}

try:
    from .dub_pitch import enrich_report_with_pitch
    enrich_report_with_pitch(report, pipeline_root=root)        # F0 音高轮廓
except Exception as exc:
    report["pitch_meta"] = {"status": "error", "reason": str(exc)}

try:
    from .dub_mel import enrich_report_with_mel
    enrich_report_with_mel(report, pipeline_root=root)          # 梅尔频谱
except Exception as exc:
    report["mel_meta"] = {"status": "error", "reason": str(exc)}
```

**① 音色 embedding 散点：这一段，聚到对的人身上了吗？**

`dub_qa` 把音色塌成了一个余弦分；但散点图要的不是那个分，是分**之前**的东西——原始向量：

```python
# quality/dub_embeddings.py —— 别塌成一个余弦，把 192 维向量本身留下来
# The dub-qa pipeline normally collapses each segment's speaker embedding
# into a single ``speaker_similarity`` scalar (the cosine vs. its reference
# clip). For the embedding-scatter visualization we need the underlying
# 192-dim vectors themselves, so the UI can run PCA projections client-side.
```

于是每段配音被重新嵌成一个 192 维 ECAPA 向量，连同每个说话人的参考向量一起塞进报告。前端把它们一起 PCA 降到二维：同色是同一个人，菱形 ◇ 是参考音色。一段配音要是飘离了自己那一簇、滑向别人——肉眼立刻看见。这是单个余弦分给不了的**全局结构**：它只告诉你"这段离它的参考有多远"，散点图告诉你"它到底落在了谁的地盘上"。

降维偏偏选了最朴素的 PCA，而不是更花哨的 t-SNE / UMAP，理由写在注释里，且与"本地优先"那篇一脉相承：

```ts
// components/evaluation/EmbeddingScatter.tsx —— 为什么是 PCA，不是 t-SNE/UMAP
// - it has zero hyperparameters (so the picture is reproducible across reruns)
// - on ECAPA embeddings the first two PCs already separate speakers well
// - it's tiny — runs in a few ms for typical loads.
```

**可复现**——同一份报告，每次画出同一张图。这正是上一篇里"钉死的本地权重胜过会在你脚下变的云模型"那条原则，换了个场景再说一遍。

**② 音高轮廓：配音跟上原片的语调了吗？**

```python
# quality/dub_pitch.py —— librosa.pyin 抽基频曲线 [(秒, Hz 或 None), ...]
f0, _voiced_flag, _voiced_prob = librosa.pyin(
    waveform.astype(np.float32),
    fmin=PITCH_FMIN_HZ, fmax=PITCH_FMAX_HZ,   # 65 ~ 1000 Hz
    sr=sample_rate,
    frame_length=PITCH_FRAME_LENGTH, hop_length=PITCH_HOP_LENGTH,
)
```

原片画成灰线、配音画成蓝线，叠在同一张对数 Hz 图上；右上角再给一个**半音偏移**徽章，是配音中位数音高相对原片的偏移：

```ts
// components/evaluation/PitchContourCompare.tsx —— 中位数音高差几个半音
function semitones(a: number, b: number): number {
  return 12 * Math.log2(a / b)
}
// ≤1 半音 → 绿；≤2.5 → 琥珀；再大 → 红
```

它抓的是余弦分抓不到的东西：一段配音完全可能**音色对、语调死**——句子读平了、问句没扬上去、情绪该起伏的地方一条直线。音色相似度对这种毛病几乎无感，但音高曲线一画就露馅。

**③ 梅尔频谱：音质的纹理，像不像？**

```python
# quality/dub_mel.py —— 64 维 log-mel，量化成 uint8 好塞进 JSON
db   = librosa.power_to_db(mel, ref=np.max, top_db=-DB_MIN)   # ≈ [-80, 0] dB
norm = (np.clip(db, DB_MIN, DB_MAX) - DB_MIN) / (DB_MAX - DB_MIN)
mel_uint8 = np.clip(np.round(norm * 255.0), 0, 255).astype(np.uint8)
```

上方一条是原片、下方一条是配音，viridis 色带把能量画成热图。它让你一眼看出共振峰的位置、谐波的结构、以及配音有没有那种 TTS 特有的"塑料感"或者糊成一团的高频——这些"音质纹理"层面的毛病，是任何一个标量都概括不了的。

![三把仪器，各回答一个余弦分回答不了的问题](/blog/dub-evaluation/fig-three-instruments.svg)
*左：embedding 散点——这段聚到对的人身上了吗（◇ 是参考音色）。中：音高轮廓——配音蓝线跟上了原片灰线的语调起伏吗。右：梅尔频谱——上原片下配音，音质纹理像不像。三种视角，三角定位同一个"像不像"。*

## 再把它们收成一张脸：说话人雷达

上面三把仪器都是给**单段**看的。但你常常想先问一个更粗的问题："哪个角色整体配崩了？"——`SpeakerRadar` 就是干这个的，它按说话人把逐段信号聚合成五个轴：

```ts
// components/evaluation/SpeakerRadar.tsx —— 按说话人聚合成 5 维 [0,1]
// - timbre:          mean speaker_similarity           音色一致性
// - intelligibility: mean text_similarity              可懂度
// - pacing:          1 − |1 − duration_ratio| / 0.65   节奏对齐
// - issueFree:       share of segments without issues  问题段占比
// - coverage:        share of segments with dub audio   配音覆盖
```

五个轴，越靠外越好。一眼就能看出 `SPEAKER_02` 的音色轴塌了一块、`SPEAKER_00` 的覆盖轴缺了一角。它不引入任何新测量，只是把已有的逐段信号换成"以人为单位"的视角——给你一个先看哪儿的起点。

## 几条克制

加这一整套仪器，最容易犯的错，是让"诊断"反过来威胁"产物"。所以每一处都带着克制：

**仪器坏了，不许弄坏报告。** 三个富集器全包在 `try/except` 里，失败只往 `*_meta.status` 写一行，报告照常落盘；前端则反过来，只有数据齐了才渲染那一块：

```tsx
// pages/EvaluationDetailPage.tsx —— 数据没齐就不渲染，绝不报错
{report.embedding_meta?.status === 'ok' &&
  report.segments.some(s => Array.isArray(s.speaker_embedding) && s.speaker_embedding.length > 0)
  ? <EmbeddingScatter report={report} ... />
  : null}
```

原则很简单：**诊断功能是加分项，不能变成一个新的失败点。** 给评测加一双眼睛，不该让流水线多一处会崩的地方。

**后置、幂等、可回填。** 每个模块都另带一个 `enrich_report_path` 和一个命令行入口——老报告不用重跑整条流水线，就能把仪器补上；已经富集过的段再跑一遍是 no-op。仪器是后装的，不是返工。

**省着点带宽。** 梅尔频谱量化成 uint8、每段封顶 200 帧（约 12 KB）；音高 200 点封顶；向量只留 6 位小数。整份报告——连同所有仪器的数据——还是能塞进一个 JSON，流式发给浏览器。

**给仪器也写测试。** 一个测量工具，最起码得证明它真在测它声称测的东西。所以音高模块的测试，是喂一段 220 Hz 的正弦波，看 `pyin` 能不能把它认回来：

```python
# tests/test_dub_pitch.py —— 喂一个 220 Hz 纯音，仪器得认得出来
contour = dub_pitch.extract_pitch_contour(waveform, sr)
median_hz = float(np.median([hz for _, hz in contour if hz is not None]))
assert abs(median_hz - 220.0) < 8.0   # pyin 量化有几 Hz 抖动，给够余量
```

**依赖仍然全本地。** `librosa` / `numpy` / `soundfile` 是基座依赖，ECAPA 是早就在用的认人模型——这一整排仪器，一个都不上云。评测能看的东西变多了，但"本地优先"那条地板，一寸没退。

![best-effort：先落盘诚实的账，再尽力把仪器装上去](/blog/dub-evaluation/fig-best-effort.svg)
*报告先写、永远会写；三个富集器在它之后尽力而为，挂了只记一行 status，绝不连累报告。前端反过来，数据齐了才点亮那块仪器。一个 CLI 入口让老报告也能回填——仪器是后装的，不是返工。*

## 几条"为什么这么定"

把这次取舍收拢成几条原则：

- **先诚实，再花哨。** 在加任何可视化之前，先把账算对：漏配不许隐身、存疑不许折叠、覆盖率分母锚在译文全集。一个画得很漂亮、却建立在虚高分数上的仪表盘，是更危险的谎。
- **当一个维度无法被一个数字诚实概括，别去造更聪明的数字——把仪器交给人。** 音色就是这样的维度。与其在阈值上反复横跳，不如给三种视图（标量热条 / 空间散点 / 结构频谱与音高），让它们三角定位，最后那一下交给人的眼睛和耳朵。
- **评测产出的是"可审计的证据"，不是"必须相信的判决"。** 机器负责标记可疑段，但把原始信号摊开让你复核——这跟"本地优先"把"会不会上云"写进代码结构是同一种态度：显式、可见、可审计。
- **诊断不能反过来威胁产物。** best-effort、不阻断、优雅降级——加一双眼睛，不该多出一处会崩的地方。

## 小结

配音是这条流水线的最后一棒，而"配得好不好"恰恰最难用一个数字说清。translip 的评测因此走了两步：先让账诚实——不藏漏配、不折叠存疑、分母锚在译文全集；再把那一个数字摊开成一排看得见的仪器——音色三态热条、ECAPA embedding 散点、音高轮廓、梅尔频谱、说话人雷达。分数还在，但它退回了它本该在的位置：一个**分诊信号**。真正的裁决，连同支撑它的证据，一起交还给人。

下一篇决策记录，我把上一篇结尾欠下的那篇补上：既然每一站都有好几个可插拔后端，**我们凭什么替你选了那个默认值**——以及，什么时候你应该覆盖它。
