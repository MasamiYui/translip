# 任务 `task-20260425-023015` 配音质量问题分析报告

**分析对象**：`/Users/masamiyui/.cache/translip/output-pipeline/task-20260425-023015`
**素材**：`test_video/我在迪拜等你.mp4`（约 525 秒，8 位说话人，192 条分段）
**配置摘要**：`template=asr-dub+ocr-subs`，`asr_model=small`，`translation_backend=local-m2m100`，`tts_backend=moss-tts-nano-onnx`，`fit_policy=conservative`，`fit_backend=atempo`
**分析日期**：2026-04-25

---

## 一、核心结论（TL;DR）

这条流水线**每一个环节都出了问题**，而且问题会沿管道放大。最终现象上看是"音色对不上、配音丢失、对不准口型"，但根因可以归纳为 **4 大类**：

| 类别 | 关键指标（来自 `mix_report.en.json` 的 quality_summary） |
|---|---|
| **文本本身就不准**（ASR + 翻译叠加错误） | `use_ocr` 决策 129 / 192，OCR 纠正的行文本 100 条；`alignment_score < 0.5` 的行 34 条；翻译中出现 Halifa、Alibaba、Harry Potter 等人名地名错译 |
| **音色不匹配** | placed 段 **平均说话人相似度 0.321**（极低），**161 / 164 条 < 0.5**；spk_0006 平均仅 0.191，spk_0005 平均 0.199，出现 -0.074 的负相关样本 |
| **TTS 时长爆掉** | `fit_strategy` 里 `overflow_unfitted=36`、`underflow_unfitted=8`、`compress=57`，整体 `duration_ratio` 均值 1.58；多个片段 TTS 生成到 10~12 秒顶到上限（spk_0001 的 "Happy mom mom mom mom..."，spk_0005 的 "Good morning" 被合成 12.16 秒） |
| **语音直接丢失** | 192 条翻译 → mix_report 中仅 placed=164、skipped=22；**剩下 6 条（全部属于 spk_0002）完全没有进入配音流水线**；外加 skipped 22 条和 audible_coverage 18 条字幕窗口未覆盖 |

总体质量门 `content_quality.status = "blocked"`，失败原因：`coverage_below_deliverable_threshold`、`upstream_failed_segments`、`speaker_similarity_failed`、`audible_coverage_failed`。

---

## 二、按阶段拆解具体原因

### 阶段 1：ASR 转写（task-a）—— 错字率高，吃掉下游

- `asr_model=small`（Whisper small），对这种带环境噪音、多人对话的片源识别能力偏弱。
- 实际 `stats.speaker_count=8`、`segment_count=192`，但例子能看到大量错字：
  - "娜娜 你在哪儿啊" → 正确应为 "乐乐你在哪呢"
  - "哈里巴塔" → "哈利法塔"
  - "三分钟之后 停车展间" → "停车场见"
  - "是啊 我已经在接手了" → "我已经在机场了"
- 更严重的是 **ASR 的 VAD/分段把几段长静默当成一个语音段合并**。`task-c` 里 `spk_0002` 的 6 条都超过 6 秒（8.9、11.56、11.95、17.94、20.03、**34.91** 秒），但文本极短（"奶奶"、"把篷打开"、"对不起我弄错了"）。这是典型的 ASR 片段合并错误（duration_ratio 低至 0.057）。

### 阶段 2：OCR 引导纠错（asr-ocr-correct）—— 缓解但引入新风险

`correction-report.json` 总结：
- `corrected_count=141`（73.4% 的句子被 OCR 替换）
- `kept_asr_count=24`、`review_count=27`、`ocr_only_count=8`
- `decisions: use_ocr=129, review=27, use_asr=24, merge_ocr=12`

这说明 ASR 原文本质量差到要靠硬字幕 OCR 来"救"，但产生两个副作用：

