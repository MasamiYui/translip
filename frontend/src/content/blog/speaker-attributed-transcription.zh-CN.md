---
title: 听懂，还要分清是谁说的——ASR + 说话人分离
slug: speaker-attributed-transcription
date: 2026-06-09
category: 算法
tags: [语音识别, 说话人分离, FunASR, ECAPA, OCR纠错, 流水线]
summary: 流水线的第二站，要把上一篇分出来的那条 voice.wav，变成"几点几分、谁、说了什么"的逐句文本。这篇聊聊 translip 怎么回答"说了什么"（ASR）和"谁说的"（说话人分离）这两个本来各走各路的问题，以及当屏幕上还印着硬字幕时，怎么用 OCR 反过来校准转写。
cover: /blog/speaker-attributed-transcription/fig-diarization-timeline.png
author: translip
readingTime: 15
---

# 听懂，还要分清是谁说的——ASR + 说话人分离

> 这是 **幕后 · 博客** 的第二篇。[上一篇](/blog/voice-background-separation) 我们把一锅声音拆成了人声和背景两条轨；这一篇顺着那条 `voice.wav` 往下走，到流水线的第二站：**说话人归因转写**（`task-a` / CLI 的 `translip transcribe`）。

## 这一站要交出什么

上一站的产物是一条干净的人声轨 `voice.wav`。它能听，但机器还读不懂——它不知道哪几秒是一句话、那句话是什么字、又是谁说的。Task A 的任务，就是把这条连续的人声，变成一串**结构化的句子**，每一句都带三样东西：

- **时间**：这句话从第几秒到第几秒（`start` / `end`）；
- **文字**：这句话说了什么（`text`）；
- **说话人**：这句话是谁说的（`speaker_label`）。

最终落到磁盘上的，是一份叫 `segments.zh.json` 的契约，核心就是一个 `segments` 数组，每个元素长这样：

```json
{
  "id": "seg-0007",
  "start": 12.84,
  "end": 15.21,
  "duration": 2.37,
  "speaker_label": "SPEAKER_01",
  "text": "我不是早就跟你说过了吗",
  "language": "zh"
}
```

后面的所有环节都吃这份文件：翻译（Task C）按句翻、配音（Task D）按 `speaker_label` 分配音色、混音（Task E）按 `start`/`end` 把新配音卡回原来的时间槽。所以这一站要把两个**本来不相干**的问题同时答对：

- **说了什么**——这是 **ASR**（自动语音识别）干的事；
- **谁说的**——这是 **说话人分离**（diarization）干的事。

这两件事，用的是两个不同的模型、两套不同的"看声音"的方式。难点不在于各自答对，而在于**把两个答案对齐到同一句话上**。

![一段人声被切成逐句、并按说话人上色的时间轴](/blog/speaker-attributed-transcription/fig-diarization-timeline.png)
*Task A 的产出：连续的人声被切成一句句带时间戳的文本，再按"谁在说"染成不同颜色。横轴是时间，每个色块是一句话，颜色代表说话人。（示意图）*

## 先做一件不起眼的事：把音频改造成"模型爱吃的样子"

上一站为了分离，把音频解成了 **44.1 kHz、立体声**——因为分离要尽量保真。但转写和声纹完全不需要这么高的规格，反而吃 16 kHz 单声道：语音模型几乎都在这个采样率上训练，立体声的两个声道对"听清内容"也没有帮助。

所以 Task A 一进来先用 ffmpeg 把输入重采样成 **16 kHz 单声道**：

```python
# pipeline/ingest.py —— 转写/声纹统一的预处理
working_audio = temp_dir / "transcription_input.wav"
extract_audio(
    input_path=input_path,
    output_path=working_audio,
    audio_stream_index=audio_stream_index,
    sample_rate=TRANSCRIPTION_SAMPLE_RATE,   # 16000
    channels=1,                              # 单声道
)
```

一个细节：Task A 既能吃上一站的 `voice.wav`，也能直接吃原始视频——它内部一律先抽音轨、统一规格，所以"先分离再转写"和"拿原片直接转写"走的是同一段预处理代码。

## 第一问：说了什么（ASR）

translip 的 ASR 有两个后端，由 `--asr-backend` 选择，**默认是 FunASR**：

![两个 ASR 后端的分段哲学](/blog/speaker-attributed-transcription/fig-asr-backends.svg)
*默认 FunASR 走中文优先的 Paraformer / SenseVoice；faster-whisper 是多语种备选。两条路最后都归一成同一种 `AsrSegment`。*

