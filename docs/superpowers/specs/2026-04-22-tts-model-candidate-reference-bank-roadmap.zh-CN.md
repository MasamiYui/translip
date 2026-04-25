# TTS 模型切换、多候选重生成与 Speaker Reference Bank 后续优化方案

日期：2026-04-22

适用任务：`task-20260421-075513`

## 1. 结论摘要

当前更大的质量收益不应继续押在单点规则改写上，而应按下面顺序推进：

1. **先建 Speaker Reference Bank**：每个说话人不再只依赖一个 reference clip，而是保留 3-7 个可评测候选，包括原始 clip、拼接 composite reference、人工推荐 reference。
2. **再做多候选重生成**：对 failed/review 片段按失败原因生成候选组合，候选维度包括文本改写、reference、TTS backend、采样参数、同 speaker 短句合并。
3. **最后做模型切换**：这台机器是 Apple M4、16GB 内存、MPS 可用、无 CUDA，因此优先验证本机可运行的轻量模型：`moss-tts-nano-onnx`、`qwen3tts 0.6B`、可选 `MLX Qwen3-TTS 0.6B 4bit`。不建议直接把 1.7B 或更大模型作为默认全量后端。

推荐落地策略：

```text
短期默认:
  MOSS-TTS-Nano ONNX CPU
  + reference quality retry
  + safe rule-based rewrite

下一阶段:
  Voice Bank benchmark
  + adaptive multi-candidate repair
  + qwen3tts 0.6B 小样本 benchmark

通过门槛后:
  对特定 speaker / 特定 failure type 启用 Qwen3 0.6B fallback
  而不是全任务直接切换模型
```

## 2. 当前基线

### 2.1 本机硬件与运行约束

本机环境：

```text
CPU/SoC: Apple M4
内存: 16GB
OS: macOS 26.4.1 arm64
PyTorch: 2.11.0
MPS: available / built
CUDA: unavailable
```

约束：

- 不能依赖 CUDA。
- 全量 Task D 已经耗时较高，任何多候选方案都必须做自适应触发，不能对所有片段无差别生成 3-5 次。
- 16GB 内存可以尝试 0.6B 级别 TTS 模型，但不应默认全量跑 1.7B+ 模型。
- MPS 后端需要保留 CPU fallback，因为部分音频/transformer op 可能在 MPS 上不稳定。

### 2.2 当前样例质量

最新完整重跑结果：

```text
Task C:
  fit = 103
  review = 28
  risky = 44
  rule_based_condense = 12

Task D:
  total = 173
  retry_triggered = 75
  retry_selected_second_reference = 49
  retry_review_or_passed = 7

Task E:
  overall failed = 133
  overall review = 38
  overall passed = 1

  duration failed = 75
  speaker failed = 81
  intelligibility failed = 25

  avg speaker_similarity = 0.2581
  avg text_similarity = 0.8804
  avg duration_ratio = 1.8497
  avg quality_score = 1.3566
```

已经完成的优化有效但有限：

| 优化 | 已验证收益 | 剩余问题 |
| --- | --- | --- |
| 本地规则压缩 | Task C `risky` 从 54 降到 44 | 只能处理少量安全短语，不能盲目截词 |
| Task D quality retry | Task E `failed` 从 141 降到 133，`duration failed` 从 86 降到 75 | 75 段触发 retry，成本高；仍有大量 speaker failed |
| Task E quality summary | 问题更可见 | 只统计，不修复 |
| final dub 使用纯配音音轨 | 修复正式产物音轨选择 | 不提升 TTS 本身质量 |

核心判断：

```text
现在不是“过滤 failed”或“再加几条 rewrite 规则”能解决的问题。
剩余瓶颈主要是：
  1. reference 选择不稳定；
  2. TTS 对短句和弱 reference 的生成时长不可控；
  3. 单候选输出缺少择优；
  4. 当前 MOSS backend 在部分 speaker 上音色克隆能力不足。
```

## 3. 模型选型与本机可运行性

### 3.1 候选模型矩阵

