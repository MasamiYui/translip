# 说话人识别、人工审查与 Diarization 优化完整方案

## 1. 背景

当前配音链路已经具备：

- Task A：语音转写并输出 `speaker_label`
- ASR/OCR 校正：修正台词文本
- Task B：基于 `speaker_label` 注册 speaker profile 和 reference clip
- Task C：翻译
- Task D：按 speaker 合成配音
- Task E/G：混音和交付

但在影视短剧场景中，`speaker_label` 的错误会造成比文字识别错误更严重的连锁影响：

```text
speaker 分错
-> Task B 生成错误 speaker profile
-> reference clip 混入错误说话人
-> Task D 用错误音色合成台词
-> 短句合并和 Voice Bank 也会基于错误 speaker 做决策
```

因此，说话人识别质量必须作为配音质量闭环的前置条件。本文给出一个可落地的完整方案：先通过诊断和人工审查把当前链路救起来，再逐步增强自动 diarization 能力。

## 2. 当前任务诊断

样本任务：

```text
task_id = task-20260421-075513
task_root = ~/.cache/translip/output-pipeline/task-20260421-075513
```

### 2.1 Task A 说话人分布

Task A / ASR-OCR correction 后共有 175 段，当前被分成 8 个 speaker：

| speaker_label | segment_count | total_speech_sec | avg_duration_sec | `<1.2s` 短句数 |
| --- | ---: | ---: | ---: | ---: |
| `SPEAKER_01` | 65 | 94.83 | 1.46 | 25 |
| `SPEAKER_00` | 50 | 95.08 | 1.90 | 15 |
| `SPEAKER_03` | 43 | 72.40 | 1.68 | 12 |
| `SPEAKER_02` | 8 | 101.38 | 12.67 | 1 |
| `SPEAKER_05` | 6 | 8.95 | 1.49 | 3 |
| `SPEAKER_04` | 1 | 1.00 | 1.00 | 1 |
| `SPEAKER_06` | 1 | 1.20 | 1.20 | 0 |
| `SPEAKER_07` | 1 | 4.81 | 4.81 | 0 |

明显异常：

- `SPEAKER_02` 只有 8 段，却占 101.38 秒，平均单段 12.67 秒。
- `SPEAKER_04` 和 `SPEAKER_06` 只有 1 秒左右，不适合作为独立可克隆角色。
- `SPEAKER_07` 只有一段 4.81 秒，文本是重复短语，不能稳定代表角色音色。

### 2.2 长段异常

当前有多段“时长很长但文本很短”的异常片段：

| segment_id | speaker | start | end | duration | text |
| --- | --- | ---: | ---: | ---: | --- |
| `seg-0010` | `SPEAKER_02` | 38.49 | 73.56 | 35.07s | 三分钟之后停车场见 |
| `seg-0068` | `SPEAKER_02` | 195.64 | 216.47 | 20.83s | 您好 |
| `seg-0075` | `SPEAKER_02` | 225.42 | 236.94 | 11.52s | 先等一下给他这个 |
| `seg-0132` | `SPEAKER_02` | 395.00 | 404.74 | 9.74s | 皇爷 |

这些片段不应该被直接用于 speaker embedding 和 reference clip，因为其中很可能包含：

- 长静音
- 背景声
- 非台词声音
- ASR 时间戳过宽
- 一个 segment 内含多个真实说话人

### 2.3 Speaker run 异常

当前 speaker run 中存在明显风险：

```text
seg-0059 SPEAKER_04 1.00s  那是
seg-0141 SPEAKER_06 1.20s  那你妈有没有告诉你
seg-0175 SPEAKER_07 4.81s  懂你 懂你 懂你
```

这些 run 不应该默认成为独立 speaker profile，更不应该自动进入音色克隆。

### 2.4 代码层面根因

当前 Task A 流程是：

```text
faster-whisper ASR segments
-> assign_speaker_labels()
-> 输出 segments.zh.json
```

关键代码路径：

```text
src/translip/transcription/runner.py
src/translip/transcription/speaker.py
```

当前 speaker 逻辑的核心问题：

1. 先由 ASR 切 segment，再做 speaker clustering。
2. `_build_embedding_groups()` 会把相邻 ASR segment 合成 embedding group。
3. 默认只要 gap `<= 0.45s`、总时长 `<= 8.0s`、最多 5 段，就会合成一个 embedding group。
4. 在影视快节奏对话中，相邻短句很可能来自不同人物。
5. 一旦 group 混入 A/B 两个人，embedding 就会变成污染样本。
6. Task B 把 Task A 的 label 当真，不再二次纠错。

结论：当前不是单纯“聚类阈值调一下”的问题，而是缺少 speaker diagnostics、人工 review、二次纠错和 diarization-first 能力。

## 3. 目标

### 3.1 第一阶段目标