### 默认路线：FunASR

中文视频是 translip 的主场，所以默认后端选了 **FunASR**，默认模型 `paraformer-zh`。FunASR 这条路内部其实还分两支，由模型名决定：

**Paraformer（默认）**——它带 VAD（FSMN-VAD 切语音段）和标点恢复（CT-Punc 加标点），而且**预测 token 级时间戳**。这意味着它能直接吐出"一句一段、每句都有真实起止时间"的结果：

```python
# funasr_backend.py —— Paraformer 一句一段，时间是真的
results = model.generate(input=str(audio_path),
                         batch_size_s=300, use_itn=True,
                         sentence_timestamp=True)        # 关键
sentences = results[0].get("sentence_info") or []
for raw in sentences:
    start = float(raw.get("start", 0.0)) / 1000.0       # 毫秒 → 秒
    end   = float(raw.get("end", start)) / 1000.0
    segments.append(AsrSegment(..., start=start, end=end, text=_clean_sentence(...)))
```

**SenseVoice**——更轻快、还能识别情绪/事件标签，但**不吐 token 时间戳**。它一个 VAD 语音段返回一整段（可能跨好几句）转写，于是 translip 先按句末标点把它切成字幕大小的短句，再**按字数比例**把这段时间分摊给各句：

```python
# funasr_backend.py —— SenseVoice 没有 token 时间戳，只能按字数比例近似
def _distribute_region_time(start, end, sentences):
    total_chars = sum(len(s) for s in sentences) or 1
    span, cursor, spans = end - start, start, []
    for offset, sentence in enumerate(sentences):
        is_last = offset == len(sentences) - 1
        seg_end = end if is_last else cursor + span * len(sentence) / total_chars
        spans.append((cursor, max(seg_end, cursor), sentence))
        cursor = seg_end
    return spans
```

这是一个诚实的近似——注释里也写得很直白："per-sentence times are an approximation"。正因为 Paraformer 的时间戳是**真**的、SenseVoice 的是**估**的，默认才选了前者：下游混音要靠这些时间把配音卡回去，时间越准，成片越不容易穿帮。

还有个容易踩的坑 translip 提前处理了：SenseVoice 会吐 `<|zh|><|NEUTRAL|><|Speech|>` 这类富文本标签。如果先送进标点模型再清洗，标签会被揉成 `< | zh | >` 这种再也擦不掉的形态。所以代码**先剥标签、后加标点**，让情绪/语种标记永远不漏进字幕。

### 备选路线：faster-whisper

如果素材是多语种、或你更信任 Whisper，`--asr-backend faster-whisper` 切到 **faster-whisper**（CTranslate2 实现的 Whisper）。它的两个工程取舍值得一提：

- **量化**：CPU 上用 `int8`、CUDA 上用 `float16`（`_compute_type`），在本地无独显的机器上也能跑得动；
- **VAD 门控**：默认开 `vad_filter`，用静音时长和单段上限把长停顿切开，避免把好几句黏成一段——

```python
# asr.py —— VAD 参数：用静音切句、给单段封顶
if resolved_options.vad_filter:
    transcribe_kwargs["vad_parameters"] = {
        "min_silence_duration_ms": resolved_options.vad_min_silence_duration_ms,  # 400
        "max_speech_duration_s": resolved_options.vad_max_segment_sec,            # 30
    }
```

两条路无论走哪边，产出都被归一成同一个 `AsrSegment(segment_id, start, end, text, language)`——后面的说话人分离根本不关心这段文字是谁转的。

> **一个统一的小动作：device 自动降级。** ASR 和声纹各自解析设备：`auto` 优先 CUDA，再 MPS，再 CPU。但 faster-whisper 和 ECAPA 在 Apple Silicon 上会主动回退 CPU（faster-whisper 不直接支持 MPS、speechbrain 的算子也未必齐），而 FunASR / pyannote 可以走 MPS。原则和上一篇一致——**慢但能出**，永远比"在某台机器上直接崩"好。

## 第二问：谁说的（说话人分离）

现在每句话有了文字和时间，还差一个 `speaker_label`。这就是 Task A 真正绕不开的难点。

理论上，"谁在说"和"说了什么"是**两条独立的时间线**：ASR 给的是"几点到几点、说了什么"，而一个标准的说话人分离模型给的是"几点到几点、是谁"——两套边界根本不重合。怎么把这两条线对齐到同一句话上，translip 提供了两种哲学，由 `--diarizer-backend` 选择：

