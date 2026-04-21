# Task D/E 配音质量门控、双轨产物与返修队列技术方案

## 1. 背景

当前 Task D 已能为每个 `segment_id` 生成配音音频，并输出自动评估结果：

- `duration_status`
- `speaker_status`
- `intelligibility_status`
- `overall_status`

但 Task E 当前只要音频文件存在，就会把该片段放入时间线。结果是：即使 Task D 有大量 `overall_status=failed`，Task E/G 仍可能输出 `succeeded`，造成“工程成功”和“内容可交付”混淆。

本方案目标不是直接修复所有 failed 片段，而是先建立一个可执行的质量门控机制，让系统能区分：

- 可交付正式版
- 宽松审听版
- 待返修片段

## 2. 核心目标

1. Task E 输出两套音轨：
   - `strict`：正式质量门控版本，只使用合格片段
   - `loose`：宽松预览版本，尽量使用所有有音频的片段

2. Task D/E 共同产出 `repair_queue`：
   - 记录所有未进入 strict 版本的片段
   - 明确失败原因、可采取动作和优先级

3. Pipeline 成功状态不再只代表“程序跑完”，而要能报告“内容可用比例”。

4. 为后续自动重试、短句合并、配音改写、换模型、人工返修提供稳定数据入口。

## 3. 范围与非目标

本方案分为两层：

- 第一层是质量门控与双轨产物，这是必须先落地的基础能力。
- 第二层是基于 `repair_queue` 的自动返修与人工返修闭环，这是后续质量提升的主要路径。

本方案会完整定义第二层的技术路线，但第一阶段实现不要求一次性完成全部返修能力。

### 3.1 当前阶段非目标

- 不在质量门控第一阶段强制接入新 TTS 模型
- 不在质量门控第一阶段强制实现自动配音改写
- 不在质量门控第一阶段强制实现人工返修 UI
- 不在本阶段实现 lip-sync
- 不在本阶段重新设计 Task A/B/C/D 的全链路协议

### 3.2 后续阶段目标

`repair_queue` 后续必须能够驱动：

- 短句合并
- 配音改写
- 多候选重生成
- 换参考音频
- 换 TTS 模型
- 人工返修 UI

这些能力不是质量门控的替代品，而是质量门控发现问题后的处理闭环。

## 4. 当前问题

以 `task-20260420-170343` 为例：

```text
Task D 总段数: 192
overall failed: 161
overall review: 31
overall passed: 0

Task E 放入时间线: 191
Task G 最终状态: succeeded
```

这说明当前系统会把大量质量失败片段放入最终混音，导致最终状态缺乏内容质量含义。

## 5. 新增概念

### 5.1 Strict Timeline

正式时间线，只允许满足门控规则的片段进入。

默认规则：

```text
allow_status = ["passed", "review"]
deny_status = ["failed"]
```

可配置为更严格：

```text
allow_status = ["passed"]
```

### 5.2 Loose Timeline

宽松时间线，只要音频存在、时间线可放置，就进入。

用途：

- 快速听完整片子节奏
- 定位 failed 片段的真实听感
- 给人工审片提供上下文

### 5.3 Repair Queue

返修队列，记录所有未进入 strict timeline 的片段。

来源包括：

- Task D `overall_status=failed`
- Task E 缺音频
- Task E 缺 anchor
- Task E 时长非法
- Task E 重叠跳过
- Task E 超出可接受压缩范围

### 5.4 Repair Action

返修动作是 `repair_queue` 对每个问题片段给出的处理建议和执行记录。

系统内置动作建议包括：

```text
merge_short_segments
rewrite_for_dubbing
regenerate_candidates
switch_reference_audio
switch_tts_backend
manual_review
```

每个动作必须记录：

- 触发原因
- 输入文本和音频
- 生成的新候选
- 自动评估结果
- 是否被选中进入 strict timeline

## 6. 输出产物设计

Task E 输出目录建议扩展为：

```text
task-e/voice/
  strict/
    dub_voice.en.wav
    preview_mix.en.wav
    timeline.en.json
    mix_report.en.json

  loose/
    dub_voice.en.wav
    preview_mix.en.wav
    timeline.en.json
    mix_report.en.json

  repair_queue.en.json
  task-e-manifest.json
```

兼容策略：

- 保留当前旧路径：
  - `task-e/voice/dub_voice.en.wav`
  - `task-e/voice/preview_mix.en.wav`
- 短期旧路径默认指向 `loose` 版本，保证 Task G 能继续生成完整成片。
- `strict` 版本作为质量门控版，通过 manifest 和前端明确展示。
- manifest 必须标注旧路径当前指向哪个 variant。

