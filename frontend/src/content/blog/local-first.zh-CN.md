---
title: 默认不上云——本地优先，与那唯一的例外
slug: local-first
date: 2026-06-30
category: 决策
tags: [本地优先, 离线, 隐私, 可选依赖, DeepSeek, 决策记录]
summary: 这是博客的第一篇"决策记录"——不讲某一站怎么工作，讲一个贯穿全局的取舍：translip 为什么把一整条 ML 流水线默认跑在你自己的机器上。聊聊本地优先买到了什么（隐私、离线、不按分钟计费、可复现）、它的代价、我们怎么把代价压下去，以及那唯一允许上云的例外——以及为什么它必须是一个你主动按下的开关。
cover: /blog/local-first/fig-local-first-cover.svg
author: translip
readingTime: 13
---

# 默认不上云——本地优先，与那唯一的例外

> 这是 **幕后 · 博客** 的第五篇，也是第一篇**决策记录**。前面几篇要么走"数据的路"（算法），要么拉远看"那台机器"（架构）；这一篇换一种：不讲某一站怎么工作，讲一个**贯穿全局的取舍**。从最根上的那个决定说起——**本地优先**。

## 这一篇不讲"怎么做"，讲一个取舍

前面的算法篇回答"这一站如何工作"，架构篇回答"这些站如何被组织起来"。但有些决定，不属于任何一站——它们是**整条流水线的底色**，一旦定下，后面每一个小选择都被它牵着走。本地优先就是这样一个决定：

> **默认情况下，translip 的每一步——分离、转写、认人、翻译、配音、混音——都跑在你自己的机器上，一个字节都不上网。**

这不是一句口号，它是写死在默认值里的。`config.py` 里那一排 `DEFAULT_*`，每一个后端都是本地的：

```python
# config.py —— 每一个默认后端，都是本地的
DEFAULT_DIALOGUE_BACKEND          = "cdx23"               # 分离：本地
DEFAULT_TRANSCRIPTION_ASR_BACKEND = "funasr"              # ASR：本地（中文优先 paraformer-zh）
DEFAULT_TRANSLATION_BACKEND       = "local-m2m100"        # 翻译：本地（默认！）
DEFAULT_DUBBING_BACKEND           = "moss-tts-nano-onnx"  # TTS：本地
DEFAULT_RENDER_FIT_BACKEND        = "atempo"              # 时间线 / 混音：本地 ffmpeg
```

![默认全本地，只有翻译留了一条可选的上云岔路](/blog/local-first/fig-all-local-one-exception.svg)
*整条链路的默认后端都在本机；唯一一条通往云端的虚线岔路在"翻译"那一站，而且默认是关着的——要走它，你得自己显式扳过去。*

云端不是没有位置，但它的位置是**一个你主动扳过去的备选**，不是默认。这篇就讲清楚这个取舍：本地优先换来了什么、付出了什么、我们怎么让代价可接受，以及那唯一的例外凭什么是例外。

## 本地优先，买到了什么

把模型留在本机，不是为了情怀，是为了四件很实在的事。

**1. 隐私——像素和声音永远不离开这台机器。** 你要配音的，可能是还没上映的片子、客户的内部素材、家里的录像。本地优先意味着这些内容**根本不存在"被上传"这个动作**。对很多使用场景，这不是加分项，而是硬约束。

**2. 离线可跑。** 没网的剪辑间、内网隔离的工作站、飞机上——只要模型已经在本地缓存里，整条流水线照常跑。它不依赖任何一个"对方服务今天在不在线"。

**3. 不按分钟计费。** 一部剧上千句台词。如果 ASR、TTS 都走云 API 按量计费，一次试错就是一笔账单，反复调参更是。本地是**一次性的算力**：电费之外，跑多少次都不再花钱。

**4. 可复现——这一条最容易被忽略。** 本地权重是**钉死的**：今天这个 `htdemucs`、这个 `m2m100_418M`，明年还是同一个，输出可复现。云端模型却会**在你脚下悄悄变**。这不是假设——证据就写在 translip 自己的配置注释里：