1. **文本时间戳被重锚**。例如 `seg-0001` 从 ASR 的 [15.73, 18.14] 锚定到 `dubbing_window=[15.991, 18.636]`，警告 `asr_start_precedes_ocr_window`；`mix_report` 里 **104 条** 带注解 `dubbing_window:asr_anchor`、14 条 `late_ocr_anchor`、17 条 `ocr_extended_anchor`——这种时间轴再锚会让配音口型错位。
2. **文本换了但说话人归属没换**。例如 OCR 发现"乐乐"而不是"娜娜"，但 `speaker_label` 仍沿用 ASR 原始的 `SPEAKER_00` 聚类结果。如果 ASR 把两个人错分到同一个聚类里，后续所有流程都会继续用错的声纹。

### 阶段 3：说话人建档（task-b）—— 几乎没有可用参考样本

`speaker_registry.json` 登记了 8 个说话人，`speaker_profiles.json` 给出每人参考片段数：
- spk_0000：3 条 / spk_0001：5 / spk_0002：3 / spk_0003：5 / spk_0004：5 / **spk_0005：1** / spk_0006：4 / spk_0007：1

**spk_0005 和 spk_0007 只有 1 条参考 clip**，根本无法训出有辨识度的声纹。这也解释了 task-e 中这些说话人的相似度最低（spk_0005 平均 0.199，spk_0006 平均 0.191，均值 < 0.2，属于"几乎随机"的水平）。

`speaker_matches.json` 里所有说话人全部判定为 `new_speaker`，说明没有任何历史注册库可借鉴，并没有跨任务复用声纹。

### 阶段 4：翻译（task-c）—— 语义错误叠加

用的是 `local-m2m100`（batch=4），对专有名词几乎无保护：
- "哈利法塔" 翻成 "**Halifa Tower**"、"**Hollywood Tower**"
- "哈利波特" 翻成 "**Harry Potter**"（正确但原文本身是 OCR 混入的"哈利波特的场景"）
- "哈里巴塔" 翻成 "by Haribata"
- "阿里波特" 翻成 "**Alibaba**"
- "奶奶" 翻成 "The grandmother"
- "我妈说了/感情是需要磨合的" 等有 8 条 `ocr_only_events` 标 `needs_review=true` 但 `action=reported_only`（只报告，没拦下）

`duration_budget.fit_level=fit` 基本上都写着 fit，但对 spk_0002 的长片段出现 `duration_ratio=0.057~0.181`（极度空洞），翻译器根本没被告知要"填满"源时长，这是 task-c 和下游 fit 策略的接口错位。

### 阶段 5：单人声克隆（task-d）—— **spk_0002 被整组丢弃**

这是"语音丢失"的最直接、最决定性原因。代码证据：

- `src/translip/dubbing/planning.py:103` 中 `is_usable_task_d_segment`：
  ```python
  if duration_sec < 1.0 or duration_sec > 6.0:
      return False
  ```
- `orchestration/runner.py:347` 用 `pick_task_d_speaker_ids` 选候选说话人，要求 `usable_counts > 0`。

spk_0002 的 6 条翻译时长全部 > 6 秒（见上表），`usable_counts['spk_0002'] = 0`，于是 **整个 spk_0002 被跳过**，`task-d-stage-manifest.json` 的 `selected_segment_map` 里直接没有 spk_0002 这一项。

**结果**：`seg-0013 / 0072 / 0078 / 0083 / 0106 / 0107` 共 6 条翻译既不在 placed 里、也不在 skipped 里，在 task-e 中**静默消失**（`192 - 164 - 22 = 6`）。

此外 task-d 合成质量也普遍差：
- `overall_status_counts`：failed 83 / review 98 / **passed 仅 5**（186 段中）
- `poor_speaker_match` 频繁触发 `quality_retry_reasons`，重试最多也就把相似度抬到 0.4 级别
- 音色对不上的主因是 **moss-tts-nano 本身克隆能力有限 + 参考样本少/短**；spk_0000 的示例里 backread_text 与 target_text 相似度 1.0（能说对），但 `speaker_similarity=0.286`（声音像另一个人）。