短期策略：

```text
legacy path = loose output
Task G default = loose output
strict output = quality-gated review artifact
```

长期策略：

```text
当 strict_coverage 达到可交付阈值后，Task G default 可切换为 strict。
```

建议长期切换阈值：

```text
strict_coverage >= 95%
high_priority_repair_count = 0
manual_blocker_count = 0
```

## 7. Repair Queue 数据结构

```json
{
  "target_lang": "en",
  "source": {
    "task_d_reports": [".../speaker_segments.en.json"],
    "task_e_timeline": ".../strict/timeline.en.json"
  },
  "stats": {
    "total_segments": 192,
    "strict_placed_count": 31,
    "loose_placed_count": 191,
    "repair_count": 168,
    "strict_blocker_count": 161,
    "risk_only_count": 7
  },
  "items": [
    {
      "segment_id": "seg-0084",
      "speaker_id": "spk_0002",
      "source_text": "Thank you",
      "target_text": "Thank you",
      "anchor_start": 242.50,
      "anchor_end": 242.90,
      "source_duration_sec": 0.40,
      "generated_duration_sec": 10.00,
      "audio_path": ".../seg-0084.wav",
      "queue_class": "strict_blocker",
      "strict_blocker": true,
      "failure_reasons": [
        "task_d_overall_failed",
        "duration_failed",
        "intelligibility_failed",
        "too_short_source"
      ],
      "metrics": {
        "duration_ratio": 25.0,
        "speaker_similarity": 0.51,
        "text_similarity": 0.62
      },
      "suggested_actions": [
        "rewrite_shorter",
        "regenerate_with_duration_limit",
        "merge_with_adjacent_segment"
      ],
      "attempts": [],
      "selected_attempt_id": null,
      "priority": "high"
    }
  ]
}
```

## 8. 门控规则

### 8.1 默认 strict 规则

片段进入 strict 必须满足：

```text
audio_path exists
anchor exists
overall_status in ["passed", "review"]
source_duration_sec > 0
generated_duration_sec > 0
```

额外建议：

```text
duration_ratio <= 1.65
duration_ratio >= 0.55
```

这与当前 Task D 的 review 边界一致。

本方案明确采用以下产品决策：

```text
strict 默认允许 passed 和 review 进入。
```

理由：

- 当前自动评估中 `passed=0`，如果只允许 passed，strict 会完全不可听。
- `review` 代表需要人工关注，但不一定不可用。
- 正式交付前仍应由人工审片或更严格 QC 再做最终确认。

### 8.2 Loose 规则

片段进入 loose 只需满足：

```text
audio_path exists
anchor exists
source_duration_sec > 0
generated_duration_sec > 0
```

如果 `overall_status=failed`，保留 notes：

```text
task_d_failed_upstream
```

### 8.3 可配置参数

新增 Task E 配置：

```json
{
  "render_variants": ["strict", "loose"],
  "strict_gate": {
    "allowed_overall_status": ["passed", "review"],
    "allow_failed_with_audio": false,
    "min_duration_ratio": 0.55,
    "max_duration_ratio": 1.65
  },
  "loose_gate": {
    "allow_failed_with_audio": true
  },
  "task_g_audio_variant": "loose"
}
```

`task_g_audio_variant` 短期默认值为 `loose`，以保持成片完整度。后续当 repair queue 闭环成熟后，可以切换为 `strict`。

## 9. Task E 实现改动

当前 Task E 的核心流程是：

```text
load candidates
-> apply fit strategy
-> resolve overlaps
-> render dub voice
-> render preview mix
```

改为：

```text
load candidates
-> split candidates into strict_candidates / loose_candidates
-> render_variant(strict)
-> render_variant(loose)
-> build repair_queue
-> write unified manifest
```

建议新增内部函数：

```python
def _gate_candidates(items, gate_policy) -> tuple[list[TimelineItem], list[RepairItem]]:
    ...

def _render_variant(name, items, request, work_dir) -> RenderVariantResult:
    ...

def _build_repair_queue(all_items, strict_result, loose_result) -> dict:
    ...
```

## 10. Manifest 变化

`task-e-manifest.json` 增加：

```json
{
  "status": "succeeded",
  "quality_status": "needs_repair",
  "variants": {
    "strict": {
      "placed_count": 31,
      "skipped_count": 161,
      "dub_voice": ".../strict/dub_voice.en.wav",
      "preview_mix": ".../strict/preview_mix.en.wav"
    },
    "loose": {
      "placed_count": 191,
      "skipped_count": 1,
      "dub_voice": ".../loose/dub_voice.en.wav",
      "preview_mix": ".../loose/preview_mix.en.wav"
    }
  },
  "repair_queue": ".../repair_queue.en.json"
}
```