![两种说话人分离哲学：锚定 ASR vs 独立时间线再对齐](/blog/speaker-attributed-transcription/fig-diarization-two-ways.svg)
*默认 ECAPA 把"谁"直接锚定在 ASR 的句子上（聚类）；pyannote 各跑各的时间线，再按时间重叠把标签贴回每句。*

### 默认路线：ECAPA 嵌入 + 聚类（锚定在 ASR 上）

默认后端 `ecapa` 干脆**不另起一条时间线**——它把 ASR 切好的句子当成"什么时候"的基准，只回答"每一句是谁"。流程是：

**1. 把相邻的短句攒成组。** 单独一句太短，声纹不稳；于是把间隔小、总时长不超 8 秒、不超过 5 句的相邻句子攒成一个"嵌入组"，整组提一个声纹。

**2. 给每组提一个 ECAPA 声纹。** 用 speechbrain 的 `spkrec-ecapa-voxceleb`，把那段音频（窗口不足 2 秒会向两侧补足）编码成一个归一化向量。声纹的妙处是：同一个人不同的话，向量方向接近；不同的人，方向分得开。

**3. 用余弦相似度聚类。** 先判断"是不是其实只有一个人"，否则做层次聚类：

```python
# speaker.py —— 相似度阈值与聚类
DEFAULT_SAME_SPEAKER_SIMILARITY = 0.62   # 同一人的余弦相似度门槛
DEFAULT_SINGLE_SPEAKER_FLOOR    = 0.52   # 低于它才敢说"不止一个人"

def _is_single_speaker(embeddings):
    sims = _pairwise_similarities(embeddings)        # 两两余弦
    return float(np.percentile(sims, 20)) >= DEFAULT_SINGLE_SPEAKER_FLOOR

clusterer = AgglomerativeClustering(
    n_clusters=None, metric="cosine", linkage="average",
    distance_threshold=1.0 - DEFAULT_SAME_SPEAKER_SIMILARITY,  # = 0.38
)
```

判"是不是单人"用的是**第 20 百分位**的相似度，而不是平均值——只要绝大多数句子彼此都像，就当一个人，避免被个别噪声片段骗出一个假的"第二人"。

**4. 时序平滑。** 聚类只看声纹、不看顺序，偶尔会把一句话误判成孤立的"插入"。所以最后扫一遍：如果某句的前后两句是同一个人、而它自己很短（≤1.5 秒）又被判成了别人，就把它并回去——

```python
# speaker.py —— 抹掉"A A B A A"里那个孤立的 B
if prev_id == next_id and curr_id != prev_id and segments[index].duration <= 1.5:
    smoothed[index] = prev_id
```

聚类看到的"原始材料"，其实就是一张句子两两之间的相似度矩阵。说话人分得越开，这张矩阵的**块对角**结构越明显：

![说话人嵌入的余弦相似度矩阵](/blog/speaker-attributed-transcription/fig-similarity-matrix.png)
*把每句话的声纹两两算余弦相似度，得到这张矩阵。三个说话人对应三个高相似度的方块（块对角），块与块之间偏冷——聚类做的，就是把这些方块认出来。（示意数据）*

这条路的好处很实在：**便宜**（在 Task A 进程内就算完，不用额外起一个分离模型）、**对齐**（标签天生贴在 ASR 句子上，不存在两条线对不齐的问题）。代价是它的分辨率被 ASR 的分句锁死——如果一句话里真有两个人抢话，它没法把这一句再劈开。

### 备选路线：pyannote（独立时间线 + 按重叠对齐）

如果要更专业的说话人分离，`--diarizer-backend pyannote` 切到 `pyannote/speaker-diarization-3.1`。它是一个**真正独立**的分离流水线，自己吐出一串"说话人轮次"（谁、从几点到几点），完全不管 ASR 是怎么分句的。

于是就回到了那个"两条时间线"的原始问题，translip 的对齐策略很直接：**每一句 ASR，认领与它时间重叠最多的那个说话人轮次。**

```python
# pyannote_diarizer.py —— 每句话挑"重叠最多"的说话人轮次
for turn_start, turn_end, label in diarization_turns:
    overlap = max(0.0, min(seg_end, turn_end) - max(seg_start, turn_start))
    if overlap > best_overlap:
        best_overlap, best_label = overlap, label
# 万一一点都不重叠，退而求其次找时间上最近的轮次
```

