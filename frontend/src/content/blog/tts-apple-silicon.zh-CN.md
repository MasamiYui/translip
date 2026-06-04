---
title: 排行榜会在 Mac 上骗你——配音后端的一次诚实选型
slug: tts-apple-silicon
date: 2026-07-21
category: 决策
tags: [配音, TTS, 音色克隆, Apple Silicon, MLX, 选型, 决策记录, F5-TTS, VoxCPM]
summary: 这是博客的第三篇决策记录,补上前两篇一直预告、却没写的那一题——既然配音那一站有好几个可插拔后端,我们凭什么替你选了那台最不起眼的小模型当默认?答案藏在一个反直觉的事实里:音色榜单前排的开源模型,几乎全是为 CUDA 调的,搬到 Apple Silicon 上不是慢一点,是直接趴窝;于是在 Mac 上,真正该信的不是排行榜,而是你自己机器上的那个实时率。我们把一圈调研、对抗核验和那些不体面的 caveat,一起摊开。
cover: /blog/tts-apple-silicon/fig-tts-apple-silicon-cover.svg
author: translip
readingTime: 15
---

# 排行榜会在 Mac 上骗你——配音后端的一次诚实选型

> 这是 **幕后 · 博客** 的第九篇,也是第三篇**决策记录**。[配音那一站](/blog/voice-cloning) 讲了怎么"借一段声音说没说过的话",结尾留了个尾巴:默认那台 MOSS-TTS-Nano,**音色是有上限的,要更像就显式切 VoxCPM2**;而它"像不像"靠的那把 [ECAPA 声纹尺子](/blog/voiceprint-internals),刚在上一篇深潜里拆过。而 [本地优先](/blog/local-first) 和 [配音评测](/blog/dub-evaluation) 两篇决策的结尾,都欠着同一道题——**既然每一站都有好几个可插拔后端,我们凭什么替你选了那个默认值。** 这一篇,把这道题在配音后端上认认真真答一次。答案的形状,和我原本以为的不太一样。

## 一个诱人、但会在 Mac 上骗你的榜单

选 TTS 后端,最自然的起手式是去看排行榜:谁的音色相似度高、谁在盲听里赢得多,选它就是了。按这个逻辑,答案似乎很清楚——