在不引入大型新模型的情况下，先建立可落地的 speaker 纠错闭环：

1. 自动输出 speaker 诊断报告。
2. 识别高风险 speaker、segment、speaker run。
3. 在任务详情页提供“说话人审查”入口。
4. 支持人工修改 segment/run 的 speaker。
5. 支持合并错误 speaker。
6. 支持标记“不参与音色克隆”。
7. 输出 `segments.zh.speaker-corrected.json`。
8. Task B/C/D 优先消费 speaker-corrected 文件。

### 3.2 第二阶段目标

增强自动纠错能力：

1. 对 segment embedding 做二次 prototype relabel。
2. 自动合并明显的短孤岛 speaker。
3. 自动过滤异常 reference clip。
4. 对长时间戳短文本片段做 VAD 级重切。
5. 对 speaker profile 加质量门控。

### 3.3 第三阶段目标

引入可选高质量 diarization-first 链路：

```text
voice track
-> diarization backend
-> speaker turns
-> ASR word timestamps
-> word-to-speaker alignment
-> speaker-aware segments
```

该阶段用于高质量影视配音，不直接替换默认链路，先通过 benchmark 验证。

## 4. 非目标

第一阶段不做以下事情：

- 不要求一次性替换 faster-whisper。
- 不强制接入 pyannote 或 NeMo。
- 不实现复杂音频剪辑时间线。
- 不让人工逐字修 ASR。
- 不让人工逐段处理全部 175 段。
- 不直接重做 Task D 音色克隆。

第一阶段只解决一个核心问题：

```text
让 Task B 之前的 speaker attribution 变得可审查、可纠错、可追溯。
```

## 5. 总体架构

新增一个逻辑阶段：

```text
Task A
-> ASR/OCR correction
-> Speaker Review
-> Task B
-> Task C
-> Task D
-> Task E/G
```

实际落地时可以不马上改 DAG 节点，而是在 `effective_task_a_segments_path()` 中增加优先级：

```text
1. asr-ocr-correct/voice/segments.zh.speaker-corrected.json
2. asr-ocr-correct/voice/segments.zh.corrected.json
3. task-a/voice/segments.zh.json
```

这样能最小化改动，先让后续 Task B/C/D 使用人工 speaker 修正版。

## 6. 新增产物

### 6.1 Speaker diagnostics

路径：

```text
asr-ocr-correct/voice/speaker_diagnostics.zh.json
```

用途：

- 自动识别 speaker 异常。
- 给前端 UI 提供审查列表。
- 给 pipeline report 提供质量状态。

示例：

```json
{
  "task_id": "task-20260421-075513",
  "target_lang": "zh",
  "source_segments": "asr-ocr-correct/voice/segments.zh.corrected.json",
  "stats": {
    "segment_count": 175,
    "speaker_count": 8,
    "high_risk_speaker_count": 4,
    "high_risk_segment_count": 9,
    "review_run_count": 12
  },
  "speakers": [
    {
      "speaker_label": "SPEAKER_02",
      "segment_count": 8,
      "total_speech_sec": 101.38,
      "avg_segment_duration_sec": 12.67,
      "risk_level": "high",
      "risk_flags": [
        "long_duration_low_segment_count",
        "long_segment_text_density_low",
        "reference_contamination_risk"
      ],
      "recommended_actions": [
        "review_runs",
        "exclude_long_anomaly_from_reference",
        "consider_merge_or_relabel"
      ]
    }
  ],
  "segments": [
    {
      "segment_id": "seg-0010",
      "speaker_label": "SPEAKER_02",
      "start": 38.49,
      "end": 73.56,
      "duration_sec": 35.07,
      "text": "三分钟之后停车场见",
      "risk_level": "high",
      "risk_flags": [
        "long_segment",
        "low_text_density",
        "bad_reference_candidate"
      ],
      "recommended_actions": [
        "review_speaker",
        "vad_resplit",
        "exclude_from_reference"
      ]
    }
  ],
  "runs": []
}
```

### 6.2 Speaker review plan

路径：

```text
asr-ocr-correct/voice/speaker_review_plan.zh.json
```

用途：

- 把 175 个 segment 压缩成较少的人类决策点。
- 按 speaker run、异常 segment、异常 speaker 组织 UI。

示例：

```json
{
  "review_items": [
    {
      "review_item_id": "run-0059-0059",
      "item_type": "speaker_run",
      "speaker_label": "SPEAKER_04",
      "segment_ids": ["seg-0059"],
      "start": 179.37,
      "end": 180.37,
      "duration_sec": 1.0,
      "text_preview": "那是",
      "risk_level": "high",
      "risk_flags": ["single_segment_speaker", "too_short_for_profile"],
      "suggested_decisions": [
        {
          "decision": "merge_to_neighbor_speaker",
          "target_speaker_label": "SPEAKER_03",
          "reason": "short run between related dialogue"
        },
        {
          "decision": "mark_non_cloneable",
          "reason": "insufficient speech sample"
        }
      ]
    }
  ]
}
```