`quality_status` 建议取值：

```text
passed
needs_review
needs_repair
failed
```

建议规则：

```text
strict_coverage >= 95% 且 high_priority_repair=0 -> passed
strict_coverage >= 80% -> needs_review
strict_coverage > 0 -> needs_repair
strict_coverage == 0 -> failed
```

## 11. Pipeline 状态策略

Pipeline 的工程状态仍可以是：

```text
succeeded
partial_success
failed
```

但新增内容质量状态：

```text
content_quality_status
```

示例：

```json
{
  "status": "succeeded",
  "content_quality_status": "needs_repair",
  "strict_coverage": 0.161,
  "repair_count": 168,
  "strict_blocker_count": 161,
  "risk_only_count": 7
}
```

这样避免破坏现有任务生命周期，又能明确告诉用户：流程跑完了，但内容不可交付。

Task G 短期状态策略：

```text
Task G 默认消费 loose 版本，保证最终视频完整。
Task G manifest 必须记录 audio_variant="loose"。
如果 strict 存在，也应记录 strict_coverage、repair_count 和 strict_blocker_count，避免把完整成片误判为质量达标。
```

长期状态策略：

```text
当 strict_coverage 达到阈值后，Task G 默认消费 strict。
用户仍可手动选择 loose，用于审听和调试。
```

## 12. 前端展示建议

任务详情页增加三类信息：

1. 产物选择：
   - 正式版 strict
   - 宽松预览 loose

2. 质量摘要：
   - strict 覆盖率
   - failed 片段数量
   - 高优先级返修数量
   - 主要失败原因分布

3. 返修列表：
   - segment_id
   - speaker_id
   - 原文
   - 译文
   - 失败原因
   - 建议动作
   - 播放 loose 音频

## 13. 验收标准

### 13.1 功能验收

- Task E 能生成 strict 和 loose 两套音频
- `overall_status=failed` 默认不进入 strict
- `overall_status=failed` 可以进入 loose
- `repair_queue.en.json` 包含所有 strict 未使用片段
- `task-e-manifest.json` 包含 variants 和 quality_status

### 13.2 回归验收

使用 `task-20260420-170343` 对应输出验证：

```text
strict placed_count 约为 31
loose placed_count 约为 191
repair_count 约为 168
strict_blocker_count 约为 161
risk_only_count 约为 7
pipeline status 保持 succeeded
content_quality_status = needs_repair
```

### 13.3 不破坏现有行为

- 旧 API 仍能拿到可播放音频
- 旧前端不会因为路径变化崩溃
- Task G 可以配置消费 strict 或 loose

## 14. 实施步骤

### Phase 1: Task E 内部双轨渲染

- 增加 gate policy
- 增加 strict/loose variant
- 增加 repair queue
- 更新 manifest

### Phase 2: Pipeline 汇总质量状态

- pipeline manifest 增加 `content_quality_status`
- pipeline report 增加 strict coverage 和 repair summary
- DB task stage 同步 quality fields，可先只从 manifest 读取

### Phase 3: 前端展示

- 任务详情页区分 strict/loose 产物
- 增加 repair queue 摘要
- 支持播放 failed 片段对应 loose 音频

### Phase 4: 接入自动返修

后续 repair queue 可驱动：

- 短句合并
- 配音改写
- 多候选重生成
- 换参考音频
- 换 TTS 模型
- 人工返修 UI

## 15. Repair Queue 驱动的后续完整方案

质量门控只负责识别问题。真正提升配音质量，需要让 `repair_queue` 进入一个可重复执行、可回放、可人工介入的返修闭环。

建议整体流程：

```text
Task D first pass
-> Task E strict/loose render
-> repair_queue
-> repair planner
-> automatic repair attempts
-> candidate evaluation
-> selected repair outputs
-> Task E strict rerender
-> manual review if still unresolved
```

### 15.1 Repair Planner

Repair Planner 根据失败原因决定优先动作。

首发实现需要区分两类队列项：

| 队列类型 | 含义 | 后续处理 |
| --- | --- | --- |
| `strict_blocker` | `overall_status=failed` 或缺少可用音频，正式 strict 产物必须排除 | 自动返修和人工返修的主处理对象 |
| `risk_only` | 当前没有被 strict 规则排除，但存在短句、极端时长比等风险信号 | 预警、抽查或低优先级优化，不应阻塞 strict 产物 |

这个区分很重要。`repair_count` 可以包含风险项，但 `strict_blocker_count` 才代表当前正式产物必须修复的阻断量。

建议规则：

