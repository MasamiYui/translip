---
title: 把声音拆成两半——人声 / 背景分离
slug: voice-background-separation
date: 2026-06-02
category: 算法
tags: [音频分离, Demucs, CDX23, 信号处理, 流水线]
summary: 配音流水线的第一站，要把一段混合音频干净地拆成"人声"和"背景"两条轨。这篇聊聊 translip 为什么用"先分流、再分离"的设计，两个后端各自的取舍，以及一次 run 背后完整的信号流。
cover: /blog/voice-background-separation/fig-spectrogram.png
author: translip
readingTime: 12
---

# 把声音拆成两半——人声 / 背景分离

> 这是 **幕后 · 博客** 的第一篇。我们不讲怎么用，而是聊聊每个环节背后的设计、取舍和算法。第一站，自然从流水线的第一站说起：**音频分离**（`separation` / CLI 的 `translip run`）。

## 为什么"分离"是第一步

translip 做的事，是把一段视频里的人声换成另一种语言，但**保留原片的一切**——配乐、音效、环境声、笑声、掌声。要做到这点，第一步既不是"听懂"，也不是"翻译"，而是**拆**：把一条混合在一起的音轨，拆成两条——

- **人声（voice）**：交给后面的转写、翻译、配音。它们只关心一件事——把话听清楚。
- **背景（background）**：先放在一边，留到最后混音时**回贴**到译制版上，让成片保留原片的氛围。

所以分离的质量，是整条链路的**天花板**：

- 人声没拆干净，背景音漏进来 → ASR 容易串词、丢字；
- 背景里混着人声残留 → 最后回贴时，原话会"鬼影"般透出来，和新配音打架；
- 人声里裹着配乐 → 替换语言后，一句话里前半是配乐、后半没了，穿帮。

一句话：**后面所有环节，都建立在这两条轨足够干净的前提上。**

## 这到底是个什么问题

把若干个声源混进一条声轨、再想把它们拆开，就是经典的**鸡尾酒会问题（cocktail party problem）**——一屋子人同时说话，你却能专注听清其中一个。机器要做同样的事，得先换一个"看声音"的角度。

声音在**时域**里是一条上下抖动的波形：信息全挤在一起，肉眼几乎读不出结构。

![混合波形与两条目标轨的时域视图](/blog/voice-background-separation/fig-waveform.png)
*同一段音频的时域波形。最上是混合输入；中间的人声按"句子"成块出现、之间留白；最下的背景则连续不断，还能看到规律的打击乐尖峰。时域能看出"节奏"，却看不清"成分"。*

换到**频域**（时频图 / 频谱图），结构一下子清楚了：

![混合频谱与分离目标](/blog/voice-background-separation/fig-spectrogram.png)
*同一段 6 秒音频的时频图。最上是混合输入；中间是人声——一摞清晰的**谐波横纹**（基频 + 泛音），随颤音轻轻起伏、按句停顿；最下是背景——底部的**贝斯横条**加上规律的**打击乐竖条**（宽带瞬态）。分离要做的，就是把最上面这张图"解耦"成下面两张。（图为合成信号，用于展示理想的分离目标）*

频谱给了我们一把直觉的尺子：

- **人声**是一摞随时间平滑移动的谐波线（说话/歌唱的基频及其整数倍）；
- **打击乐**是一根根贯穿各频段的竖线（短促的宽带能量）；
- **贝斯 / 低频**沉在底部。

现代分离模型干的事，本质就是在这张时频图（或直接在波形）上，判断每一份能量"属于谁"，把它分配给对应的轨，再用相位信息重建出可听的波形。难点在于：人声和乐器的能量在频谱上**大面积重叠**，不是简单画条线就能切开的——这正是要交给神经网络的地方。

## translip 的设计：先分流，再分离

一个很自然的念头是"找个最强的模型一把梭"。但实践里，**没有一个模型能同时在所有素材上都最优**：

- 一支 MV、一段强配乐的歌舞片，人声和密集的鼓、贝斯纠缠在一起；
- 一段影视对白，人声主要是混在音效、环境声和零星配乐里。