### 6.3 Manual speaker decisions

路径：

```text
asr-ocr-correct/voice/manual_speaker_decisions.zh.json
```

用途：

- 保存人工在 UI 上做出的 speaker 决策。
- 保留审查历史和可追溯原因。

示例：

```json
{
  "task_id": "task-20260421-075513",
  "target_lang": "zh",
  "updated_at": "2026-04-21T18:00:00+08:00",
  "decisions": [
    {
      "decision_id": "dec-0001",
      "item_type": "speaker_run",
      "item_id": "run-0059-0059",
      "decision": "relabel",
      "source_speaker_label": "SPEAKER_04",
      "target_speaker_label": "SPEAKER_03",
      "segment_ids": ["seg-0059"],
      "reason": "短孤岛，听感属于前后同一角色",
      "updated_at": "2026-04-21T18:00:00+08:00"
    },
    {
      "decision_id": "dec-0002",
      "item_type": "speaker_profile",
      "item_id": "SPEAKER_07",
      "decision": "mark_non_cloneable",
      "source_speaker_label": "SPEAKER_07",
      "reason": "样本只有一段，且文本为重复短语",
      "updated_at": "2026-04-21T18:01:00+08:00"
    }
  ]
}
```

### 6.4 Speaker-corrected segments

路径：

```text
asr-ocr-correct/voice/segments.zh.speaker-corrected.json
asr-ocr-correct/voice/segments.zh.speaker-corrected.srt
```

用途：

- 作为 Task B/C/D 的新输入。
- 保留每个 segment 的原始 speaker label 和修正后 speaker label。

示例 segment：

```json
{
  "id": "seg-0059",
  "start": 179.37,
  "end": 180.37,
  "duration": 1.0,
  "speaker_label": "SPEAKER_03",
  "original_speaker_label": "SPEAKER_04",
  "speaker_correction": {
    "source": "manual_speaker_decision",
    "decision_id": "dec-0001",
    "confidence": "manual"
  },
  "text": "那是",
  "language": "zh"
}
```

### 6.5 Speaker review manifest

路径：

```text
asr-ocr-correct/voice/speaker-review-manifest.json
```

内容：

```json
{
  "status": "succeeded",
  "source_segments": "segments.zh.corrected.json",
  "output_segments": "segments.zh.speaker-corrected.json",
  "diagnostics": "speaker_diagnostics.zh.json",
  "review_plan": "speaker_review_plan.zh.json",
  "manual_decisions": "manual_speaker_decisions.zh.json",
  "stats": {
    "segment_count": 175,
    "changed_segment_count": 12,
    "merged_speaker_count": 2,
    "non_cloneable_speaker_count": 3
  }
}
```

## 7. 自动诊断规则

### 7.1 Speaker 级风险

| 规则 | 条件 | 风险 |
| --- | --- | --- |
| `single_segment_speaker` | `segment_count = 1` | 高 |
| `too_short_for_profile` | `total_speech_sec < 3.0` | 高 |
| `low_sample_speaker` | `segment_count <= 2` 或 `total_speech_sec < 6.0` | 中高 |
| `long_duration_low_segment_count` | `total_speech_sec > 30` 且 `segment_count < 10` | 高 |
| `short_segment_heavy` | 短句占比 `> 40%` | 中 |
| `reference_contamination_risk` | 主要 reference 来自长异常 segment 或短孤岛 | 高 |

本任务触发示例：

```text
SPEAKER_02 -> long_duration_low_segment_count, reference_contamination_risk
SPEAKER_04 -> single_segment_speaker, too_short_for_profile
SPEAKER_06 -> single_segment_speaker, too_short_for_profile
SPEAKER_07 -> single_segment_speaker, low_sample_speaker
```

### 7.2 Segment 级风险

| 规则 | 条件 | 风险 |
| --- | --- | --- |
| `long_segment` | `duration_sec > 8.0` | 中 |
| `very_long_segment` | `duration_sec > 15.0` | 高 |
| `low_text_density` | `duration_sec / char_count` 过高 | 高 |
| `too_short_for_embedding` | `duration_sec < 1.0` | 中 |
| `bad_reference_candidate` | 长异常、短孤岛、静音风险 | 高 |
| `speaker_boundary_risk` | 与前后 speaker 切换且 gap 很小 | 中 |

建议阈值：

```toml
[speaker_diagnostics.segment]
long_segment_sec = 8.0
very_long_segment_sec = 15.0
min_embedding_sec = 1.0
max_sec_per_char = 1.2
max_sec_per_word = 2.5
```

### 7.3 Run 级风险

speaker run 是连续同 speaker 的片段集合。审查 UI 应优先展示 run，而不是逐段展示。

