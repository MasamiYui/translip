# 任务 B 技术设计: 声纹建档与说话人检索

- 项目: `video-voice-separate`
- 文档状态: Draft v1
- 创建日期: 2026-04-11
- 对应任务: [speaker-aware-dubbing-task-breakdown.md](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/docs/speaker-aware-dubbing-task-breakdown.md)
- 前置依赖: [task-a-speaker-attributed-transcription.md](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/docs/task-a-speaker-attributed-transcription.md)

## 1. 目标

任务 B 的目标不是重新做 diarization，而是把任务 A 产出的临时标签:

- `SPEAKER_00`
- `SPEAKER_01`
- `SPEAKER_02`

升级成 **可复用、可检索、可人工确认** 的说话人档案。

这一步要解决三个问题:

1. 如何从任务 A 的句段里，为每个说话人构造稳定的参考音频
2. 如何把参考音频变成可比较的 speaker embedding
3. 如何把当前视频里的 speaker 与已有声纹库做匹配，并给出稳定 `speaker_id`

## 2. 范围与非目标

### 2.1 任务范围

任务 B 负责:

- 从任务 A 输出中提取 speaker reference clips
- 计算 speaker embeddings
- 构建当前任务内的 `speaker_profiles.json`
- 从本地 `speaker_registry.json` 检索近邻 speaker
- 输出 top-k 候选、分数和匹配决策
- 支持人工确认后把 speaker 写回 registry

### 2.2 非目标

任务 B 当前不负责:

- 重新切分说话人时间线
- 生物认证级别的高安全声纹识别
- 复杂会议重叠说话建模
- 人名识别或自动实名
- 翻译和 TTS

说明:

- 这里的“声纹”是 **媒体生产场景里的身份一致性建档**，不是金融或门禁场景的高安全认证。

## 3. 与任务 A 的关系

任务 A 已经产出:

- 句段文本
- 时间戳
- 临时 `speaker_label`

例如:

- [segments.zh.json](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/output-task-a/voice/segments.zh.json)

任务 B 要在此基础上增加一层稳定身份:

- `speaker_label` 只在当前样本里有意义
- `speaker_id` 要能跨视频复用

因此:

- 任务 A 解决“谁在什么时候说了什么”
- 任务 B 解决“这个人是不是同一个已知 speaker”

## 4. 技术选型

## 4.1 V1 实现选型

### 选择

任务 B 第一版默认使用:

- `SpeechBrain ECAPA-TDNN` 作为 speaker embedding backend

原因:

- 任务 A 已经在本地稳定集成了它
- 无需引入新的 gated model 流程
- CPU 和本地环境已经验证可运行
- 可以与任务 A 当前 embedding 空间保持一致

这是一种 **工程优先** 的选择，不是学术上唯一最优选择。

## 4.2 升级预留

任务 B 的实现会从第一天就保留 backend 抽象，后续可切换为:

- `3D-Speaker / CAM++`
- `WeSpeaker`

升级理由:

- `CAM++` 论文明确强调更低计算成本和更快推理，同时保持强 speaker verification 表现
- `3D-Speaker` 官方仓库已经提供 speaker verification、speaker recognition、speaker diarization 和批量推理接口
- `WeSpeaker` 官方仓库提供 embedding、similarity、diarization 的 CLI 和 Python API，适合作为备选实现

但 **任务 B 的首个目标是先把“档案+匹配”链路做稳**，不是一开始就为了追最新 embedding backend 大幅增加集成复杂度。

## 4.3 为什么现在不直接切到 CAM++

不是因为 CAM++ 不好，而是因为当前项目阶段更重要的是:

- 把 registry 数据模型定稳
- 把 profile 聚合策略定稳
- 把阈值和人工确认流程定稳

如果这三件事没定稳，直接换更强 embedding 模型，工程收益有限。

结论:

- `V1`: `speechbrain-ecapa`
- `V1.1` 或 `V2`: 加 `campplus` backend

## 5. 输入与输出

## 5.1 输入

任务 B 的标准输入:

- 任务 A 产出的 `segments.zh.json`
- 对应原始人声音频:
  - `voice.wav`
  - `voice.mp3`
- 可选已有 registry:
  - `speaker_registry.json`

## 5.2 输出

建议输出 4 类产物:

1. `speaker_profiles.json`
2. `speaker_matches.json`
3. `speaker_registry.json`
4. `reference_clips/`

## 5.3 输出定义

### `speaker_profiles.json`

表示“当前这条视频里的 speaker 档案”。

示例结构:

```json
{
  "job_id": "voice",
  "backend": {
    "speaker_backend": "speechbrain-ecapa",
    "embedding_dim": 192
  },
  "profiles": [
    {
      "profile_id": "profile_0000",
      "source_label": "SPEAKER_00",
      "speaker_id": null,
      "display_name": null,
      "status": "unmatched",
      "total_speech_sec": 46.2,
      "segment_count": 21,
      "prototype_embedding": [0.01, -0.02, 0.05],
      "reference_clips": [
        "reference_clips/profile_0000/clip_0001.wav"
      ]
    }
  ]
}
```

