# 电视剧/电影配音 vNext 预期收益文档

> 日期：2026-04-30
> 对象：中文电影/电视剧/短剧自动英文配音
> 当前样片基线：`task-20260430-015606`

## 1. 当前基线

最新 Dubai Playwright 全流程任务已能生成 ASR 字幕 + 配音成品，但质量门仍为 blocked：

| 指标 | 当前值 |
| --- | ---: |
| `content_quality.status` | `blocked` |
| `coverage_ratio` | `0.9171` |
| `failed_ratio` | `0.3757` |
| `speaker_failed_ratio` | `0.1326` |
| `intelligibility_failed_ratio` | `0.0939` |
| `audible_coverage.failed_count` | `8` |
| Task E skipped segments | `15` |

用户听感问题和指标吻合：

- 少量 ASR 字幕有，但没有声音。
- 音色克隆不像或不和谐。
- 部分角色/性别配错。
- 不同说话人复用同一音色。

## 2. 本轮可直接收益

### 2.1 自动返修接入 Task E

预期收益：

- 已有 repair queue 不再停留在报告层，会真实影响最终混音。
- `selected_segments.en.json` 中通过 backread/speaker/duration gate 的候选会替换原始失败音频。
- 对 `duration_failed`、`intelligibility_failed`、`speaker_failed` 段有局部修复收益。

预期指标变化：

| 指标 | 预期 |
| --- | --- |
| `selected_segments_path` | Task E manifest/report 中非空 |
| `repair selected_count` | 大于 0 时应减少失败段 |
| `failed_ratio` | 小幅下降，取决于 repair 候选通过率 |
| `text_similarity` | 对 rewrite 后片段应提升 |

### 2.2 Overlap-safe mixing

预期收益：

- 当前多个 `subtitle_window_not_covered` 来自 `skipped_overlap`。
- 有字幕窗口的短 overlap 改为 `placed_overlap` 后，字幕窗口不会直接静音。
- 对用户最敏感的“有字幕没声音”问题有直接收益。

预期指标变化：

| 指标 | 当前 | 预期 |
| --- | ---: | ---: |
| `audible_coverage.failed_count` | 8 | 下降到 0-3 |
| Task E skipped segments | 15 | 明显下降 |
| `coverage_ratio` | 0.9171 | 提升到 0.95+ |

风险：

- overlap 段可能听起来更密或轻微重叠。
- 如果失败音频本身质量差，保留声音不等于听感完全好。

缓解：

- `placed_overlap` 低增益叠放。
- 报告保留 `overlap_layered` note，后续可继续进 repair。

## 3. 中期收益

### 3.1 Character Ledger

预期收益：

- 减少“男声变女声”和“多人同音色”。
- 把 speaker 聚类错误从不可见问题变成可审计、可修正数据。
- 为角色级 voice prompt 缓存打基础。

预期指标：

| 指标 | 目标 |
| --- | --- |
| 高频角色 voice prompt 数 | 每个主角色 1 个稳定 prompt |
| 同角色 reference 污染 | 显著下降 |
| `speaker_failed_ratio` | 从 0.13 降到 0.08 以下 |

### 3.2 TTS/VC Tournament

预期收益：

- 不把单模型、单 reference 的偶然失败直接交付。
- Qwen xvec/icl、IndexTTS2、F5-TTS、CosyVoice2、Seed-VC 可以在同一评分器里公平对比。
- 对“说对内容”和“像原角色”分开优化。

预期指标：

| 指标 | 目标 |
| --- | --- |
| `text_similarity` | 0.90+ |
| `speaker_similarity` 主角色均值 | 0.40+ |
| `overall failed_ratio` | 0.15 以下 |

### 3.3 两阶段 TTS + VC

策略：

1. 先用内容稳定的 TTS 生成正确英文对白。
2. 再用 Seed-VC/OpenVoice 类 VC 转换到角色音色。

预期收益：

- 把“说错词”和“音色不像”解耦。
- 对短句和强情绪段更稳定。
- 可以让同一角色全片音色更一致。

## 4. 电影/电视剧场景专项收益

| 场景 | 当前风险 | vNext 方案 | 预期收益 |
| --- | --- | --- | --- |
| 短对白/抢话 | overlap skip、字幕静音 | `placed_overlap` + DialogueUnit | 少丢声音 |
| 反打/离屏说话 | 视觉角色和音频不一致 | Character Ledger 多证据融合 | 减少角色串台 |
| 硬字幕 | OCR 文本进入字幕但不进 TTS | Transcript Resolver + repair | 字幕/配音一致 |
| 方言/口语 | ASR 粗错和断句错 | ASR/OCR/forced alignment 融合 | 时间轴更稳 |
| 情绪强烈 | TTS 内容漂移 | backread gate + style candidates | 减少胡说/漏词 |
| 背景音乐/电话声 | reference 污染 | reference scoring + tournament | 音色更干净 |

## 5. 本轮停止/继续标准

本轮如果满足以下条件，可认为有阶段性收益：

- Playwright 全流程成功生成 final preview。
- Task E `selected_segments_path` 可见，且 repair report 产出。
- `skipped_overlap` 比基线下降。
- `audible_coverage.failed_count` 比基线下降。
- 没有因为 repair 让最终视频生成失败。

如果不满足：

- 若 repair selected 为 0：扩大 attempts 或接入 Qwen xvec repair backend。
- 若 overlap 后听感太乱：降低 overlap gain、只对 subtitle window 启用。
- 若 speaker mismatch 仍严重：下一轮优先落 Character Ledger 和 gender guard。

## 6. 参考来源

- [IndexTTS official GitHub](https://github.com/index-tts/index-tts)
- [F5-TTS arXiv](https://arxiv.org/abs/2410.06885)
- [CosyVoice2 arXiv](https://arxiv.org/abs/2412.10117)
- [Seed-VC official GitHub](https://github.com/Plachtaa/seed-vc)
- [pyannote.audio official GitHub](https://github.com/pyannote/pyannote-audio)
- [AVA-ActiveSpeaker Google Research](https://research.google/pubs/ava-activespeaker-an-audio-visual-dataset-for-active-speaker-detection/)
- [WhisperX paper](https://www.robots.ox.ac.uk/~vgg/publications/2023/Bain23/bain23.pdf)