这两类素材，最合适的模型并不一样。于是 translip 的第一个设计决定是：**先用极轻量的手段判断素材类型（分流），再把它交给最擅长这类素材的后端（分离）。**

![自动分流的决策过程](/blog/voice-background-separation/fig-router.svg)
*auto-router：截取前 90 秒、降采样到 22.05 kHz 单声道，用 librosa 提取 4 个轻量特征，每个越过阈值记 1 分，`score ≥ 2` 判为 music，否则 dialogue。*

分流逻辑刻意做得**便宜**——它只需要一个粗判断，不值得再上一个重模型。实现就是 `pipeline/route.py` 里的一段打分：

```python
# 只读前 90 秒、22.05 kHz 单声道，特征提取几乎免费
signal, sr = librosa.load(wav_path, sr=22_050, mono=True, duration=90.0)

harmonic, _ = librosa.effects.hpss(signal)          # 谐波/打击分量
chroma      = librosa.feature.chroma_stft(y=signal, sr=sr)
onset       = librosa.onset.onset_strength(y=signal, sr=sr)
tempo       = float(librosa.feature.tempo(y=signal, sr=sr, aggregate=np.median)[0])

score = 0
if tempo          >= 72.0: score += 1   # 有稳定节拍
if chroma_peak    >= 0.60: score += 1   # 持续的音高/和声能量
if harmonic_ratio >= 0.50: score += 1   # 谐波占比高（偏乐音）
if onset_std      >= 7.5:  score += 1   # 起音强弱波动大（偏律动）

route = "music" if score >= 2 else "dialogue"
```

四个特征分别从**节奏、和声、谐波占比、律动**四个角度投票——这些恰好是"音乐性"的信号。默认 `mode=auto` 走这套启发式；如果你已经知道素材类型，`--mode music` / `--mode dialogue` 可以直接跳过分流。

> **为什么是启发式而不是分类模型？** 分流的输出只有两种，错了大不了换条路、代价有限；但如果为它引入一个需要加载、占显存的模型，就违背了"便宜"的初衷。90 秒 + 22 kHz + 单声道，让这一步的成本几乎可以忽略——把算力留给真正难的分离。

## 两个后端，各管一摊

分流之后，素材进入两条路之一。

![两个分离后端的对比](/blog/voice-background-separation/fig-backends.svg)
*music 路线交给 Demucs，dialogue 路线交给 CDX23；但两条路的产出会被归一成同一组文件。*

### music 路线：Demucs

音乐素材交给 **Demucs**——`quality=balanced` 用更快的 `htdemucs`，`quality=high` 用微调过的 `htdemucs_ft`（bag-of-4 融合）。它以 `--two-stems vocals` 模式运行，把音频切成**人声**和**其余全部（no_vocals）**两块。

htdemucs 的看家本领是**混合域（hybrid）**：它**同时**在波形域和频谱域里"听"。

![htdemucs 的双域结构示意](/blog/voice-background-separation/fig-htdemucs.svg)
*波形域分支直接处理时间信号，频谱域分支处理时频图；两个分支各有编码器/解码器（带 U-Net 式 skip 连接），中间用一个 Transformer 做**跨域融合**，最后各自还原再相加得到分轨。两种视角互补——频域擅长抓稳定的谐波结构，时域擅长抓瞬态和相位细节。*

工程上，Demucs 是作为**独立子进程**调用的（`python -m demucs ...`）：

```python
command = [sys.executable, "-m", "demucs",
           "-n", self.model, "--two-stems", "vocals",
           "--segment", "7", "--shifts", "1",
           "-o", str(output_root), "-d", device, str(wav_path)]
```

这不是偷懒，而是和整条流水线一致的哲学：**重 ML 任务跑在隔离的子进程里**。好处是跑完即退、显存/内存彻底释放，单个后端崩了也不会污染主进程。

### dialogue 路线：CDX23

对白素材交给 **CDX23**（源自影视向多源分离方案 MVSEP-CDX23）。它把声音拆成**三**条——`dialog` / `music` / `effect`，再把后两者相加得到背景：

```python
music  = averaged[0].T
effect = averaged[1].T
dialog = averaged[2].T
background = music + effect      # 背景 = 配乐 + 音效
```