### 阶段 6：时间轴拟合与混音（task-e）—— 丢段 + 时长挤压

`mix_report.en.json` 给出完整画像：

- **placed=164，skipped=22，完全丢失=6**（合计 28 条未出现在最终音轨，占比 14.6%）
- **skip_reason_counts = { skipped_overlap: 22 }**：22 条都是因为与前一条 TTS 音频在时间上重叠，被后一条挤掉。典型例子：
  - `seg-0047` "What logic." 被 `seg-0046` 覆盖
  - `seg-0074` "Good Morning" 生成了 12.16 秒（上限被打爆），挤掉后面的段
  - `seg-0089` "Happy mom mom mom mom mom mom mom"（m2m100 翻译重复病 + TTS 10 秒）
  - 12 条标 `replaced_by:seg-xxxx`，说明是后段盖掉前段

- **fit_strategy 分布**：`overflow_unfitted 36 + underflow_unfitted 8`，合计 44 段 **atempo 都调不回时长**（超过 `max_compress_ratio=1.45` 或超短段没法拉长）。`fit_policy=conservative` 不允许丢内容，只能硬塞 → 42 段标 `tail_trimmed_for:xxx`（把后段头尾砍掉腾位置），32 段标 `overflow_trimmed`。

- **audible_coverage**：`subtitle_window_count=136, failed_count=18`，有 18 个字幕窗口没有可听配音覆盖，`min_coverage_ratio=0.0`。

- **averages.speaker_similarity=0.3211**（< 阈值 0.5），`speaker_failed_ratio=0.1774`，`speaker_status=failed` 的 33 条、`review` 的 138 条——这正是用户主观感受到的 "配音和人物音色对不上"。

---

## 三、把现象映射到根因

用户报告了三类现象，分别对应下面的具体原因：

### 现象 A：大量配音音色和人物对不上

1. **声纹参考样本太少/太短**（spk_0005、spk_0007 各 1 条；spk_0000/2 各 3 条），embedding 没有稳定中心。
2. **MOSS-TTS-Nano-100M-ONNX 作为 zero-shot 克隆模型能力弱**，整体相似度均值 0.321、中位数 0.319，仅 3 条 ≥ 0.5。
3. **说话人聚类错误未被纠正**：OCR 纠错能改文本但不会重划 speaker_label；ASR 的 `SPEAKER_00` 里可能混了"乐乐"和"娜娜"两个不同孩子的声音（从 seg-0001 的错字性质可推断），后续给到同一个 spk_0000 参考，合成的 TTS 自然"谁都不像"。
4. **片段边界不稳**：`ocr_guided` 重锚时间轴，裁参考 clip 时可能切到静音/背景声，也降低了声纹纯度。

### 现象 B：语音丢失

按丢失类型分级：

| 丢失类型 | 数量 | 根因 |
|---|---|---|
| task-d 阶段直接剔除 | **6 条（全属 spk_0002）** | `is_usable_task_d_segment` 强制 1s ≤ duration ≤ 6s，而 ASR 把 spk_0002 的所有片段都错并成 8.9~34.9 秒长段，全被过滤 |
| task-e 因时间轴重叠被挤掉 | 22 条 | TTS 生成时长经常爆掉（overflow_unfitted=36 / underflow=8），相邻段被后段替换（`replaced_by`）或尾巴被砍（`tail_trimmed_for`） |
| 字幕窗口未被覆盖 | 18 条（`audible_coverage.failed_count`） | 配音窗口被过度压缩后 placement 提前结束，没盖满字幕时间段 |

### 现象 C：转写/配音错位（口型对不上）

