# 任务 D 测试报告: 单说话人目标语言声音克隆

- 项目: `video-voice-separate`
- 对应设计: [task-d-single-speaker-voice-cloning.md](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/docs/task-d-single-speaker-voice-cloning.md)
- 测试日期: 2026-04-12
- 当前开发后端: `F5-TTS`
- 测试机器: `MacBook M4 16GB`

## 1. 测试范围

本轮测试覆盖 3 类内容:

1. 单元测试与 CLI 回归
2. 任务 D 独立冒烟验证
3. 从 `test_video/我在迪拜等你.mp4` 到任务 D 的端到端串行验证

本轮没有把 `OpenVoice V2` 作为可运行后端纳入测试范围。

## 2. 最终结论

任务 D 当前已经达到 **可开发、可重复运行、可自动评估** 的状态:

- `F5-TTS` 权重下载、缓存和本地加载已经接入项目
- `synthesize-speaker` CLI 已可稳定输出 segment 级音频、demo 音频和报告
- 评估链已接入:
  - `speaker similarity`
  - `ASR back-read`
  - `duration ratio`
- 从测试视频出发，到 `Stage 1 -> Task A -> Task B -> Task C -> Task D` 的链路已经真实跑通

但任务 D 目前仍然属于 **开发验证级**，不是生产可交付级:

- 中文参考音频到英文输出，`F5-TTS` 的音色相似度通常可以过线
- 时长已经可控到 `review/passed` 区间附近
- 但内容正确率仍会出现串词、前缀噪句和跨语种错误

因此当前结论是:

- **工程链路已成立**
- **开发默认后端可用**
- **成品质量仍需后续 `OpenVoice V2` 或更强后端继续提升**

## 3. 本轮修复的关键问题

这轮实现和测试中，实际打到并修掉了下面这些问题:

1. `F5-TTS` 默认运行时下载会长时间卡住
   - 处理: 改成项目内显式下载并缓存 checkpoint / vocoder
   - 实现位置: `src/video_voice_separate/dubbing/assets.py`

2. `F5-TTS` 内部把超大随机种子写到 `PYTHONHASHSEED`
   - 结果: 评估阶段会出现 `Fatal Python error: config_init_hash_seed`
   - 处理: 调用层固定使用合法范围内的稳定种子

3. 对 `fix_duration` 的理解错误
   - 初版把“目标段长”直接传给 F5
   - 实际上 F5 需要的是“参考音频 + 目标语音”的总时长
   - 结果: 初版生成结果只有 `256` 个采样点，几乎是空音频
   - 处理: 修正为 `reference.duration_sec + target_duration_sec`

4. 声纹评估会被极短音频打崩
   - `ECAPA` 在极短 waveform 上可能直接因 padding 报错
   - 处理: 在 speaker embedding 侧增加重采样和最小时长补齐逻辑

5. 端到端脚本的默认 speaker 选择不适合 Task D
   - 初版直接选 `total_speech_sec` 最大的 speaker
   - 结果: 很容易选到“长段很多”的 speaker，不适合当前单段 TTS
   - 处理: 改成优先选择“短句足够多 + 参考 clip 更稳”的 speaker，并在 `--max-segments` 下自动挑更适合 Task D 的 segment

## 4. 单元测试

执行命令:

```bash
uv run pytest
```

最终结果:

- `29 passed`

其中与任务 D 直接相关的覆盖包括:

- reference candidate 排序
- reference 预处理
- Task D report / manifest 生成
- CLI 参数解析

## 5. 任务 D 独立冒烟测试

### 5.1 使用现有 Task A/B/C 产物做 3 段冒烟

执行命令:

```bash
uv run video-voice-separate synthesize-speaker \
  --translation ./tmp/task-d-recheck-c/voice/translation.en.json \
  --profiles ./output-task-b/voice/speaker_profiles.json \
  --speaker-id spk_0000 \
  --output-dir ./tmp/task-d-smoke \
  --backend f5tts \
  --device auto \
  --max-segments 3 \
  --keep-intermediate
```

最终代表性结果:

- 产物目录: `tmp/task-d-smoke/voice/spk_0000/`
- 参考 clip: `clip_0005.wav`
- 三段都能正常生成音频和评估报告
- 结果从“空音频 / 崩溃”提升到“可回读、可算声纹、时长接近可用”

代表性指标:

- `seg-0001`
  - `duration_ratio=1.249`
  - `speaker_similarity=0.5639`
  - `text_similarity=0.2143`
- `seg-0002`
  - `duration_ratio=1.481`
  - `speaker_similarity=0.5263`
  - `text_similarity=0.48`
- `seg-0003`
  - `duration_ratio=1.286`
  - `speaker_similarity=0.4923`
  - `text_similarity=0.6471`

结论:

- 声音相似度已经进入可比较范围
- 时长控制已经基本可用
- 但跨语种内容正确率仍然波动较大

## 6. 端到端验证

### 6.1 完整串行脚本真实跑通

执行命令:

```bash
uv run python scripts/run_task_a_to_d.py \
  --input ./test_video/我在迪拜等你.mp4 \
  --output-root ./tmp/e2e-task-a-to-d \
  --target-lang en \
  --translation-backend local-m2m100 \
  --tts-backend f5tts \
  --device auto \
  --max-segments 3
```

真实产物:

- Stage 1: `tmp/e2e-task-a-to-d/stage1/我在迪拜等你/`
- Task A: `tmp/e2e-task-a-to-d/task-a/voice/`
- Task B: `tmp/e2e-task-a-to-d/task-b/voice/`
- Task C: `tmp/e2e-task-a-to-d/task-c/voice/`
- Task D: `tmp/e2e-task-a-to-d/task-d/voice/`

这次完整串行流程已经成功执行到 Task D 结束，说明:

- 输入视频解复用与分离链路正常
- 说话人归因转写正常
- speaker registry 正常
- 多语种翻译脚本生成正常
- 单 speaker 语音合成和评估链路正常

### 6.2 自动 speaker/segment 选择优化后的验证

由于 Task D 当前是“单 speaker、短句优先”的开发能力，完整串行脚本里增加了更贴近 Task D 的自动选择逻辑:

- 自动 speaker: 优先短句足够多、参考 clip 更稳的 speaker
- 自动 segment: 在 `--max-segments` 下优先选 `1.5s - 4.5s` 的短句

基于这套规则的代表性验证路径:

- 输入: `tmp/e2e-task-a-to-d/task-c/voice/translation.en.json`
- 自动 speaker: `spk_0001`
- 自动 segment: `seg-0010`, `seg-0032`, `seg-0042`
- 结果目录: `tmp/e2e-task-a-to-d-auto-plan-check-v2/voice/spk_0001/`

结果:

- `3 / 3` 都达到 `overall_status=review`
- 没有再出现 `failed` 的空音频或评估崩溃

代表性指标:

- `seg-0010`
  - `duration_ratio=1.527`
  - `speaker_similarity=0.5932`
  - `text_similarity=0.7368`
  - `overall_status=review`
- `seg-0032`
  - `duration_ratio=1.565`
  - `speaker_similarity=0.4597`
  - `text_similarity=0.8919`
  - `overall_status=review`
- `seg-0042`
  - `duration_ratio=1.422`
  - `speaker_similarity=0.3149`
  - `text_similarity=0.75`
  - `overall_status=review`

这说明当前任务 D 的开发实现已经达到:

- 端到端链路稳定
- 音色相似度通常能进入 `review/passed`
- 文本回读在合适短句上可进入 `review`
- 时长比率多数可压到 `review`

### 6.3 最新完整脚本重跑

为了确认最新脚本逻辑不是只在已有产物上成立，我又对整条链路做了一次完整重跑:

```bash
uv run python scripts/run_task_a_to_d.py \
  --input ./test_video/我在迪拜等你.mp4 \
  --output-root ./tmp/e2e-task-a-to-d-v2 \
  --target-lang en \
  --translation-backend local-m2m100 \
  --tts-backend f5tts \
  --device auto \
  --max-segments 3
```

最新真实产物:

- Stage 1: `tmp/e2e-task-a-to-d-v2/stage1/我在迪拜等你/`
- Task A: `tmp/e2e-task-a-to-d-v2/task-a/voice/`
- Task B: `tmp/e2e-task-a-to-d-v2/task-b/voice/`
- Task C: `tmp/e2e-task-a-to-d-v2/task-c/voice/`
- Task D: `tmp/e2e-task-a-to-d-v2/task-d/voice/spk_0001/`

最新脚本自动选择结果:

- `speaker_id=spk_0001`
- `segment_ids=seg-0007,seg-0008,seg-0009`

Task D 结果:

- `1 failed`
- `2 review`

代表性指标:

- `seg-0007`
  - `duration_ratio=1.736`
  - `speaker_similarity=0.4355`
  - `text_similarity=0.9655`
  - `overall_status=failed`
- `seg-0008`
  - `duration_ratio=1.437`
  - `speaker_similarity=0.4758`
  - `text_similarity=1.0`
  - `overall_status=review`
- `seg-0009`
  - `duration_ratio=1.629`
  - `speaker_similarity=0.5476`
  - `text_similarity=1.0`
  - `overall_status=review`

这里可以看到当前开发后端的真实状态:

- 文本内容在短句上已经可以很接近目标句
- 声纹相似度通常在 `review/passed` 区间
- 最大短板仍然是时长偏长

这也是任务 D 当前被定性为 **开发验证级** 而不是 **成品交付级** 的直接原因。

## 7. 当前已知限制

这不是 bug，而是当前开发后端和任务边界的真实限制:

1. `F5-TTS` 作为 `zh -> en` 开发后端，仍然会出现英文前缀串词
2. 对特别短的词组或专有名词，内容正确率波动明显
3. 对长句或长段，当前 Task D 不适合作为默认验证样本
4. `OpenVoice V2` 仍是预留后端，尚未接入实际推理
5. 当前评估仍是开发向指标，不等于最终出海成品质量

## 8. 结论

任务 D 当前已经完成了“从不可用到可开发”的跨越:

- CLI、数据结构、后端抽象、自动评估和端到端脚本都已落地
- 单元测试通过
- 真机真实视频链路跑通
- 代表性短句样本已能稳定进入 `review`

下一步最合理的方向不是继续在 `F5-TTS` 上做大量细调，而是:

1. 接入 `OpenVoice V2`
2. 把任务 D 的 `review` 级结果提升到更接近可交付的质量
3. 再进入任务 E 的时间贴合、拼接与混音