```python
# config.py —— 连云端模型会过期这件事，都得显式记下来
# deepseek-v4-pro 是当前的前沿模型；旧的 deepseek-chat 别名
# 在 2026-07-24 之后改指 V4-Flash，然后退役。
DEFAULT_DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro")
```

一个云模型别名会在某个日期之后指向**另一个模型**。今天用它跑出的译文，明年同一条命令未必复现得出。本地权重不会有这个问题。

![本地优先买到的，与它的代价](/blog/local-first/fig-buys-vs-costs.svg)
*左边是本地优先换来的四件事；右边是它实打实的代价。决策记录的意义不在于假装没有代价，而在于把代价摊开，再说清楚我们怎么把它压到可接受。*

## 它的代价，以及我们怎么把它压下去

诚实地说，本地优先有真实的代价：

- **模型有体积。** demucs、funasr、m2m100、moss-tts-nano，外加可选的字幕擦除权重（`sttn.pth` 63 MB、`big-lama.pt` 196 MB）——第一次都得下载、占盘。
- **本机更慢。** CPU / Apple Silicon 上，重模型自然比云端 GPU 慢。
- **你得管权重。** 哪个模型缺、去哪下、放哪——这份心智负担本来在云那边，现在落到了本地。

translip 没有假装这些代价不存在，而是用三个具体设计把它们压下去。

**其一，默认值是为"笔记本"调的，不是为榜单调的。** 这是本地优先最容易被忽视、却最体现态度的地方——基准测试追的是分数，但在一台 Mac 上跑，要的是"别崩、还快得能用"：

```python
# config.py —— 默认值向"在笔记本上能跑"倾斜
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")  # 不支持的算子退回 CPU，而不是直接崩
# CDX23 分离窗口重叠：上游榜单用 0.8；0.5 在 CPU/MPS 上是好得多的默认——近乎无损，却快很多
DEFAULT_CDX23_OVERLAP = 0.5
```

**其二，基座精简，重的东西用到才装。** 基础安装只有 18 个依赖。真正重的（PaddleOCR 一整套、cv2）被切进**可选 extra**，而且**全部 lazy import**——你不开硬字幕检测 / 擦除，就完全不为它们付重量：

```toml
# pyproject.toml —— 基座精简；重的、可选的，藏在 extra 后面、用到才装
[project.optional-dependencies]
ocr   = ["paddlepaddle==3.1.1", "paddleocr==3.2.0", "paddlex==3.2.0", "pydantic-settings>=2,<3"]
erase = ["opencv-contrib-python>=4.10,<5", "pydantic-settings>=2,<3"]
# 两者都在用到时才 import —— 不开字幕功能，基础安装和其余流水线完全不受影响。
```

![精简基座 + 可选 extra：重依赖用到才装、用到才 import](/blog/local-first/fig-lean-base-extras.svg)
*基础安装是一个轻量内核；OCR / 字幕擦除这类重而可选的能力被装进 extra，并且只在真正运行到那一步时才被 import——没装也不影响其余流水线，只有真用到时才会给你一个清晰的"缺依赖"报错。*

**其三，把"管权重"做成一键。** 既然代价之一是"你得管模型"，那就把它做顺：模型按需下载到本地缓存（默认 `~/.cache/translip`，可用 `TRANSLIP_CACHE_DIR` 覆盖），管理界面能一键检测缺哪个、一键下载；命令行也有：

```bash
uv run translip download-models --model cdx23   # 预下载权重到本地缓存，之后离线可跑
```

## 那唯一的例外：上云，必须是一个 opt-in 的开关

本地优先不是教条。有一件事，本地的小模型确实吃力——**翻译**。台词要"信、达、雅"，术语要前后一致，本地 m2m100 这种小模型能做，但一个强 LLM 明显更好。所以 translip 在**翻译**（以及译文质检、台词校正仲裁）这几处，允许你切到云端的 DeepSeek。

但关键在于**它怎么被允许**。这不是"默认上云、你记得关掉"，而是反过来：**默认本地，你主动扳过去**。而且这个区别不是靠文档约定的，是**写进代码结构**的——翻译后端注册表里，每个后端都标好了"会不会离开本机"：