| 失败信号 | 首选动作 | 备选动作 |
| --- | --- | --- |
| `too_short_source` + `duration_failed` | `merge_short_segments` | `rewrite_for_dubbing` |
| `duration_ratio > 1.65` | `rewrite_for_dubbing` | `regenerate_candidates` |
| `duration_ratio < 0.55` | `merge_with_context` | `rewrite_more_complete` |
| `speaker_status=failed` | `switch_reference_audio` | `switch_tts_backend` |
| `intelligibility_status=failed` | `regenerate_candidates` | `rewrite_for_dubbing` |
| 三项都 failed | `switch_tts_backend` | `manual_review` |
| 缺 anchor / 缺音频 | `manual_review` | 上游重跑 |

Planner 输出：

```json
{
  "segment_id": "seg-0084",
  "queue_class": "strict_blocker",
  "strict_blocker": true,
  "planned_actions": [
    {
      "action": "merge_short_segments",
      "priority": 1,
      "reason": "source segment is 0.40s and generated audio is 10.00s"
    },
    {
      "action": "regenerate_candidates",
      "priority": 2,
      "reason": "current TTS output repeated target text"
    }
  ]
}
```

第一阶段已落地为可执行命令：

```bash
python -m translip plan-dub-repair \
  --translation path/to/translation.en.json \
  --profiles path/to/speaker_profiles.json \
  --task-d-report path/to/speaker_segments.en.json \
  --output-dir path/to/repair-plan \
  --target-lang en \
  --glossary config/glossary.example.json
```

该命令不会直接重跑 TTS，而是生成三类计划文件：

```text
repair_queue.en.json
rewrite_plan.en.json
reference_plan.en.json
```

其中 `rewrite_plan` 用于驱动配音改写，`reference_plan` 用于驱动换参考音频，后续多候选重生成再消费这两个计划执行真实 TTS 尝试。

对 `task-20260420-170343` 的 dry run 预期是：`strict_blocker_count` 约为 161，另有少量 `risk_only` 项用于提前提示。

第二阶段已落地为可执行命令：

```bash
python -m translip run-dub-repair \
  --repair-queue path/to/repair_queue.en.json \
  --rewrite-plan path/to/rewrite_plan.en.json \
  --reference-plan path/to/reference_plan.en.json \
  --output-dir path/to/repair-run \
  --segment-id seg-0022 \
  --attempts-per-item 2 \
  --tts-backend moss-tts-nano-onnx
```

该命令会真实生成候选音频、自动评估，并输出：

```text
repair_attempts.en.json
selected_segments.en.json
manual_review.en.json
repair-run-manifest.json
```

`selected_segments.en.json` 是后续 Task E strict 重渲染的覆盖输入；`manual_review.en.json` 是人工返修 UI 的数据入口。

### 15.2 短句合并

#### 15.2.1 适用场景

短句合并主要处理：

- 0.4s - 1.2s 的孤立短句
- 称呼、地名、语气词、重复短语
- TTS 输出存在最小时长，无法压入原窗口的片段

本次问题中，192 段里有 86 段小于 1.2 秒，其中 64 段时长失败。这类问题靠单句重生成很难稳定解决。

#### 15.2.2 合并规则

只允许合并满足以下条件的相邻片段：

```text
same speaker_id
gap <= 0.35s
combined_duration <= 6.0s
combined_text_length <= configurable limit
no hard scene boundary
```

可选放宽规则：

```text
same speaker_cluster
gap <= 0.6s
one segment is filler / greeting / name / place
```

#### 15.2.3 输出结构

合并后不删除原始 segment，而是新增 repair group：

```json
{
  "repair_group_id": "rg-0008-0009",
  "action": "merge_short_segments",
  "source_segment_ids": ["seg-0008", "seg-0009"],
  "speaker_id": "spk_0001",
  "anchor_start": 30.38,
  "anchor_end": 32.78,
  "merged_source_text": "迪拜 在迪拜",
  "merged_target_text": "Dubai. It is in Dubai.",
  "generated_audio_path": ".../repair/rg-0008-0009.wav"
}
```

#### 15.2.4 预期收益

- 降低短句超长导致的 duration failed
- 减少 TTS 对孤立词的发散和重复
- 提升整体时间线连续性

#### 15.2.5 成熟度

技术成熟度：高。

原因：

- 基于已有 segment 时间轴和 speaker_id 即可实现。
- 不依赖新模型。
- 风险主要是合并后语义节奏变差，需要保留 loose 对照和 repair report。

### 15.3 配音改写

#### 15.3.1 适用场景

配音改写主要处理：