| 规则 | 条件 | 风险 |
| --- | --- | --- |
| `isolated_short_run` | run `<= 2` 段且总时长 `< 3s` | 高 |
| `sandwiched_run` | 前后 speaker 相同，中间 run 很短 | 高 |
| `rapid_turn_boundary` | speaker 切换 gap `< 0.2s` | 中 |
| `long_run_maybe_monologue` | run 很长且单一 speaker | 低或中，需要结合剧情 |
| `mixed_dialogue_risk` | run 内存在问答、称呼变化、语言切换 | 中 |

### 7.4 Reference 候选风险

Task B 生成 reference clip 前必须过滤：

```text
bad_reference_candidate
single_segment_speaker
too_short_for_profile
very_long_segment
low_text_density
speaker_boundary_risk
```

规则：

```text
高风险 segment 不允许进入 reference clip。
高风险 speaker 默认 non_cloneable，除非人工确认。
长异常 segment 需要 VAD 清洗后才能作为 reference 候选。
```

## 8. 人工审查 UI 方案

### 8.1 入口

在任务详情页底部操作栏新增“说话人审查”按钮，打开右侧抽屉。

原因：

- speaker 纠错是音色审查和短句合并的前置条件。
- UI 风格沿用任务详情页现有抽屉（WorkflowNodeDrawer 等）。
- 用户审查路径从“先分人，再选音色，再修配音”自然推进。

### 8.2 UI 视觉约束

必须沿用当前 UI 设计语言：

- 白底
- slate 色系
- 细边框
- 8px 或 12px 小圆角
- 蓝色只用于主操作和选中态
- amber/rose 只用于风险状态
- 不使用大面积渐变
- 不使用卡片套卡片
- 不做复杂波形编辑器

### 8.3 说话人总览

顶部展示 speaker 统计：

```text
speaker 总数
高风险 speaker 数
需要审查 run 数
已决策数
修正 segment 数
```

示例：

```text
说话人 8
高风险 4
审查项 12
已决策 0
```

### 8.4 Speaker 列表

每个 speaker 展示：

```text
SPEAKER_02
segment_count: 8
total_speech_sec: 101.38s
avg_segment_duration: 12.67s
risk: high
flags: long_duration_low_segment_count, reference_contamination_risk
```

操作：

```text
合并到...
标记不参与克隆
标记为真实独立角色
查看相关 run
查看 reference 风险
```

### 8.5 Speaker run 审查

UI 应展示连续台词块，而不是全量 segment 表。

示例：

```text
run-0059-0059
当前 speaker: SPEAKER_04
时间: 179.37s - 180.37s
时长: 1.00s
文本: 那是
风险: single_segment_speaker, too_short_for_profile
```

操作按钮：

```text
改为上一个 speaker
改为下一个 speaker
改为指定 speaker
保持独立 speaker
标记不参与克隆
需要拆分
```

对 `sandwiched_run`，可以给快捷操作：

```text
合并到前后同 speaker
```

### 8.6 Segment Inspector

点开 run 后展示 segment 详情：

```text
segment_id
start/end/duration
当前 speaker
原始 speaker
文本
风险标记
前后 segment
```

播放能力：

```text
播放当前 segment 音频
播放前后 2 秒上下文
播放整个 run
```

第一阶段可以先只用 artifact audio 或后端临时裁剪接口，后续再加波形。

### 8.7 决策写入

每个操作都写入 `manual_speaker_decisions.zh.json`。

按钮对应决策：

| UI 操作 | decision |
| --- | --- |
| 改为上一个 speaker | `relabel_to_previous_speaker` |
| 改为下一个 speaker | `relabel_to_next_speaker` |
| 改为指定 speaker | `relabel` |
| 合并 speaker | `merge_speaker` |
| 保持独立 | `keep_independent` |
| 不参与克隆 | `mark_non_cloneable` |
| 需要拆分 | `needs_split` |
| 排除 reference | `exclude_from_reference` |

## 9. 用户工作流

用户不应该逐段检查 175 段。推荐审查流程：

### Step 1: 先处理高风险 speaker

优先看：

```text
SPEAKER_02
SPEAKER_04
SPEAKER_06
SPEAKER_07
```

对每个 speaker 决定：

```text
是真实独立角色
合并到某个已有 speaker
不参与音色克隆
需要进一步拆分
```

### Step 2: 处理短孤岛 run

系统只展示高风险 run，例如：

```text
1 秒短句
夹在两个同 speaker 中间的孤岛
前后 speaker 切换非常密集的片段
```

用户只要听上下文，然后选择：

```text
改为前一个 speaker
改为后一个 speaker
保持不变
```

### Step 3: 处理 reference 风险

对每个 speaker，UI 标记哪些 segment/reference 不应参与音色克隆。

用户只做：