`quality=balanced` 用单个检查点，`quality=high` 用 3 个检查点做**集成**（推理后平均，更稳但更慢）。它在**进程内**用 PyTorch 跑，复用 Demucs 的推理机制，有两个关键旋钮：

- **`overlap`（默认 0.5）**：推理窗口的重叠率，做重叠相加。上游榜单用 0.8 追极限分数；0.5 在 CPU / Apple Silicon 上是**近乎无损的提速**，所以选它当默认。
- **`shifts`（默认 1）**：测试时增强（TTA），对输入做多次微小平移再平均，换一点点质量。

模型权重（demucs 格式的 `.th`）首次使用时从上游 GitHub release 自动下载并缓存到 `TRANSLIP_CACHE_DIR/models/cdx23/`，也可以提前 `translip download-models --backend cdx23` 拉好。

## 一次 `run` 背后的完整信号流

把上面串起来，一次 `translip run` 从输入到产物是这样流动的：

![端到端信号流](/blog/voice-background-separation/fig-signal-flow.svg)
*从一份视频/音频，到下游可直接消费的 voice / background 两条轨。*

1. **抽轨**：`ffprobe` 探测元信息，`ffmpeg` 把音频解出来，统一成 `input.wav`（44.1 kHz、立体声）。
2. **分流**：取前 90 秒、降到 22 kHz 单声道，跑上面那套打分，决定 music 还是 dialogue。
3. **分离**：交给 Demucs（子进程）或 CDX23（进程内）。两条路都做了 **device 自动降级**——优先 CUDA / MPS，遇到不支持的算子或推理失败就**回退 CPU** 重试，保证"慢但能出"。
4. **归一**：用 `render_wav` 把后端的原始输出整理成 `final/voice.wav` + `final/background.wav`。
5. **编码导出**：`export` 成你要的格式——`wav` / `mp3` / `flac` / `aac` / `opus`。
6. **写清单**：生成 `manifest.json`，记录路由决策、四个特征的分数、用了哪个后端、计时和产物路径。

最终落到磁盘上的，是一份稳定的**产物契约**：

```text
output-separation/example/
├── voice.wav           # 人声轨 → 喂给下游转写
├── background.wav      # 背景轨 → 留到最后混音回贴
└── manifest.json       # 路由 / 分数 / 后端 / 计时 / 产物
```

下游环节（Task A 转写、Task E 混音…）**只认这三样**，完全不关心上游到底走了哪条路、用了哪个模型。加 `--keep-intermediate` 还会额外保留 `stems/`（如 CDX23 的 `dialog` / `music` / `effect` 中间分轨），方便排查。

一个最小调用：

```bash
uv run translip run \
  --input ./test_video/example.mp4 \
  --mode auto --quality balanced \
  --output-dir ./output-separation
```

## 几个"为什么这么做"

把这一站的设计取舍收拢一下：

- **默认 `auto` + 轻量分流**：用一个几乎免费的启发式，避免"一个模型通吃所有素材"的妥协；知道类型时又能用 `--mode` 一键跳过。
- **Demucs 子进程 / CDX23 进程内**：Demucs 本就是外部 CLI，天然子进程、跑完即释放；CDX23 用 Demucs 的推理框架在进程内跑，靠 `overlap` / `shifts` 在质量和速度间取舍。两者都有 **CPU 降级**兜底。
- **`overlap` 默认 0.5**：把"榜单极限"换成"日常够用且快得多"，对本地、无独显的机器尤其友好。
- **`balanced` / `high` 两档**：单模型 vs 微调 / 集成——让用户在"快"和"准"之间自己选。
- **`--enhance-voice` 目前是占位**：分离后预留了一个人声增强位（当前是直通实现），为后续接入降噪 / 去混响留好接口。

## 小结

分离把"一锅声音"变成两条干净的轨：人声送去理解，背景留待回贴。它不显眼，却是整条配音流水线的地基——**这一步的上限，就是成片的上限。**

下一篇，我们顺着 `voice.wav` 往下走，聊聊 **Task A：怎么把一条人声轨，变成带"谁在说"标注的文字**（ASR + 说话人分离）。