- 直译不自然
- 英文过长导致时长溢出
- 专名、人名、地名误译
- TTS 回读相似度低
- 需要更口语化或更短表达

当前 Task C 的 `local-m2m100` 输出存在明显不适合配音的句子，例如：

```text
"在迪拜" -> "in Didi"
"打扰一下你是中国人吗" -> "Do you bother you are Chinese?"
"这儿的天气超霸道的" -> "The weather is superstitious."
```

#### 15.3.2 改写候选类型

每个 repair item 可以生成多种文本候选：

```text
literal: 忠实直译
natural: 自然口语
short: 更短版本，优先贴合时长
lip_friendly: 优先短音节和口型近似
dramatic: 更符合角色表演
```

首发建议只实现：

```text
natural
short
```

#### 15.3.3 改写约束

改写器必须接收：

```json
{
  "source_text": "奶奶您知道哈利法塔吗",
  "current_target_text": "Do you know the Halifa Tower?",
  "source_duration_sec": 2.2,
  "target_lang": "en",
  "speaker_role": "grandmother",
  "glossary": {
    "哈利法塔": "Burj Khalifa",
    "迪拜": "Dubai"
  },
  "max_estimated_tts_duration_sec": 2.2
}
```

输出：

```json
{
  "segment_id": "seg-0002",
  "rewrite_candidates": [
    {
      "variant": "natural",
      "target_text": "Do you know the Burj Khalifa?",
      "estimated_tts_duration_sec": 2.1
    },
    {
      "variant": "short",
      "target_text": "Know the Burj Khalifa?",
      "estimated_tts_duration_sec": 1.6
    }
  ]
}
```

#### 15.3.4 预期收益

- 直接降低 duration failed
- 降低 intelligibility failed
- 提升英语口语自然度
- 修复专名和术语一致性

#### 15.3.5 成熟度

技术成熟度：中高。

原因：

- LLM 改写能力成熟，但需要强约束和术语表。
- 自动时长估计只能粗略预测，最终仍要靠 TTS 后评估闭环。
- 需要人工可审查，避免过度改写原意。

### 15.4 多候选重生成

#### 15.4.1 适用场景

多候选重生成主要处理：

- TTS 偶发重复
- TTS 错读
- TTS 输出过长或过短
- 单次生成音色漂移

当前系统一段通常只保留一个生成结果。对于影视配音，这不够稳定。

#### 15.4.2 候选生成策略

每个 repair item 最多生成 N 个候选：

```text
N 默认 3
高优先级片段 N=5
超过预算则进入 manual_review
```

候选维度：

```text
不同 rewrite 文本
不同 reference clip
不同 TTS 参数
不同 TTS backend
```

候选目录：

```text
task-d/voice/<speaker_id>/repair_candidates/<segment_id>/
  attempt-0001.wav
  attempt-0002.wav
  attempt-0003.wav
  attempts.json
```

#### 15.4.3 候选评分

候选评分建议：

```text
score =
  duration_score * 0.35
  + intelligibility_score * 0.30
  + speaker_score * 0.25
  + stability_score * 0.10
```

首发可以直接复用现有指标：

- `duration_ratio`
- `text_similarity`
- `speaker_similarity`

拒绝规则：

```text
generated_duration_sec <= 0
duration_ratio > 2.5
duration_ratio < 0.35
text_similarity < 0.55
audio clipping severe
```

#### 15.4.4 输出结构

```json
{
  "segment_id": "seg-0155",
  "attempts": [
    {
      "attempt_id": "attempt-0001",
      "target_text": "Go well.",
      "backend": "moss-tts-nano-onnx",
      "reference_path": ".../clip_0002.wav",
      "audio_path": ".../attempt-0001.wav",
      "metrics": {
        "duration_ratio": 30.0,
        "text_similarity": 0.6316,
        "speaker_similarity": 0.2032
      },
      "status": "rejected"
    },
    {
      "attempt_id": "attempt-0002",
      "target_text": "Take care.",
      "backend": "qwen3tts",
      "reference_path": ".../clip_0003.wav",
      "audio_path": ".../attempt-0002.wav",
      "metrics": {
        "duration_ratio": 1.12,
        "text_similarity": 0.94,
        "speaker_similarity": 0.38
      },
      "status": "selected"
    }
  ],
  "selected_attempt_id": "attempt-0002"
}
```

#### 15.4.5 预期收益

- 显著降低 TTS 偶发失败的影响
- 让模型不稳定变成可搜索问题
- 为人工 UI 提供可选择候选

#### 15.4.6 成熟度

技术成熟度：高。

原因：

- 当前已有评估函数。
- 核心是重复调用现有 Task D backend。
- 成本是运行时间和磁盘占用增加。