```python
# translation/registry.py —— 代码自己就标了"哪个后端会离开本机"
@TRANSLATION_BACKENDS.register(
    "local-m2m100",
    summary="Local M2M100 model (offline, no network required).",   # 默认 = 离线
)
def _build_m2m100(*, local_model=DEFAULT_TRANSLATION_LOCAL_MODEL, device="auto", **_):
    from .m2m100_backend import M2M100Backend          # 用到才 import
    return M2M100Backend(model_name=local_model, requested_device=device)

@TRANSLATION_BACKENDS.register(
    "deepseek",
    summary="DeepSeek chat-completions API (LLM translation).",
    requires_network=True,                              # ← 明确标记：这个会上云
)
def _build_deepseek(*, api_model=None, api_base_url=None, **_):
    from .deepseek_backend import DeepSeekBackend
    return DeepSeekBackend(model_name=api_model, base_url=api_base_url)
```

默认的 `local-m2m100` 简介里白纸黑字写着 *offline, no network required*；`deepseek` 则被显式打上 `requires_network=True`。还有一道闸：万一你选了上云、却没给钥匙，它**当场明确报错**，绝不偷偷降级、更不会默默把你的台词传出去：

```python
# deepseek_backend.py —— 选了上云却没给钥匙？当场报错，绝不偷偷上传或降级
self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
if not self.api_key:
    raise BackendUnavailableError("Missing DeepSeek API key. Set DEEPSEEK_API_KEY.")
```

![上云是一道默认关闭、需主动扳开、且缺钥匙就明确报错的闸](/blog/local-first/fig-optin-gate.svg)
*选后端：默认 local-m2m100 → 全程本机。主动切到 deepseek 才走这道闸：有 DEEPSEEK_API_KEY → 上云；没有 → 当场 BackendUnavailableError，不偷偷上传、不默默降级。*

落到命令上，两条路泾渭分明：

```bash
# 默认：全程在本机跑，一个字节都不上网
uv run translip run-pipeline --input ./drama-ep01.mp4 --target-lang en

# 想用云 LLM 翻译：显式切后端 + 给钥匙（缺钥匙会当场报错，不会偷偷上云）
DEEPSEEK_API_KEY=sk-... uv run translip run-pipeline --input ./drama-ep01.mp4 \
  --target-lang en --translation-backend deepseek
```

一句话概括这个例外的设计：

> **上云是一个你主动按下的开关，不是一个你需要记得关掉的开关。**

## 几条"为什么这么定"

把这个取舍收拢成几条原则：

- **默认本地，而非默认上云**：隐私和离线是很多场景的硬约束，所以"不上网"是地板，不是选项。云只在它明显更强的地方（翻译质量）作为**可选**出现。
- **把代价摊开，再压下去**：本地优先有真实代价（体积、速度、管权重），不假装它没有；用"为笔记本调的默认值 + 精简基座 + lazy 可选依赖 + 一键模型管理"把它压到可接受。
- **可复现优先于"永远最新"**：钉死的本地权重，胜过会在你脚下变的云模型——`deepseek-chat` 别名会在某日改指另一个模型，正是反例。
- **把"会不会上云"写进代码结构**：`requires_network=True` 的标记、缺钥匙就报错的闸——让"数据离开本机"这件事永远是显式、可见、可审计的，而不是藏在某个默认值里。

## 小结

本地优先是 translip 最根上的那个决定：默认情况下，你的素材从分离到成片，全程不离开这台机器。它买来隐私、离线、不计费和可复现，代价是体积、速度和一点管权重的心智——而这些代价被一整套"为本地而调"的默认值和可选依赖压到了可接受。至于云，它有且只有一个位置：**翻译那一站、一个默认关闭、需要你主动扳开、且缺钥匙就当场报错的开关。**

下一篇决策记录，我们接着聊一个同源的取舍：既然每一站都有好几个可插拔后端，**我们凭什么替你选了那个默认值**——以及什么时候你该覆盖它。