1. **ASR 分段不稳 + OCR 重锚**：`dubbing_window` 来源分布 —— `asr_anchor:104`、`ocr_extended_anchor:17`、`late_ocr_anchor:14`、`late_ocr_anchor+ocr_extended_anchor:1`；一旦用 OCR 窗口重锚，起始时间可能比真实开口晚 0.3~1s。
2. **翻译长度和源时长严重失配**：`duration_ratio` 均值 1.58，很多句子被 atempo 压 1.4 倍，听起来像"快进"。
3. **m2m100 翻译质量低**导致 TTS 念出 "mom mom mom mom..."、"by Haribata" 这类异常长度，进一步撑爆时间线。

---

## 四、改进建议（按投入产出比排序）

**立即能做的**（纯配置/参数）：

1. 把 `asr_model` 从 `small` 升级到 `medium` 或 `large-v3`，文本错误率应能下降一半以上，也能改善 diarization 的边界准确度。
2. 把 `translation_backend` 改为 `siliconflow` 或 LLM 后端，至少启用 `glossary_path` 锁定"哈利法塔 → Burj Khalifa"、"迪拜 → Dubai"、"乐乐/奶奶"等专有名词。
3. 提高 `fit_policy` 到更激进档位（允许裁剪），或把 `max_compress_ratio` 适当放宽，同时对 TTS 生成设置硬上限（例如不超过源时长 × 1.5），避免 10~12 秒的病态产物。
4. 启用 `llm_arbitration`（当前是 `off`），让 LLM 做 OCR-only 事件的裁决，把那 8 条 `reported_only` 事件补齐。

**改代码层（中期）**：

5. **修 `is_usable_task_d_segment` 的 6 秒上限**：对超长片段应在 task-a/task-c 阶段先做二次切分（按标点 / 句子 / 静音），而不是直接丢。目前这是**任务 spk_0002 完全静默**的唯一原因。
6. **让 OCR 纠错也能纠正 speaker_label**：当 OCR 文本强匹配到某说话人（如识别到"乐乐"）时，把段落重分配到正确 speaker_id，而不是沿用 ASR 的聚类。
7. **提高参考样本下限**：voice_bank 构建时要求每个说话人 ≥ 3 条 ≥ 2 秒的参考；少于该量的说话人走 "fallback voice" 而不是硬上 1 条 clip。
8. **TTS 重试策略扩展**：`quality_retry_reasons=poor_speaker_match` 目前只能换参考 clip；可以引入"跨说话人声纹 fallback"或者切到备用 TTS 后端（如 qwen3-tts），本任务配置里 `tts_backends` 只填了 moss 一个。

**长期**：

9. 替换 MOSS-TTS-Nano 为声纹克隆能力更强的后端（CosyVoice / F5-TTS / qwen3-tts，仓库里已有 qwen3 迁移计划）。
10. 在 task-e 层实现"段落重叠智能合并"而不是简单 replace，保留被挤掉的翻译文本（至少进字幕）。

---

## 五、关键证据汇总（可复核）

| 指标 | 值 | 来源文件 |
|---|---|---|
| 总分段 | 192 | `task-a/voice/segments.zh.json` |
| OCR 替换比率 | 73.4% | `asr-ocr-correct/voice/correction-report.json > summary.auto_correction_rate` |
| spk_0002 被完全丢弃 | 6/6 段 | `task-d/task-d-stage-manifest.json > selected_segment_map`（缺 spk_0002） |
| 代码中的硬过滤条件 | `1.0 <= dur <= 6.0` | `src/translip/dubbing/planning.py:103-108` |
| 最终 placed / skipped / 丢失 | 164 / 22 / 6 | `task-e/voice/mix_report.en.json` + 反推 |
| 平均 speaker similarity | 0.3211 | `mix_report > quality_summary.averages.speaker_similarity` |
| 爆时长的 fit 策略 | overflow 36 + underflow 8 | `mix_report > stats.fit_strategy_counts` |
| content_quality 状态 | blocked | `mix_report > content_quality` |