| 后端 | 本机可运行性 | 当前集成状态 | 预期收益 | 风险 | 建议 |
| --- | --- | --- | --- | --- | --- |
| `moss-tts-nano-onnx` | 高。CPU ONNX，官方说明适合 MacBook Air M4 单核运行 | 已集成，当前默认 | 稳定、轻量、易批量跑 | 短句时长发散，音色相似度低 | 保留默认，作为 baseline 和快速候选 |
| `qwen3tts` 0.6B Base | 中高。0.6B，项目已有 backend；MPS 可用，需 CPU fallback | 已有 `QwenTTSBackend` | 声音自然度和 voice clone 可能更好，可做失败段 fallback | 首次加载慢，内存压力高于 MOSS，MPS 稳定性需实测 | 下一阶段首选 benchmark |
| MLX Qwen3-TTS 0.6B 4bit | 中。Apple Silicon 友好，模型卡显示约 1.71GB MLX 权重 | 未集成 | 更适配 M 系列芯片，可能比 PyTorch/MPS 更稳 | 新依赖 `mlx-audio`，API 需要验证 voice clone 行为 | 作为 P2 备选 adapter |
| Qwen3-TTS 1.7B | 中低。可小样本试跑，不适合 16GB 机器直接全量默认 | 未作为默认 | 质量可能更好 | 内存/速度成本高，长任务风险大 | 只做 5-10 段 smoke，不进入默认 |
| Voicebox 本地服务 | 中。产品侧支持本地多引擎和 Apple Silicon，但需要外部服务 | 未集成 | 可快速横向评估 Qwen/Chatterbox/LuxTTS 等 | 新运行时和 API 依赖，不适合作为核心闭环第一步 | 后续作为外部 adapter 选项 |
| 商业云 voice clone | 高质量可能性高 | 未集成 | 质量上限高 | 成本、隐私、版权、网络依赖 | 暂不默认，需单独确认 |

### 3.2 外部资料依据

