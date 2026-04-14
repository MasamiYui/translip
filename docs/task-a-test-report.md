# 任务 A 测试报告: 说话人归因转写

- 项目: `translip`
- 任务: `任务 A`
- 报告日期: 2026-04-11
- 状态: Passed

## 1. 测试目标

验证任务 A 是否已经具备以下能力:

- 从真实测试素材的人声轨中生成中文转写
- 为句段打上可用的 `speaker_label`
- 输出结构化 JSON 和 SRT
- 在当前测试视频上不存在阻塞性交付问题

## 2. 测试输入

### 原始测试视频

- [我在迪拜等你.mp4](/Users/masamiyui/OpenSoureProjects/Forks/translip/test_video/我在迪拜等你.mp4)

### 上游人声轨

- [voice.mp3](/Users/masamiyui/OpenSoureProjects/Forks/translip/output/我在迪拜等你/voice.mp3)

说明:

- 任务 A 的设计输入是 `voice.wav/mp3`
- 本次测试直接复用了当前仓库上一条流水线已经产出的人声轨

## 3. 测试环境

- 系统: `macOS 26.4.1 arm64`
- Python: `3.11.14`
- 执行方式: `uv run`
- ASR: `faster-whisper small`
- Speaker embedding: `SpeechBrain ECAPA`
- 设备: `CPU`

## 4. 运行命令

### 自动测试

```bash
uv run pytest
```

结果:

- `12 passed`

### 真实素材验证

```bash
uv run translip transcribe \
  --input ./output/我在迪拜等你/voice.mp3 \
  --output-dir ./output-task-a \
  --keep-intermediate
```

## 5. 产物路径

- JSON: [segments.zh.json](/Users/masamiyui/OpenSoureProjects/Forks/translip/output-task-a/voice/segments.zh.json)
- SRT: [segments.zh.srt](/Users/masamiyui/OpenSoureProjects/Forks/translip/output-task-a/voice/segments.zh.srt)
- Manifest: [task-a-manifest.json](/Users/masamiyui/OpenSoureProjects/Forks/translip/output-task-a/voice/task-a-manifest.json)
- 中间音频: [transcription_input.wav](/Users/masamiyui/OpenSoureProjects/Forks/translip/output-task-a/voice/intermediate/transcription_input.wav)

## 6. 测试结果

### 自动测试

- 全部通过
- CLI、导出结构、聚类辅助逻辑没有回归

### 真实素材结果

- 输入时长: `534.593s`
- 输出句段数: `193`
- 识别 speaker 数: `7`
- 运行耗时: `81.609s`
- 状态: `succeeded`

### 关键抽样

起始段:

- `00:18.320 - 00:32.660`
- 连续 8 个句段主要被归为 `SPEAKER_00`
- 与“同一连续说话段应保持一致标签”的预期一致

中段:

- `04:38 - 04:48` 附近连续句段主要归为 `SPEAKER_01`
- 说明在长视频中能维持一定的 speaker 连续性

尾段:

- `08:37 - 08:45` 的英文片段主要归为 `SPEAKER_02`
- 说明中英文混合句段也能被纳入统一 speaker 标签体系

## 7. 修复过程

在本次任务实现中，真实测试暴露过一个关键问题:

- 初版 speaker 聚类结果为 `193` 个句段、`185` 个 speaker

这是不可接受的过度切分。之后做了两轮修正:

1. 从“逐句段 embedding 聚类”改为“合并相邻句段形成更稳定的 embedding group 再聚类”
2. 对视频场景加入合理 speaker 上限回退，并增加短句平滑

修复后结果收敛到:

- `193` 个句段
- `7` 个 speaker

这已经从“明显错误”回到“视频场景可用”的范围。

## 8. 结论

结论:

- **任务 A 已完成并通过当前测试视频验证**
- 当前版本已经能稳定产出句段级 `start/end/text/speaker_label`
- 在当前测试视频上没有发现阻塞性交付的问题

当前版本可作为后续任务的输入:

- 任务 B `声纹建档与说话人检索`
- 任务 C `面向配音的多语种翻译脚本生成`

## 9. 当前边界

以下属于当前版本的已知边界，不视为本轮阻塞问题:

- speaker 标签仍是临时标签，不是跨视频稳定身份
- 句段级 speaker 归因优先，不是词级 diarization
- 复杂重叠说话场景不是当前版本目标

## 10. 下一步建议

下一步应进入:

- `任务 B: 声纹建档与说话人检索`

因为现在已经有了稳定的句段、时间轴和临时 speaker 标签，可以开始把这些临时 speaker 升级为可复用身份。
