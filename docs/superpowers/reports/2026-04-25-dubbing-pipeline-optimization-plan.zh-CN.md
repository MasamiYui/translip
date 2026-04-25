# 配音质量优化完整方案（video-voice-separate / translip）

**编写日期**：2026-04-25
**针对分析**：[`2026-04-25-task-20260425-023015-dubbing-quality-analysis.zh-CN.md`](./2026-04-25-task-20260425-023015-dubbing-quality-analysis.zh-CN.md)
**目标硬件**：Apple MacBook Air / M4 / 10 核 (4P+6E) / 16 GB 统一内存 / Metal 4
**目标任务**：中文视频→英文配音流水线（ASR → OCR 纠错 → 声纹建档 → 翻译 → TTS 克隆 → 时间轴混音）

---

## 0. 目录

1. [总览与目标指标](#1-总览与目标指标)
2. [当前现状（基线）](#2-当前现状基线)
3. [优化方案架构图](#3-优化方案架构图)
4. [方案 A：ASR 阶段升级](#4-方案-aasr-阶段升级)
5. [方案 B：说话人聚类与二次切分](#5-方案-b说话人聚类与二次切分)
6. [方案 C：翻译后端与术语保护](#6-方案-c翻译后端与术语保护)
7. [方案 D：TTS 后端与声纹克隆](#7-方案-dtts-后端与声纹克隆)
8. [方案 E：time-fit / mix 策略](#8-方案-etime-fit--mix-策略)
9. [实施路线图（按 Sprint 排布）](#9-实施路线图按-sprint-排布)
10. [验证与回归](#10-验证与回归)
11. [风险、资源与取舍](#11-风险资源与取舍)

---

## 1. 总览与目标指标

| 维度 | 当前值 | 目标值 | 目标提升 |
|---|---|---|---|
| 平均说话人相似度 | **0.321** | ≥ **0.55** | +71% |
| 配音覆盖率（placed/total） | 164 / 192 = 85.4% | ≥ **97%** | +11 pp |
| 完全丢失段（dropped） | 6 条 | **0** | -100% |
| time-fit overflow + underflow 不可拟合 | 44 / 192 | ≤ **15** | -66% |
| audible_coverage 失败 | 18 / 136 窗口 | ≤ **5** | -72% |
| ASR 逐行 alignment_score < 0.5 | 34 条 | ≤ **10** | -70% |
| OCR 替换率（ASR 被推翻率） | 73.4% | ≤ **40%** | ASR 更准 |
| content_quality 状态 | `blocked` | `passed` | 升级 |

> 这里列的目标是"发布级交付"（deliverable tier），审阅级（review tier）目标更松。

---

## 2. 当前现状（基线）

### 2.1 硬件

- **Apple M4 / 16 GB 统一内存 / 10 核**。
- **无独立 GPU**，但有 NPU（Apple Neural Engine）和 Metal GPU；可用 Core ML / MLX / ONNX (CoreMLExecutionProvider) 加速。
- **内存是最大约束**：跑通 7B fp16 ≈ 14 GB，基本只能跑 7B 量化 (Q4~Q5) 或更小。

### 2.2 流水线代码现状（与方案耦合点）

| 模块 | 路径 | 当前实现 |
|---|---|---|
| ASR | `src/translip/transcription/asr.py` | `faster-whisper` (CTranslate2) tiny/base/small/medium/large-v3；在 macOS 上**强制 CPU**（`asr.py:62` "faster-whisper does not support MPS directly"） |
| OCR 纠错 | `src/translip/asr_ocr_correct/` + `correction-report.json` | 文本层 fuzzy 对齐，`llm_arbitration` 字段类型为 `Literal["off"]`（**当前代码就不支持开**） |
| 声纹建档 | `src/translip/dubbing/` + `speaker_registry.json` | 直接用 ASR diarization 的 speaker_label；无纠正、无合并 |
| 翻译 | `src/translip/translation/` | 仅 `local-m2m100`（`facebook/m2m100_418M`）和 `siliconflow`（HTTP API） |
| TTS | `src/translip/dubbing/` | 仅 `moss-tts-nano-onnx`、`qwen3tts`（`qwen_tts_backend.py:96`） |
| 时长过滤 | `src/translip/dubbing/planning.py:103` | `1.0 ≤ duration ≤ 6.0` 硬编码，超出直接剔除（**导致 spk_0002 静默丢失的元凶**） |
| time-fit | `src/translip/rendering/runner.py:569-584` | `fit_policy ∈ {"conservative","balanced"}`，`max_compress_ratio` 可配 |

### 2.3 本次任务的症状复盘

- 192 分段中，**6 条（全 spk_0002）在 task-d 静默丢弃** → 根因 = `planning.py:103` 的 6 秒上限 + ASR 错并长段。
- **22 条在 task-e 被相邻段挤掉（skipped_overlap）** → 根因 = TTS 生成时长爆掉（`overflow_unfitted=36`, max 12.16 s）。
- **161 / 164 placed 段 speaker_similarity < 0.5** → 根因 = moss-tts-nano-onnx 克隆能力弱 + 参考样本少（spk_0005、spk_0007 仅 1 条）。
- **73.4% 句子被 OCR 替换文本** → 根因 = Whisper small 中文错字率高。
- 翻译出现 "Alibaba / Halifa Tower / Harry Potter"，专有名词无术语表保护。

---

## 3. 优化方案架构图

```
   ┌──────────────┐     ┌──────────────────┐     ┌────────────────┐
   │ 输入视频     │ →   │ A. ASR 升级       │ →   │ B. 说话人聚类  │
   │              │     │  faster-whisper   │     │  + 二次切分     │
   │              │     │  large-v3 + WhisperX │    │  + 声纹纠错   │
   └──────────────┘     └──────────────────┘     └────────────────┘
                                                         │
                                                         ▼
   ┌──────────────┐     ┌──────────────────┐     ┌────────────────┐
   │ E. time-fit   │ ←   │ D. TTS 克隆       │ ←   │ C. 翻译         │
   │  + 混音       │     │  CosyVoice2 / F5  │     │  Qwen2.5-7B     │
   │  质量闸门     │     │  多后端 fallback  │     │  + 术语表       │
   └──────────────┘     └──────────────────┘     └────────────────┘
          │
          ▼
   ┌──────────────┐
   │ 最终成片      │
   └──────────────┘
```

所有模块都引入 **可观测字段 + 可回退开关**，遵循仓库现有 `task-*-stage-manifest.json` + `*-report.json` 的 schema 惯例。

---

## 4. 方案 A：ASR 阶段升级

### 4.1 问题

- 当前 `faster-whisper small`，中文错字率高（本任务 100 行被 OCR 改写，alignment_score<0.5 有 34 行）。
- 分段质量差，长静默被当成单句并（spk_0002 的 34.91 秒超长段）。
- macOS 强制走 CPU（`asr.py:62`），large-v3 直接跑会慢。

### 4.2 方案

| 子方案 | 选择 | 说明 |
|---|---|---|
| **A1. 模型替换** | `faster-whisper large-v3` (INT8) 作为默认；可选 `mlx-whisper large-v3`（Apple 原生） | large-v3 中文 CER 比 small 低 50~70%。Apple M4 跑 large-v3 INT8 约 0.8~1.2x 实时；改用 `mlx-whisper` 能调到 1.5~2x 实时（利用 Metal）。 |
| **A2. 强制 VAD 预切** | 接入 `silero-vad` 或 `pyannote vad`，在 ASR 前切出语音段，避免把多人长静默合并 | 本任务 spk_0002 的 34.91 秒段最直接的解药。 |
| **A3. 引入 WhisperX 对齐** | WhisperX = faster-whisper + wav2vec2 强制对齐 | 把 ASR 的 word-level 时间戳精度从 ±0.3 s 提到 ±50 ms，解决 "dubbing_window:asr_anchor" 口型偏移 |
| **A4. 子句再分段** | 按标点、pyannote turn 切换点做二次切分，保证单段 1~6 秒 | 避开 `planning.py:103` 的硬过滤 |

### 4.3 技术实现

**代码变更点**（按接触面从小到大）：

1. `types.py:498` 把 `asr_model` 默认改为 `large-v3`。
2. `asr.py:60-65` 增加一个分支：`if os.environ.get("TRANSLIP_ASR_BACKEND") == "mlx"` 时走 `mlx-whisper`；否则沿用 `faster-whisper`。
3. 新增 `src/translip/transcription/vad.py`：silero-vad 包装，返回 `[(start, end)]` 后强制再 ASR。
4. 新增 `src/translip/transcription/resegment.py`：把 >6s 且包含标点 / 静默 > 0.5 s 的段切成多个 1-6 s 子段；并把 `segments.zh.json` 里的 `id` 保持（加 `_a/_b` 后缀），便于下游追踪。
5. 在 `asr-ocr-correct` 阶段**保留**旧 speaker_label 的同时，额外生成 `speaker_label_v2`，供说话人聚类模块（方案 B）消费。

### 4.4 本机运行参数

| 模型 | 体积 | 显存/内存 | 预期速度（525s 视频） |
|---|---|---|---|
| faster-whisper large-v3 INT8 | ~3 GB | 4~5 GB | 6~10 分钟 |
| mlx-whisper large-v3 (Metal) | ~3 GB | 3~4 GB | 3~5 分钟 |
| mlx-whisper medium | ~1.5 GB | 2 GB | 2~3 分钟（备用） |

### 4.5 预期收益

- ASR 原文 CER 从 ~15% → ~4%（中文 whisper large-v3 常规水平）。
- OCR 替换率从 73.4% → 30~40%。
- 超长 ASR 段（>6s）占比从 7 / 192 (3.6%) → < 0.5%。
- 消除因 `planning.py` 过滤导致的丢段（至少对 spk_0002 这种场景）。

---

## 5. 方案 B：说话人聚类与二次切分

### 5.1 问题

- `speaker_registry.json` 8 位说话人，其中 **spk_0005 / spk_0007 只有 1 条参考 clip**，无法训出稳定声纹。
- OCR 纠错发现"乐乐"但 speaker_label 还是旧的，可能存在两人被并入一个聚类的情况。
- 无跨任务声纹复用（所有 speaker 都是 `new_speaker`）。

### 5.2 方案

| 子方案 | 选择 | 说明 |
|---|---|---|
| **B1. 替换 diarization** | 从 whisper 自带的聚类换成 `pyannote/speaker-diarization-3.1` + `speechbrain/spkrec-ecapa-voxceleb` embedding | 专业 diarization，CER/DER 比 whisper 内建好很多。Apple Silicon 可用 ONNX。 |
| **B2. 参考 clip 下限** | 每个说话人至少 3 条 ≥ 2.0 秒的 clip；不足者自动降级到 `fallback_voice`（选 voice bank 中音色最近的一位，并标 `cross_speaker_fallback=true`） | 消除 spk_0005、spk_0007 "1 条样本" 场景 |
| **B3. 声纹 + 文本联合纠错** | 在 OCR 纠错发现人名（乐乐/娜娜/奶奶）时，把该段与同人名历史段的 embedding 做距离比较，若 > 阈值则拆分 speaker_label | 解决"文本换了但说话人没换"的问题 |
| **B4. 持久化声纹库** | 把 voice_bank 存成跨任务的全局索引，后续任务可以 "match existing speaker"（现在永远是 new_speaker）| 长期价值大 |

### 5.3 技术实现

1. 新增 `src/translip/transcription/diarization.py`：封装 pyannote pipeline；输入音频 → 输出 `[(start, end, speaker_id)]`。
2. 新增 `src/translip/voice_bank/embedding.py`：ECAPA-TDNN 提取 192-dim embedding。
3. 改 `src/translip/dubbing/` 的 voice bank 构建流程，每个 speaker 额外记录：
   ```json
   {"clip_count": 3, "min_clip_duration": 2.0, "embedding_centroid": [...], "fallback_candidate": "spk_0001"}
   ```
4. 在 `asr-ocr-correct` 里增加 `speaker_reassignment_report.json`，记录被重分配的段。
5. B4 需要新增 `~/.cache/translip/voice_bank_global/` 目录 + 简单 FAISS/SQLite 索引。

### 5.4 本机运行参数

| 模型 | 体积 | 速度 |
|---|---|---|
| pyannote-3.1 (ONNX) | ~50 MB | M4 CPU 约 5x 实时 |
| ECAPA-TDNN (ONNX) | ~20 MB | M4 CPU 约 10x 实时 |

### 5.5 预期收益

- 每个说话人保证 ≥ 3 clips → 声纹稳定性显著提升。
- 减少 speaker 错并场景，估计 speaker similarity 基线能从 0.32 提升到 0.40（单纯靠 diarization 改善）；配合方案 D 能到 0.55+。

---

## 6. 方案 C：翻译后端与术语保护

### 6.1 问题

- `local-m2m100 418M` 翻译质量弱，出现"Alibaba/Halifa Tower/Harry Potter/mom mom mom..."。
- 无 glossary，专有名词无保护。
- 句子长度失控（duration_ratio 均值 1.58），直接撑爆下游 TTS。

### 6.2 方案

| 子方案 | 选择 | 说明 |
|---|---|---|
| **C1. 升级主翻译后端** | **新增 `local-qwen2.5-7b-instruct-mlx-q4`** 作为默认；保留 siliconflow 和 m2m100 作 fallback | M4 16G 跑 Qwen2.5-7B Q4 约 12 tok/s，翻译 200 行约 1~2 分钟；质量远优于 m2m100 |
| **C2. 强制术语表** | 项目内置 `data/glossary/zh-en-travel-dubai.json`（哈利法塔→Burj Khalifa、迪拜→Dubai、乐乐/娜娜 等），在 prompt 里注入 | 解决专有名词误译 |
| **C3. 长度约束** | Prompt 明确告诉 LLM "target duration budget = X seconds, preferred English syllables = N"；并在解码后用 syllable counter 复核；超限则重翻 | 解决 mom mom mom 等病态重复和过长翻译 |
| **C4. 启用 LLM arbitration** | 当前 `types.py:74` 的 `llm_arbitration: Literal["off"]` → 扩展为 `Literal["off", "local-qwen", "siliconflow"]`；接入 OCR-only events 的裁决 | 本任务 8 条 ocr_only_events 都是 `reported_only`，有了裁决就能把它们修对 |

### 6.3 技术实现

1. 新增 `src/translip/translation/qwen_local_backend.py`，`backend_name = "local-qwen2.5"`。参考 `qwen_tts_backend.py` 的结构；用 `mlx-lm` 库（Apple 官方）加载 Qwen2.5-7B-Instruct-MLX-4bit。
2. `types.py:12` 扩展：`TranslationBackendName = Literal["local-m2m100", "siliconflow", "local-qwen2.5"]`。
3. `translation/runner.py:156` 添加分支；`subtitles/runner.py:28` 同步。
4. 新增 `data/glossary/` 目录，提交 1~2 个示例术语表。
5. 新增 `translation/length_guard.py`：用 `pyphen` 估算英文音节数，超出 `budget × 1.3` 就要求重翻。
6. 扩展 `asr-ocr-correct` 的 `arbitration` 分支，接入 LLM 后端。

### 6.4 本机运行参数

| 模型 | 体积 | 内存占用 | 速度 |
|---|---|---|---|
| `Qwen2.5-7B-Instruct` MLX-4bit | ~4.2 GB | 5~6 GB 峰值 | 12~15 tok/s |
| `Qwen2.5-3B-Instruct` MLX-4bit（备用） | ~2 GB | 3 GB | 25~30 tok/s |
| m2m100_418M（当前） | ~2 GB | 2.5 GB | ~ 8 sent/s |

### 6.5 预期收益

- 专有名词错译从当前 10+ 条 → 0（术语表强约束）。
- duration_ratio 均值从 1.58 → ~1.1（LLM 被明确告知时长预算）。
- OCR-only events 从 8 条 `reported_only` → 全部裁决完毕。
- 整体翻译 BLEU（相对 GT）从 ~25 → ~45（按 m2m100 vs Qwen2.5 公开基准推算）。

---

## 7. 方案 D：TTS 后端与声纹克隆

### 7.1 问题

- 当前 moss-tts-nano-onnx 克隆能力弱（平均 similarity 0.321，最低 -0.074 负相关）。
- qwen3tts 已在代码里但未被默认使用。
- 无 fallback，一个后端失败就整段失败。

### 7.2 方案（按本机可运行性排序）

| 后端 | 定位 | 本机可行性 | 克隆相似度参考值 |
|---|---|---|---|
| **CosyVoice2-0.5B**（FunAudioLLM） | **推荐主后端** | ONNX/Libtorch 可跑，M4 16G 可行，约 0.6~0.8x 实时 | zero-shot 相似度 0.55~0.65 |
| **F5-TTS**（small） | 备用主后端 | PyTorch/Metal 可跑，约 0.8x 实时 | 0.50~0.60 |
| **GPT-SoVITS v2**（小模型 + 声纹微调） | 离线定制主角 | 每人微调需 5~10 分钟（M4），之后推理极快 | 微调后 0.65+ |
| **IndexTTS-1.5-small** | 轻量 fallback | ~2x 实时 | 0.40~0.50 |
| moss-tts-nano-onnx（现有） | 降级 fallback | 已有 | 0.30 |
| qwen3tts（现有） | 云端 fallback | 网络依赖 | 不确定 |

### 7.3 技术实现

**子方案 D1：引入 CosyVoice2 后端**

1. 新增 `src/translip/dubbing/cosyvoice2_backend.py`，`backend_name = "cosyvoice2"`。接口对齐现有 `QwenTTSBackend`（`qwen_tts_backend.py:95`）。
2. `types.py` 扩展 `TTSBackendName`；`runner.py:1004` 分支增加 cosyvoice2。
3. 首次运行自动从 HuggingFace 下载 `FunAudioLLM/CosyVoice2-0.5B`（~1 GB）。

**子方案 D2：多后端 fallback 链**

- `request.tts_backends = ["cosyvoice2", "f5-tts", "moss-tts-nano-onnx"]`；当某段 `speaker_similarity < 0.5` 时自动重试下一个后端（当前代码已有 `tts_backends` 字段，但只用于选择单一 backend，没有 per-segment retry 逻辑）。
- 在 `task-d-manifest.json` 里新增 `backend_trace`：`[{"backend":"cosyvoice2","similarity":0.31},{"backend":"f5-tts","similarity":0.61,"selected":true}]`。

**子方案 D3：参考 clip 预处理管线**

- 自动去噪（`rnnoise` 或 `demucs htdemucs_ft`）+ 归一化（-23 LUFS）+ 去静默段。
- 对每个 speaker 选择"最干净"的 3 条 clip（信噪比最高）作为最终参考。

**子方案 D4：TTS 生成时长硬上限**

- 在 TTS 生成后立即检查 `generated_duration`，如果 > `source_duration × 1.5` 则标记为 `generated_too_long`，触发重试（不同 temperature / seed）。
- 当前管线直到 task-e 才发现时长问题，浪费一次合成。

### 7.4 本机运行参数

| 模型 | 磁盘 | 内存 | 速度 |
|---|---|---|---|
| CosyVoice2-0.5B | 1.0 GB | 3~4 GB | 0.6~0.8x 实时 |
| F5-TTS small | 0.5 GB | 2 GB | 0.8x 实时 |
| GPT-SoVITS v2 (微调后) | 0.3 GB × N 人 | 1~2 GB | 3x 实时 |
| moss-tts-nano-onnx（现） | 0.1 GB | 1 GB | 5x 实时 |

### 7.5 预期收益

- 平均 speaker_similarity：0.321 → **0.55~0.65**（CosyVoice2 zero-shot 基线）。
- 配合方案 B 声纹纯度提升，可进一步上探到 **0.70**。
- 通过 fallback 链 + 时长上限，overflow_unfitted 事件显著降低。

---

## 8. 方案 E：time-fit / mix 策略

### 8.1 问题

- `fit_policy=conservative` 不允许裁剪，遇到 overflow 只能硬塞 → `skipped_overlap 22` + `tail_trimmed 42`。
- `max_compress_ratio=1.45` 偏保守，`overflow_unfitted 36` 里有一半其实到 1.55~1.7 就能救回来。
- audible_coverage 18 条未覆盖字幕窗口。

### 8.2 方案

| 子方案 | 选择 | 说明 |
|---|---|---|
| **E1. 分级 fit 策略** | 引入新模式 `fit_policy="adaptive"`：先尝试 `direct→compress→pad→smart_trim`（智能裁内容末尾非关键词） | 在仓库现有基础上加一档，原有 conservative/balanced 不动 |
| **E2. 放宽 compress 上限** | `max_compress_ratio` 默认从 1.45 → 1.6（配合 atempo 多级），听感临界阈值还能接受 | 能救回 ~60% 的 overflow_unfitted |
| **E3. 语音区间调度** | overflow 段的末尾按"句末→逗号→空白"优先级裁剪 TTS 音频；配合 forced alignment 切在词边界 | 避免把单词切一半 |
| **E4. 后段让位机制** | 当后段自身有 ≥ 0.5s 静默头时，允许前段跨入后段；目前是严格禁止 | 多救 5~10 段 |
| **E5. 质量闸门** | task-e 结束加 `quality_gate`：speaker_similarity/placement_coverage/audible_coverage 三项任一不达标时返回 `status=review`，并给出分段列表让 UI 标红 | 从"盲目发布"变"主动复审" |

### 8.3 技术实现

改 `src/translip/rendering/runner.py`：

- L285 验证放宽：`if normalized.max_compress_ratio < 1.0 or > 2.0: raise`。
- L569-584 新增 `adaptive` 分支。
- 新增 `runner.smart_trim_tail(tts_audio, target_duration, word_timestamps)` 函数。

改 `src/translip/rendering/export.py`：
- `mix_report` 里新增 `quality_gate` 结构。

### 8.4 预期收益

- overflow_unfitted 从 36 → ~10。
- skipped_overlap 从 22 → ~8。
- audible_coverage 失败从 18 → ~5。

---

## 9. 实施路线图（按 Sprint 排布）

> 按"改动最小 + 收益最大"优先

### Sprint 1（1~2 天，纯配置）：立刻把 blocking 降到 review

| 任务 | 动作 | 预期效果 |
|---|---|---|
| S1-1 | `asr_model=large-v3`（或 `mlx-whisper large-v3`） | ASR 错字率 -60% |
| S1-2 | `translation_backend=siliconflow` + 接入 DeepSeek/Qwen2.5 | 翻译质量立刻可用 |
| S1-3 | 提供 `data/glossary/zh-en-travel-dubai.json`，CLI 里带 `--glossary` | 专有名词错译清零 |
| S1-4 | `max_compress_ratio=1.6`；`fit_policy=balanced` | time-fit 救回 30%+ |
| S1-5 | `tts_backends=["moss-tts-nano-onnx","qwen3tts"]`（现有即可） | 获得一层 fallback |

> **Sprint 1 不改代码，只改配置**，预期 speaker_similarity 均值 0.32→0.40、丢段数 28→15。

### Sprint 2（3~5 天，代码小改）：修关键 bug

| 任务 | 动作 | 影响文件 |
|---|---|---|
| S2-1 | 修复 `planning.py:103` 的 6 秒上限硬过滤（改为"大于 6 秒先尝试切分；仍不行再 fallback"） | `dubbing/planning.py`, `dubbing/runner.py` |
| S2-2 | 在 ASR 后加 VAD + 子句再切分模块 | 新增 `transcription/resegment.py` |
| S2-3 | TTS 生成时长硬上限（`generated > src × 1.5` 触发重试） | `dubbing/runner.py` |
| S2-4 | voice_bank 最少 3 clips 约束 + cross_speaker fallback | `dubbing/` |
| S2-5 | `mix_report.quality_gate` 结构 | `rendering/export.py` |

> Sprint 2 结束：丢段应归零，平均 similarity 预期 ≥ 0.45。

### Sprint 3（1~2 周，引新模型）：大幅提升 TTS 质量

| 任务 | 动作 |
|---|---|
| S3-1 | 新增 `cosyvoice2_backend.py`（主后端） |
| S3-2 | 新增 `qwen_local_backend.py`（翻译后端，MLX） |
| S3-3 | 引入 pyannote diarization 与 ECAPA-TDNN embedding |
| S3-4 | LLM arbitration 接入（扩展 `llm_arbitration` 的 Literal 类型） |
| S3-5 | WhisperX 强制对齐（口型问题的根治） |

> Sprint 3 结束：speaker_similarity 均值预期 ≥ 0.55，content_quality = passed。

### Sprint 4（长期）：平台化

- 全局 voice_bank（跨任务复用）
- GPT-SoVITS 微调 pipeline（对主角做 5 分钟专属微调，similarity 冲 0.75+）
- 自动 QA 报告可视化

---

## 10. 验证与回归

### 10.1 回归数据集

以本次 `task-20260425-023015` 为 **Golden Case**，每个 Sprint 结束跑一遍，指标对比表必须变好。

追加 2~3 个差异化场景：

- 单人访谈（单 speaker，长句）
- 动画片（情绪夸张、声线多变）
- 纪录片（解说 + 多采访嘉宾）

### 10.2 自动化指标

在 `tests/regression/` 下新增 pytest 场景：

```python
def test_no_silent_drop():
    report = json.load(open(f"{OUT}/task-e/voice/mix_report.en.json"))
    total = len(json.load(open(f"{OUT}/task-c/voice/translation.en.json"))["segments"])
    placed = len(report["placed_segments"])
    skipped = len(report["skipped_segments"])
    assert total == placed + skipped, "silent drops detected"

def test_speaker_similarity():
    report = ...
    assert report["quality_summary"]["averages"]["speaker_similarity"] >= 0.55

def test_content_quality_passed():
    assert report["content_quality"]["status"] == "passed"
```

### 10.3 手动听感评估

制作 3 份配音 mp4（基线 / Sprint2 / Sprint3），每份 30 秒样片，随机播放给 3 位标注员打分（音色像不像 1-5 分，节奏自然 1-5 分）。

---

## 11. 风险、资源与取舍

### 11.1 风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| CosyVoice2 在 M4 上实际速度比标称慢 | 520 s 视频 TTS 可能要 15~20 分钟 | 保留 moss fallback；文档里明确"本地离线模式慢换质量" |
| Qwen2.5-7B MLX 4bit 内存峰值可能飙到 8 GB | 与 whisper large-v3 + CosyVoice2 同时驻留时可能 OOM | 引入 "序列化加载/卸载" 策略（每阶段跑完立刻 del + gc） |
| pyannote 对背景噪声敏感 | 可能比 whisper 内建 diarization 更差 | 加"两套 diarization 比较"的开关，取 DER 低者 |
| glossary 术语表需要人工维护 | 每部新片都要补词 | 先做基础词库；长期可用 NER + OCR 自动抽取候选词 |

### 11.2 资源预估

- **磁盘增量**：~12 GB（whisper large-v3 + Qwen2.5-7B-MLX + CosyVoice2 + pyannote + F5-TTS）。
- **新 Python 依赖**：`mlx`, `mlx-lm`, `mlx-whisper`, `pyannote.audio`, `speechbrain`, `pyphen`, `silero-vad`；全部 Apple Silicon 友好。
- **CI**：现有的 `pytest` + `ruff` 体系能直接跑；加一条 "golden case 回归" dispatch。

### 11.3 取舍建议

如果只能投入有限精力，**优先级 = S2-1 > S1-1 > S1-3 > S3-1 > 其他**。

- **S2-1（planning.py 6 秒上限）** 是"丢段归零"的一行代码修复，ROI 无敌。
- **S1-1（ASR 升级）** 是文本质量的天花板。
- **S1-3（glossary）** 是客户端看到翻译质量的直接信号。
- **S3-1（CosyVoice2）** 是"音色像不像"的决定性改动。

### 11.4 放弃的方案及原因

- **ChatTTS / Spark-TTS**：开源许可不明 / 克隆能力比 CosyVoice2 弱。
- **VALL-E X**：开源实现不稳，M4 跑非常慢。
- **训练自定义 diarization 模型**：ROI 低，pyannote 现成够用。
- **云端 TTS（ElevenLabs / Azure）**：用户明确要本机运行。

---

## 附：一览表

| Sprint | 工期 | 主要产出 | 预期 similarity | 预期 drop | 预期 content_quality |
|---|---|---|---|---|---|
| 当前基线 | — | — | 0.321 | 28 / 192 | blocked |
| S1 | 1~2 天 | 改配置 + glossary | 0.40 | 15 | review |
| S2 | 3~5 天 | 修关键 bug | 0.45 | 0 | review |
| S3 | 1~2 周 | 新模型全量接入 | 0.55~0.65 | 0 | passed |
| S4 | 长期 | 全局声纹库 + 微调 | 0.70+ | 0 | passed |

> **一句话结论**：本机 M4 / 16G 足以跑起"whisper-large-v3 + Qwen2.5-7B-4bit + CosyVoice2-0.5B + pyannote"的完整新栈，预期把平均 speaker_similarity 从 0.32 提到 0.60+，同时彻底消除静默丢段问题。