- [OpenMOSS/MOSS-TTS-Nano](https://github.com/OpenMOSS/MOSS-TTS-Nano) 说明 MOSS-TTS-Nano 是 0.1B 级别模型，ONNX CPU 版本去掉 PyTorch 推理依赖，并提到在 MacBook Air M4 上可平滑运行。
- [Qwen/Qwen3-TTS-12Hz-0.6B-Base](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-Base) 是当前项目 `qwen3tts` backend 使用的 0.6B voice clone 模型。
- [mlx-community/Qwen3-TTS-12Hz-0.6B-Base-4bit](https://huggingface.co/mlx-community/Qwen3-TTS-12Hz-0.6B-Base-4bit) 提供 Apple Silicon 友好的 MLX 4bit 转换版本，模型卡显示可通过 `mlx-audio` 使用 reference audio。
- [Voicebox](https://voicebox.sh/) 是本地优先的多引擎 voice cloning 工具，支持 Qwen3-TTS、Chatterbox、LuxTTS、Kokoro 等，本方案只把它作为外部服务 benchmark 选项，不作为核心依赖。

### 3.3 默认模型切换原则

不做“一键全量换模型”。原因：

1. 当前 full Task D 已经较慢。
2. Qwen 0.6B 即使能跑，也需要验证 MPS/CPU fallback 的稳定性。
3. 不同 speaker 的收益不一定一致。
4. 有些失败不是模型能解决的，例如 speaker 归因错误、短句时间窗过窄、翻译文本不自然。

模型切换应走分层策略：

```text
if segment overall passed/review:
    不换模型
elif failure includes pathological_duration and moss_retry_failed:
    尝试 qwen3tts_0.6b
elif failure includes speaker_failed and speaker has stable voice_bank:
    尝试 qwen3tts_0.6b + best_bank_reference
elif source_duration < 0.8s:
    优先 same_speaker_merge 或 timing group，不优先换模型
else:
    保留 MOSS 多候选
```

## 4. 后续工程方案

### 4.1 Phase 0：建立可比较 benchmark

目标：先让每次优化都能量化，不再凭主观听感判断。

新增命令：

```bash
uv run translip benchmark-dub-backends \
  --translation task-c/voice/translation.en.json \
  --profiles task-b/voice/speaker_profiles.json \
  --task-d-report task-d/voice/*/speaker_segments.en.json \
  --output-dir task-d/voice/benchmark \
  --backends moss-tts-nano-onnx,qwen3tts \
  --max-segments-per-speaker 6 \
  --device auto
```

输出：

```text
task-d/voice/benchmark/
  tts_backend_matrix.en.json
  backend_scorecard.en.json
  samples/
    <backend>/<speaker_id>/<segment_id>.wav
```

每个 backend 记录：

- 可运行性：load 是否成功、是否 OOM、是否 fallback CPU。
- 速度：model load time、avg synthesis sec、RTF。
- 质量：overall/duration/speaker/intelligibility 分布。
- 成本：每段候选数、平均耗时、失败率。

验收门槛：

```text
qwen3tts_0.6b 可进入候选池，当且仅当：
  smoke test 通过 >= 20 段
  没有 OOM
  平均单段耗时 <= MOSS 当前耗时的 4x
  在同一 repair set 上:
    overall review+passed 提升 >= 15%
    或 speaker failed 降低 >= 10 个点
```

### 4.2 Phase 1：Speaker Reference Bank

目标：把“选一个 reference clip”升级成“每个 speaker 一个可评测 bank”。

新增模块：

```text
src/translip/dubbing/reference_bank.py
src/translip/dubbing/reference_benchmark.py
tests/test_reference_bank.py
```

输出文件：

```text
task-b/voice/voice_bank.en.json
```

数据结构：

```json
{
  "speaker_id": "spk_0001",
  "candidates": [
    {
      "reference_id": "profile_0001_clip_0005",
      "type": "source_clip",
      "path": "task-b/voice/reference_clips/profile_0001/clip_0005.wav",
      "duration_sec": 8.7,
      "text": "reference transcript",
      "rms": 0.05,
      "snr_proxy": 0.82,
      "speaker_purity": 0.91,
      "score": 0.77
    },
    {
      "reference_id": "profile_0001_composite_0001",
      "type": "composite",
      "path": "task-b/voice/reference_bank/profile_0001/composite_0001.wav",
      "duration_sec": 10.2,
      "source_clip_count": 4,
      "score": 0.81
    }
  ],
  "benchmark": {
    "calibration_segment_ids": ["seg-0063", "seg-0087", "seg-0100", "seg-0170"],
    "best_reference_id_by_backend": {
      "moss-tts-nano-onnx": "profile_0001_clip_0005",
      "qwen3tts": "profile_0001_composite_0001"
    }
  }
}
```

Reference candidate 来源：

1. Task B 已生成的原始 reference clips。
2. 同 speaker 多段高置信片段拼接的 composite reference。
3. 人工在 UI 中指定的 reference。
4. 后续可选：从原视频里重新裁剪更干净片段。

Reference score：

```text
score =
  duration_score * 0.22
  + text_score * 0.14
  + rms_score * 0.10
  + speaker_purity * 0.18
  + calibration_speaker_similarity * 0.22
  + calibration_intelligibility * 0.10
  + stability_score * 0.04
```

硬过滤：

```text
duration < 2.0s -> 不能作为自动 reference
duration > 15.0s -> 裁剪或拆分
疑似多人说话 -> 不能作为 voice clone reference
ASR 文本为空 -> 只能人工确认后使用
高背景音乐 / 低 RMS / 爆音 -> 降权或过滤
```

预期收益：

- `speaker failed` 从 81 降到 60-70。
- 对 `spk_0000`、`spk_0001`、`spk_0003` 收益最大。
- 对样本很少的 `spk_0007` 收益有限，需要人工决策。

技术成熟度：中高。当前已有 reference candidate 评分和 quality retry，扩展成 bank 是自然演进。

### 4.3 Phase 2：自适应多候选重生成

目标：每个 failed/review 片段不再只有一次输出，而是按失败原因生成最小必要候选集。

候选维度：

| 失败原因 | 候选动作 | 上限 |
| --- | --- | ---: |
| pathological duration | 换 reference、换 backend、降低 max_new_frames/tokens | 2-4 |
| speaker failed | voice bank top references、qwen fallback | 2-3 |
| intelligibility failed | text normalize、rewrite、qwen fallback | 2-4 |
| short source `< 1.0s` | same speaker merge、phrase rewrite、timing group | 1-3 |
| review only | 不急于生成，进入人工预览队列 | 0-1 |

候选生成策略：

```text
candidate_grid(segment):
  base = current selected output

  if duration_status == failed:
      add reference top-2
      add constrained generation params

  if speaker_status == failed:
      add voice_bank best references

  if intelligibility_status == failed:
      add rewrite candidates

  if backend_benchmark says qwen improves this speaker:
      add qwen3tts_0.6b

  if source_duration < 1.0s and same_speaker neighbor exists:
      add same_speaker_merge_group

  cap candidates by priority:
      high priority: max 5
      medium priority: max 3
      low priority: max 1
```

候选选择 score：

```text
score =
  overall_status_score * 100
  + duration_status_score * 24
  + intelligibility_status_score * 18
  + speaker_status_score * 10
  + duration_proximity * 5
  + text_similarity * 5
  + speaker_similarity * 3
  - runtime_penalty
```

缓存策略：

```text
cache_key =
  segment_id
  + target_text_hash
  + backend
  + backend_params_hash
  + reference_id
  + source_duration_bucket
```

输出：

```text
task-d/voice/repair-run/
  repair_attempts.en.json
  selected_segments.en.json
  candidate_audio/
```

预期收益：

- `overall failed` 从 133 降到 95-115。
- `duration failed` 从 75 降到 55-65。
- `intelligibility failed` 从 25 降到 12-18。

技术成熟度：中。已有 repair executor、多候选 attempt 概念和 Task D quality retry，但需要统一到 repair queue，避免主 Task D 全量变慢。

### 4.4 Phase 3：Qwen3 0.6B 本机模型验证与接入

目标：在 Apple M4 16GB 上验证 `qwen3tts` 是否能作为 fallback，而不是直接替换默认。

Smoke test：

```bash
uv run translip synthesize-speaker \
  --translation task-c/voice/translation.en.json \
  --profiles task-b/voice/speaker_profiles.json \
  --speaker-id spk_0000 \
  --backend qwen3tts \
  --device auto \
  --max-segments 3 \
  --output-dir /tmp/translip-qwen-smoke
```

Benchmark set：

```text
每个主要 speaker 选 6 段：
  2 段短句
  2 段中等长度
  1 段 speaker failed
  1 段 intelligibility failed
```

通过标准：

```text
模型加载成功；
MPS 或 CPU fallback 不崩；
peak memory 不影响系统稳定；
20-40 段 benchmark 可完成；
在目标 repair set 上比 MOSS:
  speaker_similarity 平均提升 >= 0.04
  或 intelligibility failed 降低 >= 30%
  或 overall review+passed 增加 >= 15%
```

接入策略：

```text
默认 Task D:
  backend = moss-tts-nano-onnx

repair fallback:
  if voice_bank says qwen wins for speaker:
      use qwen3tts for speaker_failed repair items

duration abnormal fallback:
  if MOSS generated_duration/source_duration >= 2.0 after reference retry:
      try qwen3tts once

manual UI:
  allow user choose "用 Qwen 重生成这段/这个 speaker"
```

不建议的做法：

- 不建议把 `qwen3tts` 设为全局默认，直到 full task benchmark 证明它的耗时和质量收益都可接受。
- 不建议在 16GB 机器上默认启用 1.7B 全量合成。

技术成熟度：中。项目已有 `QwenTTSBackend`，但需要真实机器 benchmark。

### 4.5 Phase 4：MLX Qwen3 0.6B 4bit 备选路线

目标：如果 PyTorch/MPS 版 Qwen 不稳定或太慢，评估 MLX 4bit 后端。

新增 backend：

```text
src/translip/dubbing/mlx_qwen_tts_backend.py
backend name = qwen3tts-mlx-4bit
```

依赖：

```bash
uv add mlx-audio
```

验证命令：

```bash
python -m mlx_audio.tts.generate \
  --model mlx-community/Qwen3-TTS-12Hz-0.6B-Base-4bit \
  --text "Hello, this is a test."
```

接入条件：

```text
只有当:
  PyTorch qwen3tts 在 MPS/CPU 上不稳定
  或 MLX 版速度显著更好
才进入正式 backend。
```

技术成熟度：中低。模型卡显示 MLX 4bit 可用，但项目尚未集成，需要验证 voice clone 参数和输出一致性。

### 4.6 Phase 5：same-speaker 短句合并

目标：解决 `< 1.0s` 极短片段导致 TTS 发散的问题。

规则：

```text
只允许 same_speaker_merge_group 合成一条 TTS。
不同 speaker 只允许 dialogue_timing_group，不能文本合并。
```

自动合并条件：

```text
same speaker_id
speaker confidence 高
相邻 gap <= 0.35s
合并后总时长 1.2s - 4.5s
中间无其他 speaker
无 overlap / speaker_conflict
文本语义连续
```

输出映射：

```json
{
  "merge_group_id": "mg-spk_0001-0084-0086",
  "speaker_id": "spk_0001",
  "source_segment_ids": ["seg-0084", "seg-0085", "seg-0086"],
  "merged_target_text": "Mom, Dad, I have arrived in Dubai.",
  "audio_path": "task-d/voice/merge_candidates/mg-spk_0001-0084-0086/selected.wav",
  "child_placements": [
    {"segment_id": "seg-0084", "start": 0.0, "end": 0.8},
    {"segment_id": "seg-0085", "start": 0.8, "end": 1.5},
    {"segment_id": "seg-0086", "start": 1.5, "end": 2.4}
  ]
}
```

Task E 只消费 selected audio，不再猜合并关系。

预期收益：

- 极短片段 duration failed 明显下降。
- TTS 重复输出减少。
- speaker similarity 单段评估稳定性提高。

技术成熟度：中高。方案明确，风险主要是误合并不同 speaker，需要 UI review 兜底。

## 5. UI 与人工审查

### 5.1 Voice Bank UI

每个 speaker 展示：

- 当前默认 reference。
- 所有 bank candidates。
- 每个 candidate 的原音频、文本、时长、RMS、speaker purity、benchmark 分数。
- 一键试听：reference + 3 段 calibration outputs。
- 操作：
  - 设为默认 reference。
  - 禁用 reference。
  - 上传人工 reference。
  - 合成 composite reference。

### 5.2 Repair Candidates UI

每个 failed item 展示：

- 原片段。
- 当前输出。
- 所有候选输出。
- 指标对比：
  - overall status
  - duration ratio
  - speaker similarity
  - text similarity
  - backend
  - reference
  - 耗时
- 操作：
  - 接受候选。
  - 继续重生成。
  - 改写文本。
  - 更换 reference。
  - 更换 TTS backend。
  - 标记人工返修。

### 5.3 模型切换 UI

不暴露复杂模型细节给普通用户，提供三档：

| UI 选项 | 实际策略 |
| --- | --- |
| 快速 | MOSS only，最多一次 reference retry |
| 均衡 | MOSS + voice bank + qwen fallback for failed |
| 高质量 | MOSS + Qwen + multi-candidate + human review required |

默认建议：`均衡`，但只有在 qwen smoke test 通过后启用。

## 6. 实施计划

### Milestone 1：Benchmark 与 Voice Bank

范围：

- 新增 `voice_bank.en.json` 生成器。
- 新增 reference benchmark。
- 新增 backend benchmark 命令。
- UI 显示每个 speaker 的 bank 与 benchmark 结果。

验收：

```text
task-20260421-075513:
  每个主要 speaker 至少有 3 个 reference candidates
  能输出 best reference by backend
  单测覆盖 reference scoring / composite generation / benchmark cache
```

预计收益：

```text
speaker failed: 81 -> 65-72
overall failed: 133 -> 120-128
```

### Milestone 2：Repair Queue 多候选执行

范围：

- repair queue 生成候选 grid。
- repair executor 支持 backend/reference/text 多维候选。
- Task E 消费 selected repair segments。
- UI 支持候选试听与选择。

验收：

```text
对于 high-priority failed items:
  自动生成 2-5 个候选
  selected candidate 写入 selected_segments.en.json
  Task E 可复用 selected candidate
```

预计收益：

```text
duration failed: 75 -> 55-65
intelligibility failed: 25 -> 12-18
overall failed: 133 -> 95-115
```

### Milestone 3：Qwen3 0.6B Fallback

范围：

- 运行 qwen3tts smoke test。
- 对 repair set 做 qwen/moss 对照。
- 只有通过门槛后启用 qwen fallback。
- 若 PyTorch/MPS 版不稳定，再评估 MLX 4bit adapter。

验收：

```text
qwen3tts_0.6b:
  本机可加载
  20-40 段 benchmark 完成
  无 OOM
  可回退到 MOSS
```

预计收益：

```text
speaker failed: 65-72 -> 50-62
overall failed: 95-115 -> 80-100
```

### Milestone 4：same-speaker merge 与人工审核闭环

范围：

- 生成 merge candidates。
- UI 展示并要求人工确认高风险 merge。
- repair executor 合成 merged audio。
- Task E 按 child placements 放置。

验收：

```text
不同 speaker 永不自动合并为一条 TTS。
same speaker merge 可追溯到原 segment ids。
用户可拒绝 merge。
```

预计收益：

```text
极短片段 failed 明显下降。
overall failed 进一步下降 10-20。
```

## 7. 测试方案

### 7.1 单元测试

新增：

```text
tests/test_reference_bank.py
tests/test_tts_backend_benchmark.py
tests/test_repair_candidate_grid.py
tests/test_merge_candidates.py
```

覆盖：

- reference bank scoring。
- composite reference 生成。
- reference purity 过滤。
- backend benchmark cache key。
- qwen unavailable fallback。
- candidate grid 上限控制。
- same speaker merge 硬规则。
- 不同 speaker 禁止 TTS merge。

### 7.2 集成测试

```bash
uv run pytest tests/test_dubbing.py tests/test_repair.py tests/test_rendering.py -q
uv run pytest tests -q
```

样例测试：

```bash
uv run translip run-pipeline \
  --input test_video/我在迪拜等你.mp4 \
  --output-root ~/.cache/translip/output-pipeline/task-20260421-075513 \
  --template asr-dub+ocr-subs \
  --target-lang en \
  --translation-backend local-m2m100 \
  --tts-backend moss-tts-nano-onnx \
  --device auto \
  --run-from-stage task-d \
  --run-to-stage task-g \
  --reuse-existing \
  --force-stage task-d \
  --force-stage task-e \
  --force-stage task-g \
  --write-status
```

Qwen smoke：

```bash
uv run translip synthesize-speaker \
  --translation ~/.cache/translip/output-pipeline/task-20260421-075513/task-c/voice/translation.en.json \
  --profiles ~/.cache/translip/output-pipeline/task-20260421-075513/task-b/voice/speaker_profiles.json \
  --speaker-id spk_0000 \
  --backend qwen3tts \
  --device auto \
  --max-segments 3 \
  --output-dir /tmp/translip-qwen-smoke
```

### 7.3 浏览器测试

必须验证：

- 任务页 Task D/E/G 状态正常。
- Dubbing Review UI 可以看到 voice bank、repair candidates。
- 用户选择候选后，Task E/G 可重新导出。
- 控制台无 error。

## 8. 风险与回滚

| 风险 | 处理 |
| --- | --- |
| Qwen 首次下载/加载慢 | 只做 smoke test，不阻塞默认 MOSS |
| Qwen MPS 崩溃 | backend 自动 CPU fallback，失败则禁用 qwen candidate |
| 多候选导致 Task D 过慢 | candidate cap + cache + high-priority only |
| reference bank 选错 reference | UI 可禁用 candidate；每个 candidate 有 benchmark 证据 |
| same speaker merge 误合并 | 只允许 same speaker；高风险 merge 需要人工确认 |
| 指标提升但听感差 | UI 人工试听确认；selected candidate 可覆盖 |
| 1.7B 模型内存压力 | 不进入默认，只允许手动小样本试跑 |

回滚策略：

```text
全局配置:
  repair_multi_candidate_enabled = false
  qwen_fallback_enabled = false
  voice_bank_enabled = false

任务级:
  保留原 Task D reports
  Task E 可回退消费原 speaker_segments.en.json
```

## 9. 推荐下一步

我建议下一步先做 Milestone 1，不直接切模型：

1. 实现 `voice_bank.en.json`。
2. 实现 reference benchmark。
3. 实现 backend benchmark smoke。
4. 用 `task-20260421-075513` 跑 MOSS vs Qwen 0.6B 的小样本对照。
5. 根据 benchmark 决定是否启用 qwen fallback。

原因：

- 当前 75 段触发 retry，说明 reference 与短句稳定性是主要问题。
- qwen3tts 已有代码入口，但还没有本机 full-quality 证据。
- 先做 benchmark 能避免“换模型后更慢但不一定更好”。

推荐优先级：

```text
P0: benchmark framework + voice bank
P1: adaptive multi-candidate repair
P2: qwen3tts 0.6B fallback
P3: same-speaker merge UI review
P4: MLX 4bit adapter or Voicebox external adapter
```