### `speaker_matches.json`

表示当前 profile 与 registry 的检索结果。

示例结构:

```json
{
  "matches": [
    {
      "profile_id": "profile_0000",
      "decision": "matched",
      "matched_speaker_id": "spk_0007",
      "score": 0.79,
      "margin_to_second": 0.11,
      "top_k": [
        {"speaker_id": "spk_0007", "score": 0.79},
        {"speaker_id": "spk_0012", "score": 0.68}
      ]
    }
  ]
}
```

### `speaker_registry.json`

表示项目长期复用的说话人库。

建议结构:

```json
{
  "version": 1,
  "backend": {
    "speaker_backend": "speechbrain-ecapa",
    "embedding_dim": 192
  },
  "speakers": [
    {
      "speaker_id": "spk_0007",
      "display_name": "narrator_main",
      "status": "confirmed",
      "aliases": ["host_a"],
      "prototype_embedding": [0.01, -0.02, 0.05],
      "exemplar_embeddings": [
        [0.01, -0.02, 0.05]
      ],
      "reference_clips": [
        "registry_clips/spk_0007/clip_0001.wav"
      ],
      "created_at": "2026-04-11T22:00:00+08:00",
      "updated_at": "2026-04-11T22:00:00+08:00"
    }
  ]
}
```

### `reference_clips/`

存放当前 profile 的高质量参考音频片段，方便:

- 人工试听
- 后续 TTS 参考
- registry 更新时复用

## 6. 核心设计

任务 B 的核心链路是:

`segments.zh.json -> 按 speaker_label 聚合 -> 生成参考 clips -> 提 embedding -> 聚合成 prototype -> 与 registry 匹配 -> 输出 match decision`

## 6.1 说话片段聚合

从任务 A 输出中先按 `speaker_label` 分组。

然后对每组句段做两步处理:

1. 合并相邻且 gap 很小的句段
2. 过滤质量太差的候选片段

合并的原因:

- 单句太短时 speaker embedding 容易抖
- 相邻句段本来就常常属于同一轮发言

建议初始规则:

- 相邻 gap `<= 0.6s` 时合并
- 合并后单段目标时长优先落在 `2s ~ 12s`

## 6.2 参考片段质量过滤

不是所有句段都适合入库。

任务 B 第一版建议只保留满足以下条件的片段:

- 语音时长 `>= 1.5s`
- 语音时长 `<= 15s`
- 不全是极短词、语气词或纯噪声
- RMS 能量不明显异常

这一步的目标是避免:

- 用太短的词当 reference
- 用背景噪声或残留音乐污染 speaker prototype

## 6.3 Embedding 提取

对每个候选 reference clip:

- 抽取 speaker embedding
- 做 `L2 normalize`
- 保存 clip 级 embedding

当前默认 backend:

- `speechbrain-ecapa`

输出:

- 一个 profile 对应多个 clip embeddings

## 6.4 Prototype 聚合

不能直接拿某一个 clip 代表整个人。

建议聚合流程:

1. 先算 profile 内 embeddings 的两两相似度
2. 找出最稳定的中心 embedding
3. 剔除明显离群的 clip
4. 对剩余 embeddings 求均值
5. 再做一次 normalize，得到 `prototype_embedding`

这样做的好处:

- 某个片段里如果混入噪声或误分 speaker，不会直接把 prototype 拉偏

## 6.5 Registry 匹配

对当前 profile 的 `prototype_embedding`，与 registry 中每个 speaker 比较。

比较对象建议有两层:

1. registry speaker 的 `prototype_embedding`
2. registry speaker 的 `exemplar_embeddings`

匹配分数建议定义为:

- `score = max(cos(query, prototype), max(cos(query, exemplars)))`

原因:

- 某些 speaker 的 prototype 很稳
- 某些 speaker 在不同语气下 exemplar 反而更有判别力

## 6.6 决策策略

任务 B 不应该只输出“最像谁”，还要输出“这次结果是否可信”。

建议先用三档决策:

- `matched`
- `review`
- `new_speaker`

初始阈值建议:

- `score >= 0.72` 且 `margin_to_second >= 0.05`:
  - `matched`
- `0.62 <= score < 0.72`:
  - `review`
- `score < 0.62`:
  - `new_speaker`

说明:

- 这些阈值是 **项目初始阈值**
- 必须根据本仓库后续真实数据持续校准

## 6.7 Registry 更新策略

registry 不应该被自动写乱。

建议只允许两种写入方式:

1. `confirmed new speaker`
2. `confirmed match and merge`

也就是说:

- `matched` 可以自动建议
- 真正写库时最好仍留一个确认动作

这样可以避免:

- 一次错误匹配把两个不同人永久合并

## 7. 模块设计

建议新增模块:

- `src/video_voice_separate/speakers/runner.py`
  - 任务 B 主入口
- `src/video_voice_separate/speakers/reference.py`
  - 参考片段选择与导出