```text
允许作为 reference
排除 reference
不确定，进入 review
```

### Step 4: 应用修正

点击：

```text
应用 speaker 修正
```

系统输出：

```text
segments.zh.speaker-corrected.json
speaker-review-manifest.json
```

### Step 5: 从 Task B 重跑

speaker 修正后，需要从 Task B 开始重跑：

```text
Task B speaker profiles
Task C translation
Task D dubbing
Task E mixing
Task G delivery
```

Task C 的文本可复用缓存，但 speaker_id 映射变了，因此至少 Task B/D/E 需要重跑。

## 10. 后端接口设计

### 10.1 获取 speaker review 数据

```http
GET /api/tasks/{task_id}/speaker-review
```

返回：

```json
{
  "task_id": "task-20260421-075513",
  "target_lang": "zh",
  "status": "available",
  "summary": {
    "speaker_count": 8,
    "high_risk_speaker_count": 4,
    "review_item_count": 12,
    "decision_count": 0
  },
  "speakers": [],
  "runs": [],
  "segments": [],
  "decisions": []
}
```

### 10.2 保存 speaker 决策

```http
POST /api/tasks/{task_id}/speaker-review/decisions
```

请求：

```json
{
  "item_type": "speaker_run",
  "item_id": "run-0059-0059",
  "decision": "relabel",
  "source_speaker_label": "SPEAKER_04",
  "target_speaker_label": "SPEAKER_03",
  "segment_ids": ["seg-0059"],
  "reason": "听感属于前后同一角色"
}
```

### 10.3 应用 speaker 决策

```http
POST /api/tasks/{task_id}/speaker-review/apply
```

行为：

```text
读取 source segments
读取 manual_speaker_decisions.zh.json
应用 relabel / merge / non_cloneable
输出 segments.zh.speaker-corrected.json
输出 speaker-review-manifest.json
```

### 10.4 重跑后续任务

复用现有 rerun：

```http
POST /api/tasks/{task_id}/rerun
{
  "from_stage": "task-b"
}
```

需要注意：如果 rerun 创建新 task，新 task 应继承 `segments.zh.speaker-corrected.json` 或共享 output_root。更稳妥的方式是先支持当前任务内局部重跑。

## 11. CLI 设计

### 11.1 生成诊断

```bash
python -m translip analyze-speakers \
  --segments asr-ocr-correct/voice/segments.zh.corrected.json \
  --audio stage1/我在迪拜等你/voice.mp3 \
  --output-dir asr-ocr-correct/voice \
  --target-lang zh
```

输出：

```text
speaker_diagnostics.zh.json
speaker_review_plan.zh.json
```

### 11.2 应用人工决策

```bash
python -m translip apply-speaker-decisions \
  --segments asr-ocr-correct/voice/segments.zh.corrected.json \
  --decisions asr-ocr-correct/voice/manual_speaker_decisions.zh.json \
  --output asr-ocr-correct/voice/segments.zh.speaker-corrected.json \
  --srt-output asr-ocr-correct/voice/segments.zh.speaker-corrected.srt
```

### 11.3 自动二次纠错

第二阶段新增：

```bash
python -m translip refine-speaker-labels \
  --segments asr-ocr-correct/voice/segments.zh.corrected.json \
  --profiles task-b/voice/speaker_profiles.json \
  --audio stage1/我在迪拜等你/voice.mp3 \
  --output asr-ocr-correct/voice/segments.zh.auto-speaker-refined.json
```

## 12. Pipeline 接入

### 12.1 路径优先级

修改 `effective_task_a_segments_path()`：

```python
def effective_task_a_segments_path(request):
    speaker_corrected = task_a_speaker_corrected_segments_path(request)
    corrected = task_a_corrected_segments_path(request)
    if speaker_corrected.exists():
        return speaker_corrected
    if corrected.exists():
        return corrected
    return task_a_segments_path(request)
```

新增路径函数：

```python
def task_a_speaker_corrected_segments_path(request):
    return task_a_correction_bundle_dir(request) / "segments.zh.speaker-corrected.json"
```

### 12.2 Task B 防御

Task B 不能再无条件信任 speaker label。需要增加：

```text
speaker profile quality gate
reference candidate quality gate
non_cloneable speaker handling
```

规则：

```text
non_cloneable speaker:
  可以保留字幕和翻译
  不生成 Voice Bank
  不自动克隆
  Task D 使用基础音色或要求人工 reference
```

### 12.3 Task C/D 影响

Task C：

- 文本翻译可复用。
- 但 `speaker_id` 映射必须更新。
- `translation.en.json` 应保留 `original_speaker_label` 和 `speaker_correction`。

Task D：

- 只对 cloneable speaker 做 voice clone。
- non_cloneable speaker 默认使用 fallback voice 或进入人工 reference。
- reference clip 必须来自 speaker-corrected 后的 label。