pyannote 通常更准，尤其在说话人多、抢话频繁的素材上。代价是它更重，而且要接受模型许可、配一个 HuggingFace token（`PYANNOTE_AUTH_TOKEN` / `HF_TOKEN`），首次还要联网拉权重——所以它是"按需开启"的选项，而不是默认。

> **一个容易踩的默认值差异。** 在**完整流水线**（`run-pipeline`）里，说话人分离**默认开启**（`enable_diarization=True`，用 ecapa）；但单独跑 `translip transcribe` 时，它**默认关闭**——你得显式加 `--enable-diarization` 才会分人，否则所有句子都挂在 `SPEAKER_00` 名下。这是 CLI 为"我只想快速看一眼文字"留的快捷默认，知道这点能省掉一次"怎么没分人"的困惑。

### 把两个答案缝起来

ASR 给了一串句子，分离给了一串等长的标签，最后用一个 `zip(..., strict=True)` 把它们一一对上——`strict=True` 是一道刻意的保险：万一两边长度不一致，宁可当场报错，也不让文字和说话人错位地配在一起。

```python
# runner.py —— 文字 × 说话人，严格对齐成最终段
segments = [
    TranscriptionSegment(start=seg.start, end=seg.end, text=seg.text,
                         speaker_label=label, language=seg.language, ...)
    for seg, label in zip(asr_segments, speaker_labels, strict=True)
]
```

到这里，`segments.zh.json` 就齐了。对很多素材，这已经够用。但还有一类素材，能再榨出一截质量——屏幕上本来就印着字。

## 第三问（彩蛋）：屏幕上印着字，为什么不用？

中文是同音字的重灾区。ASR 把音听成字，"是 / 事 / 试"、"在 / 再"、"做 / 作"——只要发音一样，再好的声学模型也可能挑错那个字。可很多视频**屏幕上就压着一行硬字幕**，那行字往往就是台词的"标准答案"。

上一类节点（OCR 硬字幕检测，`ocr-detect`）已经把屏幕上的字连同时间、置信度抠了出来。于是 translip 多了一步可选的**OCR 反哺**（`asr-ocr-correct` 节点 / CLI 的 `correct-asr-with-ocr`）：用 OCR 的**文字**去修 ASR 的**文字**，但**保留 ASR 的时间**——因为时间是声音定的，比画面上字幕的出现/消失更贴合"话什么时候说出口"。

但 OCR 自己也不干净：它会把形近字认错（"未 / 末"、"己 / 已"），还可能把多行字幕的时间糊在一起。所以这又是一次"两个都不可靠的源，怎么取真"的问题。translip 的答案是一道**确定性的闸门**，先不急着信任谁：

![OCR 反哺 ASR：确定性闸门 + 四个去向](/blog/speaker-attributed-transcription/fig-ocr-correction.svg)
*每句 ASR 配上时间重叠的高置信 OCR，过三道闸（置信度 / 时间对齐 / 长度比），按结果落进四个桶之一。只有最含糊的 review 桶，才可选地交给 LLM 仲裁。*

```python
# ocr_correction.py —— 三道闸：都过才敢用 OCR 改写
should_replace = bool(
    high_confidence_candidates                          # OCR 置信度够高
    and alignment_score >= config.min_alignment_score   # 时间对得上
    and length_ok                                       # 字数比例在合理区间
)
```

按这道闸的结果，每句话落进四个桶之一：

- **用 OCR 改写**（三道闸全过）：OCR 大概率是对的，直接替换文字，时间不动；
- **保留 ASR**（有 OCR 但置信度不够）：不冒险，留着 ASR；
- **进 review**（OCR 置信度够、但对齐或长度可疑）：最含糊的一类，单独标记；
- **ocr_only**（有高置信 OCR、却没有任何 ASR 句子覆盖）：可能是一句被漏听的台词，只上报、不擅自插入。

三个预设 `conservative / standard / aggressive` 就是在拧这几个阈值的松紧：保守版要求 OCR 置信度 ≥0.92、对齐 ≥0.70 才肯改；激进版把门槛放到 0.75 / 0.40，改得更多但更敢冒险。

只有最含糊的 **review** 桶，才会（在你显式开启时）交给一个 LLM 仲裁——而且给它戴了**紧箍咒**：

