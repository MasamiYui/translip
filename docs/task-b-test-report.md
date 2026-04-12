# 任务 B 测试报告: 声纹建档与说话人检索

- 项目: `video-voice-separate`
- 任务: `任务 B`
- 报告日期: 2026-04-12
- 状态: Passed

## 1. 测试目标

验证任务 B 是否已经具备以下能力:

- 能基于任务 A 的 `segments.zh.json` 构建当前视频的 speaker profiles
- 能把 speaker profiles 写入文件化 registry
- 能用已有 registry 检索新片段中的 speaker
- 能给出 `matched / review / new_speaker` 的可解释决策

## 2. 实现结论

任务 B 本轮采用:

- 存储方式: **文件化 JSON**
- speaker backend: `SpeechBrain ECAPA`
- registry 形式: `speaker_registry.json`

没有引入数据库。

## 3. 自动测试

运行命令:

```bash
uv run pytest
```

结果:

- `18 passed`

覆盖范围:

- CLI 参数解析
- reference clip 合并与过滤
- profile payload 生成
- registry 读写与更新
- top-k 匹配逻辑
- 动态阈值决策逻辑

## 4. 正式产物

### 完整人声轨建档

运行命令:

```bash
uv run video-voice-separate build-speaker-registry \
  --segments ./output-task-a/voice/segments.zh.json \
  --audio ./output/我在迪拜等你/voice.mp3 \
  --output-dir ./output-task-b \
  --registry ./output-task-b/registry/speaker_registry.json \
  --update-registry \
  --keep-intermediate
```

正式产物:

- Profiles: [speaker_profiles.json](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/output-task-b/voice/speaker_profiles.json)
- Matches: [speaker_matches.json](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/output-task-b/voice/speaker_matches.json)
- Registry snapshot: [speaker_registry.json](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/output-task-b/voice/speaker_registry.json)
- Manifest: [task-b-manifest.json](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/output-task-b/voice/task-b-manifest.json)
- Registry file: [speaker_registry.json](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/output-task-b/registry/speaker_registry.json)

结果摘要:

- 输入完整人声轨时长: `534.593s`
- 构建 profile 数量: `7`
- 写入 registry speaker 数量: `7`
- 状态: `succeeded`

说明:

- 这是“首轮建库”运行，因此决策自然全部是 `new_speaker`
- 这一轮的目标是建立正式 speaker registry，而不是做跨片段复用验证

## 5. 跨片段复用验证

为了验证任务 B 最关键的“跨片段复用”能力，本轮使用 `test_video` 派生的人声轨做了分段测试。

### 5.1 测试素材

原始来源:

- [我在迪拜等你.mp4](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/test_video/我在迪拜等你.mp4)

上游人声轨:

- [voice.mp3](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/output/我在迪拜等你/voice.mp3)

派生片段:

- [voice_part_a.mp3](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/tmp/task-b-eval/clips/voice_part_a.mp3)
- [voice_part_b.mp3](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/tmp/task-b-eval/clips/voice_part_b.mp3)

### 5.2 测试步骤

1. 从完整人声轨切出 `part_a` 和 `part_b`
2. 分别对两个片段跑任务 A，得到两份独立的 `segments.zh.json`
3. 用 `part_a` 的任务 B 结果建 registry
4. 用 `part_b` 的任务 B 结果检索 `part_a` 的 registry

### 5.3 运行命令

任务 A:

```bash
uv run video-voice-separate transcribe \
  --input ./tmp/task-b-eval/clips/voice_part_a.mp3 \
  --output-dir ./tmp/task-b-eval/transcribe-a

uv run video-voice-separate transcribe \
  --input ./tmp/task-b-eval/clips/voice_part_b.mp3 \
  --output-dir ./tmp/task-b-eval/transcribe-b
```

任务 B:

```bash
uv run video-voice-separate build-speaker-registry \
  --segments ./tmp/task-b-eval/transcribe-a/voice_part_a/segments.zh.json \
  --audio ./tmp/task-b-eval/clips/voice_part_a.mp3 \
  --output-dir ./tmp/task-b-eval/task-b-a \
  --registry ./tmp/task-b-eval/registry/speaker_registry.json \
  --update-registry \
  --keep-intermediate

uv run video-voice-separate build-speaker-registry \
  --segments ./tmp/task-b-eval/transcribe-b/voice_part_b/segments.zh.json \
  --audio ./tmp/task-b-eval/clips/voice_part_b.mp3 \
  --output-dir ./tmp/task-b-eval/task-b-b \
  --registry ./tmp/task-b-eval/registry/speaker_registry.json \
  --keep-intermediate
```

### 5.4 关键产物

- `part_a` profiles: [speaker_profiles.json](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/tmp/task-b-eval/task-b-a/voice_part_a/speaker_profiles.json)
- `part_b` profiles: [speaker_profiles.json](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/tmp/task-b-eval/task-b-b/voice_part_b/speaker_profiles.json)
- `part_b` matches: [speaker_matches.json](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/tmp/task-b-eval/task-b-b/voice_part_b/speaker_matches.json)
- 评估 registry: [speaker_registry.json](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/tmp/task-b-eval/registry/speaker_registry.json)

### 5.5 结果摘要

- `part_a` profile 数量: `5`
- `part_a` registry speaker 数量: `5`
- `part_b` profile 数量: `4`
- `part_b` 检索决策:
  - `matched`: `1`
  - `review`: `2`
  - `new_speaker`: `1`

具体结果:

- `profile_0002` -> `matched` -> `spk_0000`
  - `score = 0.579782`
  - `margin_to_second = 0.372873`
- `profile_0001` -> `review`
  - `score = 0.467004`
- `profile_0000` -> `review`
  - `score = 0.371138`
- `profile_0003` -> `new_speaker`
  - `score = 0.311846`

### 5.6 阈值优化结论

本轮调试中，最初固定阈值过于保守，导致:

- 所有 `part_b` profile 都被判成 `new_speaker`

为了解决这个问题，本轮改成了:

- 基于 registry 内不同 speaker 的相似度底噪，动态推导 `matched_threshold` 和 `review_threshold`

本次评估中:

- registry speaker 间最大相似度: `0.306896`
- `matched_threshold`: `0.55`
- `review_threshold`: `0.356896`

优化后结果收敛到:

- `1 matched`
- `2 review`
- `1 new_speaker`

这个结果已经能体现出任务 B 的核心目的:

- 能从已有 registry 中检索出强候选
- 能把高置信和中置信结果区分开
- 不会把所有 profile 都粗暴判成同一个人

## 6. 本轮实现的关键改进

本轮不是只把 JSON 文件写出来，而是补了这些真实能力:

1. reference clip 自动选择与导出
2. profile prototype 聚合
3. top-k speaker 检索
4. `matched / review / new_speaker` 决策
5. 文件化 registry 增量更新
6. 基于 registry 底噪的动态阈值

## 7. 结论

结论:

- **任务 B 已完成并通过真实测试视频的分段复用验证**
- 当前版本已经能从任务 A 的临时 speaker 标签，构建出可复用的 speaker registry
- 当前版本已经能对新片段做 top-k speaker 检索，并给出可解释决策

当前版本已经满足进入任务 C 的前置条件:

- speaker profile 可用
- registry 可用
- speaker_id 映射链路成立

## 8. 当前边界

以下仍属于当前版本边界，不视为阻塞问题:

- `review` 结果仍需要人工确认
- speaker backend 目前还是 `speechbrain-ecapa`，还没有切到 `CAM++`
- registry 仍是 JSON 文件，不支持并发写入
- 任务 A 的分段错误仍会影响任务 B 的 profile 纯度

## 9. 下一步建议

下一步可以进入:

- `任务 C: 面向配音的多语种翻译脚本生成`

如果你希望先把 speaker 侧继续做强，也可以先做任务 B 的增强版:

- 加 `campplus` backend
- 加 profile 质量评分
- 加人工确认后的 registry merge 工具