## 13. 自动纠错算法设计

### 13.1 Conservative embedding group

当前相邻短句会被较激进地合并成 embedding group。建议改成保守策略：

```text
只有在以下条件满足时才合并进同一个 embedding group：
gap <= 0.25s
combined_duration <= 5.0s
text 不包含明显问答切换
两段不是中英混合互答
两段都不是极短称呼/应答词
两段声学 embedding 初步相似
```

第一阶段可以先只调整参数：

```toml
[speaker_attribution.embedding_group]
max_gap_sec = 0.25
max_group_sec = 5.0
max_segments = 3
```

但更好的方式是两步：

```text
先单段/短窗口提 embedding
再按 embedding similarity 决定是否合并
```

### 13.2 Long segment VAD resplit

对长异常 segment：

```text
duration_sec > 8s 且 text_density 低
```

处理：

1. 在 segment 时间范围内跑 VAD。
2. 找出真实 speech islands。
3. 只对 speech island 提 embedding。
4. reference clip 只使用 speech island，不使用整段时间窗。
5. 如果 island 内有多 speaker 风险，进入 review。

### 13.3 Prototype relabel

Task B 生成 speaker profile 后，做二次 segment relabel：

```text
for each segment:
  segment_embedding = embedding(segment audio)
  scores = cosine(segment_embedding, speaker_prototypes)
  best = max(scores)
  current = score(current_speaker)

  if best_speaker != current_speaker
     and best - current >= margin
     and best >= threshold:
       suggest relabel
```

建议阈值：

```toml
[speaker_attribution.prototype_relabel]
auto_threshold = 0.72
review_threshold = 0.62
margin = 0.08
```

输出：

```text
speaker_relabel_suggestions.zh.json
```

### 13.4 Short orphan smoothing

自动修正短孤岛：

```text
prev_speaker == next_speaker
current_speaker != prev_speaker
current_run_duration <= 1.5s
current_run_segment_count <= 2
```

可以自动建议：

```text
merge_to_surrounding_speaker
```

是否自动应用取决于风险：

```text
high confidence -> auto
medium confidence -> review
low confidence -> keep
```

### 13.5 Speaker profile gate

Task B 生成 profile 后输出质量状态：

```text
profile_status:
  ready
  review
  non_cloneable
  unstable
```

规则：

```text
total_speech_sec < 3s -> non_cloneable
segment_count = 1 -> non_cloneable
reference_clip_count = 0 -> non_cloneable
long anomaly dominates references -> review
prototype internal similarity low -> unstable
```

## 14. Diarization-first 长期方案

### 14.1 为什么需要 diarization-first

当前链路是：

```text
ASR segment -> speaker label
```

问题是：一个 ASR segment 可能包含多个真实说话人。后处理最多只能给整个 segment 改 speaker，无法对 segment 内部拆 A/B。

更适合影视配音的链路是：

```text
audio
-> speaker diarization turns
-> ASR with word timestamps
-> word-to-speaker alignment
-> speaker-aware segments
```

这样可以解决：

- 快速对话
- 插话
- 同一句中多人说话
- 电话/画外音
- ASR 时间戳过宽

### 14.2 候选 backend

| backend | 成熟度 | 优点 | 风险 |
| --- | --- | --- | --- |
| pyannote | 高 | diarization 能力成熟，生态完整 | 可能需要 Hugging Face token 和模型授权 |
| NeMo diarization | 中高 | 可本地运行，配置灵活 | 依赖重，调参成本高 |
| whisperX pipeline | 中高 | ASR alignment + diarization 组合成熟 | 依赖复杂，GPU 更合适 |
| 当前 SpeechBrain ECAPA 聚类 | 中 | 已接入，工程成本低 | 不是完整 diarization，影视快对话效果有限 |

建议：

```text
默认继续使用当前轻量方案
新增 high_quality_diarization 模式
对同一任务做 benchmark 后再切换默认策略
```

### 14.3 Benchmark 指标

如果有人工标注，使用：

```text
DER
speaker confusion
missed speech
false alarm
```

如果没有人工标注，使用代理指标：

```text
高风险 speaker 数下降
single_segment_speaker 数下降
long_duration_low_segment_count 下降
reference contamination risk 下降
Task D speaker_failed 下降
人工 review 决策数下降
```

对 `task-20260421-075513` 的目标：

```text
speaker_count 从 8 收敛到更合理数量
SPEAKER_02 长异常 profile 不再污染 reference
SPEAKER_04/06/07 不再默认参与 clone
Task D speaker_failed 从 91 明显下降
```

## 15. 配置设计