### 15.5 换参考音频

#### 15.5.1 适用场景

换参考音频主要处理：

- `speaker_status=failed`
- 某个 speaker 大量声纹相似度偏低
- 当前 reference clip 有多人重叠、噪声、情绪过强、文本错误

本次任务中 `spk_0004` 和 `spk_0005` 的 speaker similarity 明显偏低，应优先进入换参考流程。

#### 15.5.2 Reference Pool

Task B 当前已有多个 reference clips。Task D repair 阶段应把它们作为 reference pool，而不是只用首选 clip。

每个 reference clip 需要评分：

```text
single_speaker_score
duration_score
transcript_confidence
rms_stability
noise_risk
emotion_risk
overlap_risk
```

首发可以用已有字段和简单音频统计实现：

```text
duration_score
text presence
rms
known risk flags
```

#### 15.5.3 选择策略

```text
如果当前 reference 的候选平均 speaker_similarity < 0.25：
  尝试下一个 reference clip

如果同一 speaker 的 3 个 reference 都低：
  标记为 speaker_reference_unstable
  建议 switch_tts_backend 或 manual_review
```

#### 15.5.4 预期收益

- 改善声纹失败段
- 降低单个差 reference 对整个角色的影响
- 为角色级 voice profile 打基础

#### 15.5.5 成熟度

技术成熟度：中高。

原因：

- 已有 reference clips。
- 需要更完整的 reference 质量评分。
- 对跨语种声纹保持的改善依赖 TTS backend 能力。

### 15.6 换 TTS 模型

#### 15.6.1 适用场景

换模型主要处理：

- 当前 backend 多次生成后仍 duration failed
- 当前 backend 多次生成后仍 speaker failed
- 当前 backend 对某类文本稳定发散
- 某 speaker 在当前 backend 下整体声纹失败

#### 15.6.2 候选模型策略

建议支持三层模型策略：

```text
default_backend: 当前默认后端，用于首轮全量生成
repair_backend: 失败片段返修用后端
benchmark_backend: 离线对比评估后端
```

可选 backend：

```text
moss-tts-nano-onnx
qwen3tts
cosyvoice
external-elevenlabs
```

首发建议：

```text
default_backend = moss-tts-nano-onnx 或 qwen3tts
repair_backend = qwen3tts
benchmark_backend = qwen3tts / cosyvoice / external-elevenlabs
```

#### 15.6.3 模型选择规则

模型切换不应主观决定，应通过同一批 repair queue 做 benchmark。

评估维度：

```text
strict_pass_or_review_rate
duration_failed_rate
speaker_failed_rate
intelligibility_failed_rate
平均生成耗时
显存/内存占用
失败异常率
```

最低验收标准：

```text
新 backend 必须在同一 repair set 上显著降低至少一个主要失败维度，且不能让其他维度大幅恶化。
```

#### 15.6.4 预期收益

- 对声纹保持和自然度可能有显著改善
- 对当前 backend 的重复、发散问题形成兜底
- 为影视级质量提供更强生成底座

#### 15.6.5 成熟度

技术成熟度：中。

原因：

- 接口层已有 backend abstraction。
- 新模型依赖、资源占用、授权、推理稳定性都需要单独验证。
- 换模型不能替代配音改写和短句处理。

### 15.7 人工返修 UI

#### 15.7.1 适用场景

人工返修 UI 是影视配音从 demo 进入生产的关键能力。自动返修无法解决所有问题，尤其是：

- 角色语气不对
- 翻译含义偏差
- 专名/梗/文化语境错误
- 自动候选都不好听
- 需要导演或人工审片判断

#### 15.7.2 页面能力

建议新增 Dubbing Review 页面，围绕 repair queue 展示：

```text
video preview
source segment text
target text
strict audio
loose audio
candidate attempts
failure reasons
metrics
suggested actions
manual decision
```

核心操作：

- 播放原视频片段
- 播放 loose 音频
- 播放候选音频
- 编辑 target_text
- 单段重生成
- 选择候选
- 标记 accepted / rejected / needs rewrite
- 合并相邻 segment
- 拆分错误 segment
- 指派 speaker
- 导出人工审校后的 repair decisions

#### 15.7.3 人工决策文件

```json
{
  "review_session_id": "review-20260421-001",
  "items": [
    {
      "segment_id": "seg-0008",
      "decision": "accept_candidate",
      "selected_attempt_id": "attempt-0003",
      "edited_target_text": "Dubai.",
      "reviewer_note": "short enough and understandable"
    },
    {
      "segment_id": "seg-0084",
      "decision": "merge_with_next",
      "merge_with": ["seg-0085"],
      "edited_target_text": "Thank you. Please rest and take a bath."
    }
  ]
}
```

