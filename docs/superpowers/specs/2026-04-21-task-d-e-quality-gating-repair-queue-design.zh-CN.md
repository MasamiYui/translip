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

## 3. 非目标

本方案不直接解决以下问题：

- 不在本阶段实现新 TTS 模型接入
- 不在本阶段实现自动配音改写
- 不在本阶段实现人工返修 UI
- 不在本阶段实现 lip-sync
- 不在本阶段重新设计 Task A/B/C/D 的全链路协议

本方案的定位是质量闸门和返修数据结构。

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
- 旧路径默认指向 `strict` 版本，或通过配置选择。
- 短期也可以先让旧路径继续生成 loose 版本，避免影响现有前端；但 manifest 必须明确标注。

推荐最终策略：

```text
legacy path = strict output
debug/preview path = loose output
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
    "repair_count": 161
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
  }
}
```

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
  "repair_count": 161
}
```

这样避免破坏现有任务生命周期，又能明确告诉用户：流程跑完了，但内容不可交付。

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
repair_count 约为 161
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

## 15. 技术成熟度评价

| 模块 | 成熟度 | 说明 |
| --- | --- | --- |
| strict/loose 双轨渲染 | 高 | 基于现有 Task E 渲染逻辑复制一层 variant |
| repair queue JSON | 高 | 纯数据结构和统计汇总 |
| quality_status | 高 | 基于已有 Task D/E 指标 |
| 前端展示 | 中 | 需要 UI 增量开发 |
| 自动返修 | 中 | 依赖后续改写、重生成和模型策略 |
| 提升最终配音质量 | 间接 | 本方案本身不修音频，但为修音频建立闭环 |

## 16. 主要风险

1. strict 版本可能出现大量静音缺口

   这是预期行为，代表当前系统真实可交付程度不足。

2. 用户可能误以为 strict 变差

   需要在 UI 上明确：strict 是正式质量门控版，loose 是调试预览版。

3. Task G 默认消费哪个版本需要慎重

   建议产品默认 strict，开发调试可选 loose。

4. 如果 repair queue 不继续被使用，收益有限

   本方案必须作为自动返修和人工返修的前置步骤。

## 17. 最终建议

先实现本方案，但不要把它宣传成“质量提升”。它的定位是：

- 建立正式交付门槛
- 暴露真实问题
- 形成可执行返修列表
- 为后续自动重试和人工返修提供入口

它是后续解决问题的地基，不是问题本身的最终答案。

## 18. 待讨论决策点

1. `strict` 默认允许 `review` 进入，还是只允许 `passed`？
2. `Task G` 默认消费 `strict`，还是短期继续消费 `loose` 以保持成片完整度？