```toml
[speaker_review]
enabled = true
auto_generate_diagnostics = true
require_review_before_task_b = false
block_clone_for_non_cloneable = true

[speaker_review.thresholds]
min_cloneable_total_speech_sec = 3.0
min_cloneable_segment_count = 2
long_segment_sec = 8.0
very_long_segment_sec = 15.0
isolated_run_sec = 3.0
max_sec_per_char = 1.2

[speaker_attribution.embedding_group]
max_gap_sec = 0.25
max_group_sec = 5.0
max_segments = 3

[speaker_attribution.prototype_relabel]
enabled = true
auto_threshold = 0.72
review_threshold = 0.62
margin = 0.08

[speaker_attribution.high_quality_diarization]
enabled = false
backend = "pyannote"
min_speaker_turn_sec = 0.5
word_alignment = true
```

## 16. 前端落地计划

### Phase UI-1: 说话人审查 Tab

实现 `SpeakerReviewDrawer`，Tab 结构如下：

```text
说话人总览
高风险 speaker
speaker run
segment 详情
```

功能：

- speaker 总览
- 高风险 speaker 列表
- speaker run 列表
- segment 详情
- 保存人工决策

不做：

- 不做波形编辑
- 不做拖拽时间线
- 不做实时重切音频

### Phase UI-2: 决策应用

增加底部操作：

```text
应用 speaker 修正
从 Task B 重跑
```

状态展示：

```text
未应用
已应用
需要重跑 Task B
Task B 已使用 speaker-corrected 输入
```

### Phase UI-3: 上下文试听

支持：

```text
播放 segment
播放 run
播放前后上下文
```

实现方式：

- 第一版后端临时裁剪 WAV 并作为 artifact 返回。
- 后续可缓存到 `.speaker-review-clips/`。

## 17. 后端落地计划

### Phase BE-1: 诊断和决策文件

新增模块：

```text
src/translip/speaker_review/diagnostics.py
src/translip/speaker_review/decisions.py
src/translip/speaker_review/export.py
```

新增路由：

```text
src/translip/server/routes/speaker_review.py
```

新增测试：

```text
tests/test_speaker_review.py
tests/test_speaker_review_routes.py
```

### Phase BE-2: 应用决策

实现：

```text
apply_speaker_decisions()
write_speaker_corrected_segments()
write_speaker_corrected_srt()
```

支持决策：

```text
relabel
merge_speaker
mark_non_cloneable
exclude_from_reference
keep_independent
needs_split
```

### Phase BE-3: Task B 接入

修改：

```text
effective_task_a_segments_path()
Task B profile builder
Task B reference selector
```

新增：

```text
speaker_profile_quality
non_cloneable speaker status
reference exclusion
```

## 18. 数据兼容策略

### 18.1 旧任务

旧任务没有 speaker-corrected 文件时：

```text
继续使用 segments.zh.corrected.json 或 segments.zh.json
```

### 18.2 新任务

新任务默认生成 diagnostics，但不阻塞 pipeline：

```text
speaker_diagnostics.zh.json always generated
speaker_review_plan.zh.json generated when risks exist
```

是否阻塞 Task B 由配置决定：

```text
require_review_before_task_b = false
```

短期建议不阻塞，只提示风险。高质量模式可以设置为 true。

### 18.3 已完成任务返修

对已完成任务：

```text
生成 speaker decisions
输出 speaker-corrected segments
从 Task B 重跑
```

如果不想重跑 Task C，可在 Task C 加“只更新 speaker_id 映射”的快速路径。

## 19. 风险与防护

### 19.1 人工误改 speaker

防护：

- 所有决策可撤销。
- 保留 `original_speaker_label`。
- 保存决策历史。
- 支持重新生成 corrected 文件。

### 19.2 自动合并 speaker 过度

防护：

- 第一阶段不默认自动应用高风险 relabel。
- 自动建议和人工决策分开。
- 只有短孤岛且前后 speaker 一致时才允许自动合并。

### 19.3 speaker-corrected 影响缓存

防护：

- manifest 记录输入 hash。
- Task B/C/D cache key 纳入 speaker-corrected segments hash。
- 如果 speaker decisions 变化，Task B 以后必须失效。

### 19.4 reference clip 被污染

防护：

- bad_reference_candidate 直接从候选中剔除。
- non_cloneable speaker 不构建 Voice Bank。
- reference plan 显示风险来源。

### 19.5 diarization-first 依赖复杂

防护：

- 作为 high_quality 模式，不影响默认链路。
- 先做 benchmark。
- 明确模型授权和 token 需求。

## 20. 验收标准

### 20.1 Speaker diagnostics

- 能对 `task-20260421-075513` 输出 speaker 级、run 级、segment 级风险。
- `SPEAKER_02` 被标记为高风险。
- `SPEAKER_04/06/07` 被标记为样本不足或 non-cloneable 候选。
- 长异常 segment 被标记为 `bad_reference_candidate`。

### 20.2 Speaker Review UI