#### 15.7.4 预期收益

- 让系统具备真实制作流程能力
- 让自动生成不可控问题可被人工修正
- 形成可审计、可复跑的人工决策记录

#### 15.7.5 成熟度

技术成熟度：中。

原因：

- 数据结构清晰，前端实现可控。
- 需要和音频预览、视频片段定位、单段重跑 API 配合。
- 产品交互复杂度高于后端 JSON 改造。

### 15.8 Repair Attempt 生命周期

每个 repair item 建议经历以下状态：

```text
queued
planned
auto_attempted
candidate_selected
strict_accepted
manual_required
manual_accepted
unresolved
```

状态含义：

| 状态 | 含义 |
| --- | --- |
| `queued` | 已进入 repair queue，尚未处理 |
| `planned` | 已生成修复计划 |
| `auto_attempted` | 已尝试自动修复 |
| `candidate_selected` | 自动选择出候选 |
| `strict_accepted` | 候选通过 strict gate |
| `manual_required` | 自动修复失败，需要人工 |
| `manual_accepted` | 人工已确认可用 |
| `unresolved` | 暂无可用修复 |

### 15.9 Repair 后的重渲染

自动或人工修复后，不应重跑全链路，而应支持：

```text
repair outputs
-> update selected Task D report
-> rerun Task E strict variant
-> optionally rerun Task G
```

建议新增中间文件：

```text
task-d/voice/selected_segments.en.json
```

它表示当前每个 segment 最终选用哪个音频：

```json
{
  "segments": [
    {
      "segment_id": "seg-0008",
      "speaker_id": "spk_0001",
      "selected_audio_path": ".../repair_candidates/seg-0008/attempt-0003.wav",
      "selected_source": "repair_candidate",
      "selected_attempt_id": "attempt-0003",
      "overall_status": "review"
    }
  ]
}
```

Task E strict 优先消费 `selected_segments.en.json`，没有 selected override 时再消费原始 `speaker_segments.en.json`。

已落地 CLI：

```bash
python -m translip render-dub \
  --quality-gate strict \
  --selected-segments path/to/selected_segments.en.json \
  ...
```

`--quality-gate strict` 会过滤 `overall_status=failed` 的原始 Task D 片段；如果某片段在 `selected_segments` 中已有通过自动返修的候选，则使用修复候选进入 strict timeline。

在 `task-20260420-170343` 对应产物上的验证结果：

```text
未接入 selected repair:
strict placed_count = 31
skipped_quality_gate = 161

接入 seg-0022 repair selected:
strict placed_count = 32
skipped_quality_gate = 160
seg-0022: "My eyes are good too." -> "Great eyes."
seg-0022 overall_status: failed -> passed
```

### 15.10 Repair 优先级

建议优先修这些片段：

```text
P0: 明显灾难片段，例如 1s 生成 30s、回读完全错误
P1: 主角/高频 speaker 的失败片段
P1: 影响剧情理解的失败片段
P2: 背景路人、短语气词、可接受缺口
P3: 片尾歌曲、非对白、可跳过内容
```

优先级评分：

```text
priority_score =
  duration_severity
  + intelligibility_severity
  + speaker_importance
  + timeline_importance
  + user_marked_importance
```

### 15.11 Repair 闭环验收指标

每次 repair run 输出：

```text
repair_input_count
auto_attempted_count
auto_resolved_count
manual_required_count
strict_coverage_before
strict_coverage_after
duration_failed_before/after
speaker_failed_before/after
intelligibility_failed_before/after
```

对 `task-20260420-170343`，第一阶段可设目标：

```text
strict_coverage: 31/192 -> 70/192
duration_failed: 102 -> 70 以下
灾难性超长片段: 清零
```

第二阶段目标：

```text
strict_coverage >= 80%
高优先级 repair item = 0
Task G 可选择 strict 作为正式交付音频
```

## 16. 分阶段实施路线

### Phase 1: 质量门控和双轨产物

目标：

- 让系统区分 strict 和 loose。
- 让 failed 片段进入 repair queue。
- Task G 短期默认继续使用 loose，保持完整成片。

交付：

- strict/loose Task E outputs
- repair_queue.en.json
- task-e-manifest variants
- Task G `audio_variant="loose"` manifest 字段

### Phase 2: 自动返修基础能力

目标：

- 对 repair queue 做自动 planner。
- 支持短句合并和多候选重生成。

交付：

- repair planner
- merge_short_segments
- regenerate_candidates
- selected repair attempts
- strict rerender

### Phase 3: 配音改写与参考音频切换