- `src/video_voice_separate/speakers/embedding.py`
  - embedding backend 封装
- `src/video_voice_separate/speakers/profile.py`
  - profile 聚合与 prototype 构建
- `src/video_voice_separate/speakers/registry.py`
  - registry 读写、匹配、更新
- `src/video_voice_separate/speakers/export.py`
  - JSON manifest 导出

## 8. CLI 设计

任务 B 不建议一开始就做得过于复杂。

先做一个主命令就够:

```bash
uv run video-voice-separate build-speaker-registry \
  --segments ./output-task-a/voice/segments.zh.json \
  --audio ./output/我在迪拜等你/voice.mp3 \
  --output-dir ./output-task-b \
  --registry ./registry/speaker_registry.json
```

第一版建议命令完成这几件事:

1. 读取任务 A 结果
2. 生成当前视频的 `speaker_profiles.json`
3. 读取 registry 并做匹配
4. 生成 `speaker_matches.json`
5. 在显式允许时更新 registry

是否拆成多个子命令，可以在代码实现前再确认，但第一版不必过度设计。

## 9. 任务 B 的实现顺序

建议按下面顺序写代码:

1. 先做 reference clip 选择
2. 再做 embedding 提取
3. 再做 profile 聚合
4. 再做 registry 读写
5. 最后做 matching decision

原因:

- 任务 B 的质量首先取决于 reference clips 是否干净
- 如果 reference clip 本身选坏了，后面换模型也救不回来

## 10. 测试策略

## 10.1 自动测试

必须覆盖:

- reference clip 合并与过滤规则
- embedding 维度与归一化
- prototype 聚合逻辑
- registry schema
- top-k 排序正确性
- 阈值决策逻辑

## 10.2 真实素材测试

当前仓库只有一个完整测试视频，因此任务 B 的真实验证建议这样做:

### 测试方案 A: 同视频分段复用测试

把同一个测试视频的人声轨切成两个时间段:

- `clip_a`
- `clip_b`

然后:

1. 对 `clip_a` 先跑任务 A
2. 对 `clip_b` 再跑任务 A
3. 分别建立 speaker profiles
4. 用 `clip_a` 建的 speaker registry 去匹配 `clip_b`

验收点:

- 主讲人或主要角色在两个片段中应能稳定 top-1 命中

### 测试方案 B: 正负样本对比

从当前视频中人工挑出:

- 同一说话人的两个片段
- 不同说话人的两个片段

验收点:

- 同人相似度显著高于异人相似度

## 10.3 报告要求

任务 B 每次完成测试后要产出测试报告，至少包含:

- 输入样本路径
- speaker profile 数量
- registry 中 speaker 数量
- 匹配到已有 speaker 的数量
- 新 speaker 数量
- review 数量
- same-speaker 与 different-speaker 的相似度抽样
- 人工抽查结论

## 11. 验收标准

任务 B 通过的最低标准:

- 能为任务 A 的临时 speaker 生成稳定 profile
- 能输出 top-k 匹配结果
- 同一人物跨两个片段时，top-1 基本稳定
- 同人分数明显高于异人分数
- registry 可读、可写、可禁用

如果出现以下情况，则任务 B 不算完成:

- registry 写入后无法重复读取
- top-k 结果排序明显错误
- same-speaker 和 different-speaker 分数大面积混淆
- 当前视频里的主 speaker 无法稳定复用

## 12. 风险与升级路径

## 12.1 当前风险

- 任务 A 的句段级 speaker 标签如果有误，会把 reference clip 污染到任务 B
- 背景音乐残留会影响 embedding 稳定性
- 单视频数据不足时，阈值容易过拟合

## 12.2 升级方向

任务 B 后续可按这条路线升级:

1. `speechbrain-ecapa` -> `campplus`
2. 加入更严格的 reference clip 质量评分
3. 增加人工确认后的增量学习式 prototype 更新
4. 引入跨语言、跨情绪更稳的 speaker backend

## 13. 结论

任务 B 的核心不是“再换一个更强模型”，而是先把这三件事做稳:

1. reference clip 选得对
2. profile prototype 聚得稳
3. registry match 决策可解释

本轮代码实现建议采用:

- `V1 backend = speechbrain-ecapa`
- `backend interface` 预留 `campplus`

这样可以在不推倒任务 A 的前提下，最快把“临时 speaker 标签 -> 可复用 speaker_id”这条链路跑通。

## 14. 参考资料

- 3D-Speaker 官方仓库: [modelscope/3D-Speaker](https://github.com/modelscope/3D-Speaker)
- 3D-Speaker Toolkit 论文: [arXiv:2403.19971](https://arxiv.org/abs/2403.19971)
- CAM++ 论文: [arXiv:2303.00332](https://arxiv.org/abs/2303.00332)
- WeSpeaker 官方仓库: [wenet-e2e/wespeaker](https://github.com/wenet-e2e/wespeaker)
- ECAPA-TDNN 论文: [arXiv:2005.07143](https://arxiv.org/abs/2005.07143)