- 客观基准 [Seed-TTS-eval](https://github.com/BytedanceSpeech/seed-tts-eval)(字节那套,量 WER 可懂度 + SIM 音色相似度)上,**IndexTTS-2** 几乎逐格碾压:test-en SIM 0.860 / WER 1.521、test-zh SIM 0.865 / CER 1.008,同时赢 F5-TTS、CosyVoice2、MaskGCT、SparkTTS([arXiv 2506.21619](https://arxiv.org/abs/2506.21619));
- 你现在的"音色担当" **VoxCPM** 客观分更猛:EN WER 1.85 / SIM 72.9、ZH CER 0.93 / SIM 77.2,逐格赢 F5 和 CosyVoice2([arXiv 2509.24650](https://arxiv.org/html/2509.24650v1));
- 跨语种(中文音色念英文)这一项,**CosyVoice 3** 自带 `cross_lingual` 模式、覆盖 9 语种,号称"zh2en/en2zh 领先"([CosyVoice3 paper](https://funaudiollm.github.io/cosyvoice3/pdf/CosyVoice3_0.pdf))。

照榜单,你该把默认从那台 100M 的小不点换成 IndexTTS-2 或 VoxCPM。然后你把它们装上你的 MacBook,点下合成,等来的是——什么都没有。

> **榜单测的是"在 H100 上谁更像",你的问题是"在我这台 M4 上谁能跑完一句话"。这是两道完全不同的题,而前者会在后者上骗你。**

## 把"音色好"的模型搬上 M4,会发生什么

有人替我们做了这个残酷的实验。一个独立基准 [tts-bench](https://github.com/5uck1ess/tts-bench)(真实 Apple M4 / 16 GB、42 个模型、逐模型跑分,2026-06 还在更新)把榜单前排一个个搬上 Mac,CPU+MPS 实测的实时率(RTF,≥1 才算实时)是这样的:

| 榜单前排(音色好) | M4 实测 RTF | 体感 |
| --- | --- | --- |
| IndexTTS-2 | **~0.1×** | 慢十倍 |
| Qwen3-TTS Base(你在用) | ~0.2× | 慢五倍 |
| F5-TTS(原生 MPS) | ≤0.1× | 慢十倍 |
| Fish Speech 1.5 | ~0.31× | 慢三倍 |
| **VoxCPM(你在用)** | **超时 >600 秒/句** | **直接挂掉** |

不是慢一点,是**整整慢一个数量级,或者干脆超时**。而且原因不是你的机器弱,是这些模型**根上就是为 NVIDIA 调的**:

- 它们的提速全靠 `torch.compile` / CUDA Graphs,这些在 MPS 上**直接失效**(index-tts 的 issue #585 就卡在这);
- 像 VoxCPM 的 ZipEnhancer 降噪器,**强制留在 CPU** 上跑,成了独木桥(这条在 VoxCPM 自己的文档 FAQ 里写着)。

换句话说,**"音色好"和"在 Mac 上能跑"这两件事,在当前这批模型上几乎是负相关的**——越是堆料堆出好音色的,越依赖那套搬不到 Apple Silicon 的 CUDA 加速。

![榜单前排搬上 M4,集体趴窝](/blog/tts-apple-silicon/fig-mps-stall.svg)
*这些模型为 CUDA 调优:torch.compile / CUDA Graphs 在 MPS 上失效、降噪器卡在 CPU 上。于是在 M4 上,IndexTTS-2 只有 0.1×、VoxCPM 直接超时。榜单的"快",留在了数据中心里。*

## 真正能在 Mac 上跑的,是另一拨模型

把同一份 tts-bench 倒过来看——筛出在 M4 上**暖跑 ≥ 0.8× 实时**、又能做参考音色克隆的,是另一份名单:

| 跑得动的克隆模型 | 参数 | M4 实测 RTF | 许可证 | 备注 |
| --- | --- | --- | --- | --- |
| OpenVoice v2 | ~100M | MPS **5.91×** | MIT | 音色转换器路线 |
| Coqui XTTS-v2 | ~467M | MPS 2.0× | ⚠️ **CPML 非商用** | 快,但许可证是坑 |
| **MOSS-TTS-Nano(你的默认)** | ~100M | **CPU 1.93× · 48 kHz** | — | 小到 MPS 反而更慢(0.40×) |
| ChatterBox Turbo | ~744M | MPS 1.1× | MIT | 勉强实时 |

注意这份名单和上一份**几乎没有交集**:榜单前排一个都不在,跑得动的这拨,音色档次普遍中庸。这就是 Mac 上选 TTS 的真实地形——**你不是在"最像"和"次像"之间选,你是在"跑得动的里头,哪个最像"之间选。**

把两张表叠到一张图上,地形一目了然:好音色全挤在"太慢"的左边,能跑的全在中庸那一档。

![速度 × 质量:Mac 上的真实地形](/blog/tts-apple-silicon/fig-speed-quality-map.svg)
*横轴 M4 实时率、纵轴音色质量。右边阴影是"实时可用区"(≥0.8×)。音色榜单前排(IndexTTS-2 / VoxCPM / Qwen3)全堆在左侧太慢区;能跑进可用区的(MOSS / Coqui / ChatterBox)音色中庸。唯一的例外在下一节。*

## 那台最不起眼的默认值,其实选对了

回到那道题:**我们凭什么默认选了 MOSS-TTS-Nano?** 调研给了一个有点反讽的答案——**正因为它"不够好",它才跑得动。**

- 它在你三个后端里,是**唯一一个在 Mac 上实时**的(CPU 1.93×);Qwen3-TTS 只有 0.2×,VoxCPM 直接超时;
- 它原生 **48 kHz** 输出,恰好配上你 [刚改成 48 kHz 的混音交付](/blog/voice-cloning)——少一层上采样损耗;
- 它 100M 小到可以开**多 worker 并行**,把一池子进程喂满。

这正是 [本地优先](/blog/local-first) 那条原则在配音后端上的复读:**默认值不是为"理论最优"定的,是为"绝大多数人、在自己的机器上、现在就能跑通"定的。** 一台跑不动的 SOTA,对一个本地优先的流水线来说,等于不存在。

> 顺带破一个容易上当的混淆:那份盲听人评里排得不错的 "MOSS-TTS",是一个 **80 亿参数的 Qwen3 大模型**,和你默认的 **MOSS-TTS-Nano-100M 完全是两个东西**。名字像,血缘远,别拿它的分给你的小模型贴金。

## 唯一一条"更好、又跑得动"的升级路:F5-TTS 的 MLX 移植

那张速度×质量图里,我留了个"例外"。它叫 **F5-TTS**。

榜单里 F5-TTS 原生 MPS 也只有 ≤0.1×,本该和别人一起趴在左边。但它有一样别人没有的东西:**一个原生的 MLX 移植** [`f5-tts-mlx`](https://github.com/lucasnewman/f5-tts-mlx)——专门为 Apple Silicon 重写,于是它能从左边"太慢区"一脚迈进右边"可用区"。这是目前**唯一一个"音色比 MOSS 高一档、又真有 Apple Silicon 路径"的开源模型**:

- **MIT 许可,可商用**;非自回归的 flow-matching DiT;
- 零样本克隆走 `--ref-audio` + `--ref-text`(mono 24 kHz、~5–10 秒)——**和你 `reference_audio + ref_text → synthesize` 的接口严丝合缝**,跟 Qwen 的 `icl`、VoxCPM 的 ultimate 同形;
- 支持 **4-bit / 8-bit 量化**(`--q 4`)省内存提速;启用 RK4 采样后约 **1.6× 实时**(M3 Max 单条短样本约 4 秒)。

接进来几乎零成本——你那套 `TTSBackend` 协议,加一个后端就是**一个文件 + 一行注册**:

```python
# 新增 dubbing/f5_mlx_tts_backend.py,registry.py 加一行即可
@TTS_BACKENDS.register("f5-mlx", requires_reference_audio=True,
                       metadata={"apple_silicon_native": True})
def _build_f5_mlx(*, device="auto", worker_count_hint=None):
    from .f5_mlx_tts_backend import F5MlxTtsBackend
    return F5MlxTtsBackend(...)   # 调 f5_tts_mlx.generate,--q 4 量化
```

接进来之后,现成的[三轴自检(ECAPA / backread / 时长)+ 参考赛](/blog/voice-cloning)**一行都不用改**就能复用——直接拿你已有的评测体系,给 F5-mlx vs MOSS 打分。

**但请把这条当"待验证的候选",不是"已确认的答案"。** 那个"1.6× 实时 / 4 秒"是 **M3 Max 上的单条短样本**;而 F5 的原生 MPS 版在 M4 上只有 ≤0.1×。**MLX 移植在你这台 M4 上、用整句、跑出来的持续 RTF,以及中文音色念英文的实际效果,谁都还没测过。** 这是它上线前的头等待办——也正好是下一节的态度。

## 跨语种那顶皇冠,本地暂时拿不到

你最硬的需求是**跨语种克隆**:用中文说话人的音色去念英文。这一项谁最强?调研很明确——**IndexTTS 2.5 和 CosyVoice 3**:前者支持 zh/en/ja/es 零样本跨语种、未见语种也保音色一致([arXiv 2601.03888](https://arxiv.org/pdf/2601.03888));后者自带 `cross_lingual` 模式、号称 zh2en/en2zh 领先。

但坏消息也一样明确:**它们俩,都没有 Apple Silicon 路径。** IndexTTS 2.5 那个亮眼的 2.28× 提速,是在数据中心 A10 GPU 上测的,论文里 Apple / MLX / MPS / CoreML **零提及**;实测 IndexTTS-2 在 M4 上只有 0.1×。CosyVoice 3 同理,它的兄弟 Qwen3-TTS 在 M4 上就 0.2×。

于是跨语种音色这顶皇冠,**本地 Mac 暂时拿不到**。诚实地讲,只有两条路:

1. **一台带 CUDA 的远程机器**跑 IndexTTS 2.5 / CosyVoice 3;
2. **加一个 opt-in 的 API 后端**——这恰好是 [本地优先](/blog/local-first) 那篇立的规矩:**云是一个你主动打开的开关,不是一个默认就开着的。** 就像 `deepseek` 翻译后端标着 `requires_network=True`,你可以给配音也加一个同样性质的 API 后端,要更好音色时显式切过去。API 这一侧音色质量的天花板,目前被闭源完全占据——[Artificial Analysis 语音竞技场](https://huggingface.co/spaces/ArtificialAnalysis/Speech-Arena-Leaderboard) 上阿里 Fun-Realtime-TTS 当前 ELO 1227 排第一,最高的开源权重 Fish Audio S2 Pro 才约 1123。

![三条路:本地默认、唯一升级、跨语种皇冠](/blog/tts-apple-silicon/fig-three-roads.svg)
*Mac 上的配音后端,现实就三条路:① 本地默认留 MOSS(实时 + 48 kHz);② 唯一"更好又跑得动"的升级是 F5-mlx(MIT,待你在 M4 上实测);③ 跨语种皇冠 IndexTTS 2.5 / CosyVoice 3 没有 Mac 路径,只能上 GPU 或 opt-in 的 API。*

## 别信榜,信你自己的耳朵和机器

这次调研最该带走的,不是某一行参数,而是一种态度——它和 [配音评测那篇](/blog/dub-evaluation) 一脉相承:**别信一个数字替你拍板,把证据摊开自己看。** 这次的"一个数字",换成了"一张排行榜"。

我得把这次调研自己的不体面之处也摊开,不然就是双标:

- **Mac 速度的主源,是一个 33 星的个人基准、单台 M4。** 它的**速度**数据可信(有逐模型代码、且被多个独立报告印证),但它的**克隆质量盲听**只有 **397 票、单一一条英文参考音**——所以那份人评,我只当方向,不当定论。基准作者自己都写了"换条参考音再测一遍再下结论"。
- **榜单上的客观分,多是各模型作者自报、基线自测**,跨论文不严格可比(SIM 提取器、WavLM 版本都不同;中文报的其实是 CER)。VoxCPM "全面 SOTA" 这条,在对抗核验里被 3 票否决了——它客观分高,可盲听只排中游(#11),还被记了"音色漂移"。
- **许可证一个个看**:Coqui XTTS-v2 是 **CPML 非商用**(快归快,商用是坑);F5-mlx 是 MIT ✅;VoxCPM / OmniVoice 是 Apache-2.0 ✅。

所以这篇不给你一个"换上它就对了"的答案。它给你一张**地形图**和一条**验证路径**:挑 1 个说话人、5–10 句,跑 **MOSS(基线) vs F5-mlx(--q4) vs 一个 API**,用你现成的 dub_qa 仪器(ECAPA 散点 / backread / 音高 / 梅尔)再加**亲耳听**,把"榜上说"变成"你机器上、你耳朵里"的证据。

## 几条"为什么这么定"

把这次选型的取舍收拢成几条原则:

- **默认值锚在"能在本机跑通",不锚在排行榜。** 一台在你机器上跑不动的 SOTA,对本地优先的流水线等于不存在。MOSS-Nano 当默认不是因为它最像,是因为它在 Mac 上唯一实时、还原生 48 kHz。
- **"质量"要乘上"在你的硬件上能不能跑"。** 当前这批模型里,音色越好往往越依赖搬不到 Apple Silicon 的 CUDA 加速——选型必须把这条算进去,否则就是被榜单骗。
- **升级要找"既更好、又有原生路径"的窄门。** F5-TTS 的价值不在它分多高,而在它有 MLX 移植——这是目前唯一一条迈得过"Mac 可用"那条线的升级路。但**有路径 ≠ 已验证**,它得在你的 M4 上跑过整句才算数。
- **拿不到的,就显式标成"要上云"。** 跨语种皇冠本地够不着,那就把它做成一个 opt-in 的 API 后端,而不是假装本地能办到——和"云是主动打开的开关"同一种诚实。
- **别信榜,信你自己的耳朵和机器。** 排行榜是分诊信号,不是判决;最后那一下,交给你机器上的 RTF 和你耳朵里的音色。

## 小结

配音后端的默认值之争,在 Mac 上有个反直觉的结论:**音色榜单前排的开源模型,几乎全是为 CUDA 调的,搬上 Apple Silicon 不是慢,是趴窝;于是那台最不起眼的 MOSS-Nano,因为"唯一跑得动",反而是对的默认。** 想更好又不离开本机,目前只有一条窄门——F5-TTS 的 MLX 移植,而它还欠你一次 M4 实测;想要跨语种音色的皇冠,就得显式地走 GPU 或 API,像打开一个你清楚知道自己按下了的开关。

下一篇,我们回到算法线,把这条流水线的最后一棒讲完——**Task E:时间线贴合与混音**:配出来的句子长短不齐、还是一条干声,怎么把它塞回原片那一格格的时间线,再和背景重新混成一条能交付的声音。