目标：

- 对时长和可懂度失败片段做文本层修复。
- 对声纹失败片段做 reference-level 修复。

交付：

- rewrite_for_dubbing
- glossary-aware rewrite
- reference pool scoring
- switch_reference_audio

### Phase 4: TTS 模型 benchmark 和 repair backend

目标：

- 通过同一 repair set 选择更适合影视配音的 backend。
- 不主观换模型，必须用指标验证。

交付：

- backend benchmark runner
- repair_backend config
- qwen3tts / cosyvoice / external backend 对比报告

### Phase 5: 人工返修 UI

目标：

- 让人工能审片、改词、重生成、选候选。
- 形成可复跑的人工决策文件。

交付：

- Dubbing Review 页面
- candidate playback
- manual repair decisions
- single-segment rerun API

## 17. 技术成熟度评价

| 模块 | 成熟度 | 说明 |
| --- | --- | --- |
| strict/loose 双轨渲染 | 高 | 基于现有 Task E 渲染逻辑复制一层 variant |
| repair queue JSON | 高 | 纯数据结构和统计汇总 |
| quality_status | 高 | 基于已有 Task D/E 指标 |
| 短句合并 | 高 | 基于现有时间轴和 speaker_id，可先规则化实现 |
| 多候选重生成 | 高 | 基于现有 Task D backend 和评估函数 |
| 配音改写 | 中高 | LLM 能力成熟，但需要时长约束、术语表和人工审查 |
| 换参考音频 | 中高 | 需要 reference pool 评分，收益依赖参考音频质量 |
| 换 TTS 模型 | 中 | 需要依赖集成、资源评估和 benchmark |
| 前端展示 | 中 | 需要 UI 增量开发 |
| 人工返修 UI | 中 | 交互复杂，需要视频/音频预览和单段重跑 API |
| 自动返修闭环 | 中 | 需要 planner、attempt 管理、selected output 和重渲染 |
| 提升最终配音质量 | 间接 | 本方案本身不修音频，但为修音频建立闭环 |

## 18. 主要风险

1. strict 版本可能出现大量静音缺口

   这是预期行为，代表当前系统真实可交付程度不足。

2. 用户可能误以为 strict 变差

   需要在 UI 上明确：strict 是正式质量门控版，loose 是调试预览版。

3. Task G 默认消费哪个版本需要慎重

   本方案明确短期默认消费 loose，保证成片完整；strict 用于质量评估和返修目标。

4. 如果 repair queue 不继续被使用，收益有限

   本方案必须作为自动返修和人工返修的前置步骤。

5. 自动返修可能引入语义漂移

   配音改写必须保留 source text、current target text、rewrite candidate 和人工可审查记录。

6. 多候选重生成会增加成本

   需要限制每段最大 attempts，并按 priority 分配预算。

7. 换模型会引入工程不确定性

   新 backend 必须先通过 repair set benchmark，不能直接替换默认生产路径。

## 19. 已确认决策

### 19.1 Strict 默认门控

已确认：

```text
strict 默认允许 passed 和 review 进入。
failed 默认不进入 strict。
```

原因：

- 只允许 `passed` 会导致当前任务 strict 版本为空。
- `review` 是可审片状态，不等于不可用。
- 正式交付前仍需要人工或更严格 QC。

### 19.2 Task G 默认消费策略

已确认：

```text
短期 Task G 默认消费 loose，保持成片完整度。
```

要求：

- Task G manifest 必须记录 `audio_variant="loose"`。
- Task G report 必须透出 `strict_coverage`、`repair_count` 和 `strict_blocker_count`。
- UI 必须说明该最终视频是 loose 成片，不代表质量门控已通过。

长期切换条件：

```text
strict_coverage >= 95%
high_priority_repair_count = 0
manual_blocker_count = 0
```

满足后可把 Task G 默认消费策略切换为 strict。

## 20. 最终建议

先实现质量门控和双轨产物，但不要把它宣传成“质量提升”。它的定位是：

- 建立正式交付门槛
- 暴露真实问题
- 形成可执行返修列表
- 为后续自动重试和人工返修提供入口

然后按优先级实现 repair queue 驱动的修复闭环：

```text
Phase 1: strict/loose + repair_queue
Phase 2: 短句合并 + 多候选重生成
Phase 3: 配音改写 + 换参考音频
Phase 4: TTS 模型 benchmark + repair backend
Phase 5: 人工返修 UI
```

这条路线的核心判断是：

```text
质量门控负责识别和隔离问题；
repair queue 负责驱动自动和人工修复；
Task G 短期保留 loose 成片完整度；
strict 成为系统真实质量进展的度量。
```