```text
# arbitration.py 的系统提示（节选）
… use ONLY characters that already appear in the ASR or OCR text;
  never introduce new words or content;
  if genuinely unsure, prefer the OCR text. …
```

并且模型给的合并结果还要再过一道**忠实性校验**：每一个字都必须在 ASR 或 OCR 原文里出现过，否则一律作废、退回确定性结果——

```python
# ocr_correction.py —— 合并文本里不许出现凭空冒出来的字
def _is_faithful(candidate, *sources):
    allowed = set().union(*(set(_clean_text(s)) for s in sources))
    return set(_clean_text(candidate)) <= allowed
```

这套设计的克制是有意的：**能用确定性规则解决的，绝不喊模型；非要喊模型的，也只让它在 ASR 和 OCR 已有的字里做选择题**，杜绝"AI 自由发挥"把台词改出花来。OCR 反哺只在带 `+ocr-subs` 的模板里出现，产物是 `segments.zh.corrected.json`，下游会优先认这份修正版。

## 一次 `transcribe` 背后的完整流程

把三问串起来，一次 Task A 是这样流动的：

![Task A 端到端流程](/blog/speaker-attributed-transcription/fig-task-a-flow.svg)
*从一条人声轨，到下游可直接消费的、带说话人标注的逐句文本。*

1. **预处理**：ffmpeg 把输入抽成 16 kHz 单声道 `transcription_input.wav`。
2. **ASR**：FunASR（默认）或 faster-whisper，吐出一串 `AsrSegment`（时间 + 文字）。
3. **说话人分离**：ECAPA 聚类（默认）或 pyannote，给每段配一个 `speaker_label`；关掉时全归 `SPEAKER_00`。
4. **缝合**：`zip(strict=True)` 把文字和说话人严格对齐成 `TranscriptionSegment`。
5. **写产物**：`segments.zh.json` + 可选 `segments.zh.srt` + `task-a-manifest.json`（记后端、设备、检测语种、段数、说话人数、计时）。
6. **（可选）OCR 反哺**：若上游有 `ocr-detect`，再产出 `segments.zh.corrected.json`。

落到磁盘上的产物契约：

```text
output-transcribe/example/
├── segments.zh.json        # 逐句：时间 + 文字 + 说话人  → 喂给下游翻译/配音
├── segments.zh.srt         # 带 [SPEAKER_xx] 前缀的字幕，方便人工核对
└── task-a-manifest.json    # 后端 / 设备 / 语种 / 段数 / 说话人数 / 计时
```

一个最小调用（吃上一站分出来的人声轨）：

```bash
uv run translip transcribe \
  --input ./output-stage1/example/voice.wav \
  --asr-backend funasr --asr-model paraformer-zh \
  --enable-diarization --diarizer-backend ecapa \
  --output-dir ./output-transcribe
```

## 几个"为什么这么做"

把这一站的取舍收拢一下：

- **默认 FunASR / `paraformer-zh`**：中文优先，且 Paraformer 有**真**的句级时间戳；faster-whisper 作为多语种备选。把"时间准"放在第一位，因为下游混音要靠它。
- **默认说话人分离锚定在 ASR 上（ECAPA）**：便宜、在进程内算完、标签天生对齐句子；pyannote 是更准但更重、要 token 要联网的"按需"选项。
- **单人判定取第 20 百分位 + 时序平滑**：用统计的保守，避免被个别噪声片段骗出假说话人，再把孤立的误判抹平。
- **device 自动降级**：faster-whisper / ECAPA 在 MPS 上回退 CPU，FunASR / pyannote 可走 MPS——慢但能出，胜过崩。
- **OCR 反哺：确定性优先、LLM 兜底、忠实性封顶**：能用规则就不喊模型；喊模型也只让它在已有的字里做选择题，且每个字都要能在原文找到来源。

## 小结

Task A 把一条只能听的人声，变成了能读、能查、能往下游传的结构：**几点几分、谁、说了什么**。它要同时答对两个本来各走各路的问题，必要时还借屏幕上的字再校一遍。这一步的字准不准、人分得对不对，直接决定了后面翻译会不会跑偏、配音会不会串音。

不过你大概也注意到了：这里的 `SPEAKER_00` / `SPEAKER_01` 只是**本片段内的临时工号**——它不知道"01 号"在上一集、或者下一个片段里又是谁。下一篇，我们聊 **Task B：怎么把这些临时工号，变成跨片段、跨整部作品都稳定的"谁"**（说话人注册表与声纹画像）。
