# 任务 A 技术设计: 说话人归因转写

- 项目: `translip`
- 文档状态: Draft v1
- 创建日期: 2026-04-11
- 对应任务: [speaker-aware-dubbing-task-breakdown.md](/Users/masamiyui/OpenSoureProjects/Forks/translip/docs/speaker-aware-dubbing-task-breakdown.md)

## 1. 目标

把输入的人声音频转成结构化中文转写结果，至少回答三个问题:

1. 说了什么
2. 谁在说
3. 从什么时候开始，到什么时候结束

本任务只解决 **样本内说话人归因**，不负责跨视频身份复用。跨视频 `speaker_id` 归档属于任务 B。

## 2. 输入与输出

### 输入

- `voice.wav`
- `voice.mp3`
- 也允许直接输入视频或普通音频文件，内部统一抽取为单声道 wav 处理

### 输出

- `segments.zh.json`
- 可选 `segments.zh.srt`
- `task-a-manifest.json`

`segments.zh.json` 的目标结构:

```json
{
  "input": {
    "path": "/abs/path/to/voice.wav",
    "duration_sec": 12.34,
    "sample_rate": 16000
  },
  "model": {
    "asr_backend": "faster-whisper",
    "asr_model": "small",
    "speaker_backend": "speechbrain-ecapa"
  },
  "segments": [
    {
      "id": "seg-0001",
      "start": 0.52,
      "end": 2.91,
      "duration": 2.39,
      "speaker_label": "SPEAKER_00",
      "text": "大家好，欢迎来到迪拜。",
      "language": "zh"
    }
  ]
}
```

## 3. 技术选型

### 3.1 ASR

选择:

- `faster-whisper`

原因:

- 本地部署成熟
- 中文可用
- 支持稳定的句段时间戳
- CPU 可跑，Apple Silicon 和 CUDA 都相对友好

当前不选 `WhisperX` 作为任务 A 首发实现，主要因为:

- 它更重
- 集成 diarization 时通常更依赖外部模型与复杂环境
- 当前任务先强调“单能力可落地”，不是一步到位做完整研究栈

### 3.2 Speaker embedding

选择:

- `SpeechBrain` 的 `ECAPA-TDNN` 说话人识别模型

原因:

- 开源可直接下载
- 不需要 Hugging Face gated access 或额外授权流程
- 社区成熟，适合做样本内 speaker clustering

当前不选 `pyannote` 作为任务 A 的首发 diarization 主链，主要因为:

- 很多高质量 pipeline 下载依赖 Hugging Face token 和模型授权确认
- 对当前“先把能力跑通并稳定测试”的目标不够友好

## 4. 方案设计

任务 A 不做“完整会议级 diarization”，而是采用一个更适合当前项目阶段的实用方案:

`预处理 -> ASR 句段 -> 句段音频切片 -> speaker embedding -> 聚类 -> 回填 speaker_label -> 导出`

### 4.1 预处理

- 任意输入统一抽取为:
  - 单声道
  - 16kHz
  - `wav`

原因:

- ASR 和 speaker embedding 都更适合统一采样率
- 可减少后续实现分支

### 4.2 句段生成

- 使用 `faster-whisper` 生成带时间戳的 ASR 句段
- 每个句段作为 speaker 归因的基本单位

这是一个明确的工程取舍:

- 优点:
  - 实现简单
  - 输出自然就是可编辑文本段
  - 很适合配音场景后续处理
- 缺点:
  - 如果一个 ASR 句段里恰好混入多个说话人，speaker 归因会退化

结论:

- 对当前项目阶段可接受
- 之后如果测试暴露问题，再升级成更细粒度的 VAD + diarization 方案

### 4.3 Speaker embedding 窗口

直接对过短句段提 embedding 会不稳定，因此采用“扩展窗口”策略:

- 以 ASR 句段的时间范围为核心
- 向前后各扩展一小段上下文
- 若句段过短，扩展到最小目标时长
- 窗口仍然受整段音频边界约束

这样做的目标是:

- 提高 embedding 稳定性
- 避免对 0.3 到 0.8 秒的超短句段直接抽 embedding

### 4.4 聚类策略

初版采用:

- 余弦距离
- 层次聚类
- 可调相似度阈值

输出临时标签:

- `SPEAKER_00`
- `SPEAKER_01`
- ...

初版不自动推断“真实人名”，也不做跨视频映射。

### 4.5 异常与退化策略

需要显式处理这些情况:

- 只有 1 个有效句段
  - 直接标成 `SPEAKER_00`
- embedding 提取失败
  - 整体降级为单 speaker
- 音频过短或无有效语音
  - 返回空句段结果并标注状态

## 5. 模块划分

建议新增以下模块:

- `src/translip/transcription/runner.py`
  - 任务 A 主入口
- `src/translip/transcription/asr.py`
  - `faster-whisper` 封装
- `src/translip/transcription/speaker.py`
  - embedding 与聚类
- `src/translip/transcription/export.py`
  - JSON/SRT/manifest 导出

CLI 新增一个独立命令，例如:

```bash
uv run translip transcribe \
  --input ./output/voice.wav \
  --output-dir ./output-task-a
```

## 6. 输出质量标准

任务 A 达标的最低口径:

- 单人样本:
  - 大部分句段为同一 `speaker_label`
- 双人样本:
  - 大部分句段能区分出两个 speaker
- 所有句段:
  - 时间戳合法
  - `speaker_label` 不为空
  - 文本可人工编辑

## 7. 已知限制

当前版本接受这些限制:

- 不处理复杂重叠说话
- 不保证会议场景的 state-of-the-art diarization
- 不做跨视频 identity linking
- 不做词级 speaker 对齐，只做到句段级 speaker 对齐

这些都属于当前版本的已知边界，不是 bug。

## 8. 测试策略

### 自动测试

- CLI 参数解析
- 输出 JSON schema
- 聚类结果稳定性
- 时间戳合法性
- 空结果和单 speaker 退化路径

### 实测

使用 `test_video` 中的真实素材做两轮验证:

1. 开发调试阶段:
  - 可先对测试视频裁出短样本进行迭代
2. 最终验收阶段:
  - 必须对完整测试视频跑一遍

### 测试报告

每次任务完成后都产出:

- 运行命令
- 运行环境
- 输入输出路径
- 句段数量
- 识别到的 speaker 数量
- 人工抽查结论
- 已知问题与后续修复建议

## 9. 下一步

任务 A 的首个实现目标是:

`input media -> segments.zh.json (start/end/text/speaker_label)`

在任务 A 被真实测试视频验证通过之前，不进入任务 B。