- 能展示 speaker 总览。
- 能展示高风险 speaker。
- 能展示 speaker run。
- 能保存 relabel / merge / non_cloneable 决策。
- UI 风格与任务详情页一致。
- 不出现不同 speaker 被默认合成同一角色的误导操作。

### 20.3 Apply decisions

- 能输出 `segments.zh.speaker-corrected.json`。
- 每个被改动的 segment 保留 `original_speaker_label`。
- SRT 中 speaker label 同步更新。
- manifest 记录 changed segment 数和决策来源。

### 20.4 Pipeline 接入

- Task B 优先消费 `segments.zh.speaker-corrected.json`。
- non_cloneable speaker 不进入自动音色克隆。
- reference clip 不包含 bad_reference_candidate。
- 从 Task B 重跑后，speaker profile 数和 reference 质量有明显改善。

### 20.5 质量收益

对 `task-20260421-075513` 的首轮目标：

```text
高风险独立 speaker 数下降
reference contamination risk 下降
speaker profile 更接近真实角色
Task D speaker_failed 明显下降
人工审查从 175 段压缩到约 10-30 个高价值决策点
```

## 21. 技术成熟度评估

| 能力 | 成熟度 | 评价 |
| --- | --- | --- |
| speaker diagnostics | 高 | 基于现有 JSON 和简单规则即可实现 |
| speaker run review UI | 高 | 沿用任务详情页右侧抽屉视觉语言，工程风险低 |
| manual speaker decisions | 高 | 纯 JSON 决策文件，可追溯 |
| apply speaker decisions | 高 | 本质是重写 segment speaker_label |
| Task B 消费 speaker-corrected | 高 | 路径优先级改造小 |
| reference 风险过滤 | 中高 | 需要把 diagnostics 接入 Task B reference builder |
| prototype relabel | 中 | 依赖 segment embedding 质量，需要阈值调优 |
| long segment VAD resplit | 中 | 需要音频裁剪和 VAD 边界稳定 |
| diarization-first | 中 | 能力成熟，但依赖和授权成本更高 |
| 全自动影视级 speaker attribution | 中低 | 快速对话和混音场景仍需要人工审查兜底 |

## 22. 推荐实施顺序

### Phase 1: 诊断和人工闭环

交付：

```text
speaker_diagnostics.zh.json
speaker_review_plan.zh.json
manual_speaker_decisions.zh.json
segments.zh.speaker-corrected.json
Speaker Review UI
```

价值：

- 马上解决当前任务的 speaker 错配。
- 防止错误 speaker 继续污染音色克隆。
- 人工工作量可控。

### Phase 2: Task B 防污染

交付：

```text
profile_status
non_cloneable speaker
reference exclusion
reference contamination report
```

价值：

- 即使 speaker 仍有少量错误，也不让坏样本进入 Voice Bank。

### Phase 3: 自动二次纠错

交付：

```text
speaker_relabel_suggestions.zh.json
prototype relabel
short orphan smoothing
long segment VAD cleaning
```

价值：

- 减少人工审查量。
- 提升默认 speaker attribution。

### Phase 4: 高质量 diarization backend

交付：

```text
high_quality_diarization config
pyannote / NeMo / whisperX benchmark
speaker attribution benchmark report
```

价值：

- 面向影视配音质量上限。
- 对快节奏多人对话有根本改善。

## 23. 针对 task-20260421-075513 的执行建议

第一轮人工只需要处理：

```text
SPEAKER_02
SPEAKER_04
SPEAKER_06
SPEAKER_07
```

建议策略：

| speaker | 建议 |
| --- | --- |
| `SPEAKER_02` | 高风险，先排除长异常 reference，人工审查它的 8 段是否属于多个真实角色 |
| `SPEAKER_04` | 只有 1 秒，默认 non_cloneable，听上下文后合并到相邻真实 speaker |
| `SPEAKER_06` | 只有 1.2 秒，默认 non_cloneable，听上下文后合并或保留字幕-only |
| `SPEAKER_07` | 只有一段重复短语，默认 non_cloneable，不进入 Voice Bank |

然后处理 speaker run 中明显的短孤岛：

```text
seg-0059
seg-0141
```

应用修正后，从 Task B 重跑：

```text
Task B -> Task D -> Task E -> Task G
```

短期不要继续基于当前 speaker profile 做 Voice Bank 优化，因为当前 profile 已经包含错误样本风险。

## 24. 结论

这块应作为配音质量优化的前置项目处理。

当前最可落地的路线不是直接换 diarization 模型，而是先建立：

```text
speaker diagnostics
-> Speaker Review UI
-> manual decisions
-> speaker-corrected segments
-> Task B 防污染
```

这样可以在不大改 pipeline 的情况下，先把真实任务中的 speaker 错配控制住。等这个闭环稳定后，再引入 diarization-first 高质量模式，才有明确的 benchmark 和回退路径。
