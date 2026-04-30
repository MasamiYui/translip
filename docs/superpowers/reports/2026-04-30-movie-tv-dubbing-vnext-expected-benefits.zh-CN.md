# 电影/电视剧配音 vNext 预期收益与验收标准

> 日期：2026-04-30  
> 对象：中文影视内容自动英文配音  
> 样例：`test_video/我在迪拜等你.mp4`

## 1. 当前基线问题

`task-20260429-165133` 暴露了三类主要问题：

1. **字幕和真实说话不同步**  
   最终预览使用 `subtitle_source=asr`，但 ASR segment 中有很多长窗口只有少量真实人声，导致“字幕有，人没说话”。

2. **配音角色和音色绑定不稳定**  
   Task A 的 speaker diarization 把大部分对白压到 `SPEAKER_03` 和 `SPEAKER_01`，多个真实角色复用少量 `speaker_id`。

3. **TTS clone 后端质量不够**  
   本次任务使用 `moss-tts-nano-onnx`，Task E 中 `speaker passed=5`、`speaker failed=59`、平均 `speaker_similarity=0.2861`，不适合作为电影级默认。

## 2. 目标收益

### 2.1 时间轴与字幕

| 指标 | 当前问题 | vNext 目标 |
| --- | --- | --- |
| 长 ASR 空窗 | 33s ASR 窗口中活跃人声只占 23% | 通过 forced alignment 重切，长空窗不直接用于字幕/配音 |
| 预览字幕来源 | ASR source | 默认 SRT/OCR/DialogueUnit source，ASR 只作为听写证据 |
| subtitle/audio mismatch | 多处字幕挂在静音区 | 自动报告并阻断 |

预期收益：

- “字幕有但人没说话”的明显体感问题减少 70% 以上。
- 预览字幕和配音窗口从 segment 级变成 DialogueUnit/word-level 级。

### 2.2 角色与音色

| 指标 | 当前 `task-20260429-165133` | vNext 目标 |
| --- | ---: | ---: |
| speaker failed | 59 | <= 25 |
| speaker passed | 5 | >= 35 |
| avg speaker_similarity | 0.2861 | >= 0.45 |
| 主角音色一致性 | 无 character-level prompt | 同 character 复用 voice prompt |

预期收益：

- 不同角色复用同一音色的问题明显减少。
- 同一角色跨全片音色更稳定。
- 低置信 speaker 不再自动进入 TTS，而是要求人工确认或 fallback。
- 已验证局部收益：`seg-0042` 到 `seg-0044` 三句 unit 使用 `QWEN_TTS_CLONE_MODE=xvec + TRANSLIP_REFERENCE_TOURNAMENT=1` 后，speaker similarity 从 MOSS 样本的 `0.2302` 级别提升到 `0.4537`，进入 passed 边界；overall 从 failed 提升到 review。
- 扩大到 `spk_0003` 前 10 段后，overall 从 `0 passed / 1 review / 9 failed` 提升到 `1 passed / 6 review / 3 failed`，avg speaker similarity 从 `0.2361` 提升到 `0.3215`，avg text similarity 从 `0.8820` 提升到 `0.9283`。

### 2.3 配音完整度

| 指标 | 当前最佳 vNext-windowed | vNext 目标 |
| --- | ---: | ---: |
| SRT 可听覆盖 | 161/171 | >= 165/171 |
| overlap skip | 0 | 0 |
| intelligibility failed | 43 | <= 30 |
| avg text_similarity | 0.7867 | >= 0.82 |

预期收益：

- 小对白、短句和漏句不再简单丢失。
- 低质量短句不会直接进入最终视频。
- 配音完整度提升时，不牺牲文本可懂度。

## 3. 阶段性验收

### Preview-OK

用于内部预览或产品演示：

- SRT 可听覆盖 >= `160/171`。
- overlap skip = `0`。
- 不使用 ASR 字幕直接导出。
- 明显坏翻译如 `乐乐 -> pleasure` 被拒绝。

当前 `tmp/dubai-vnext-windowed` 已达到 Preview-OK。

### Movie-OK

用于电影/电视剧配音质量目标：

- avg speaker_similarity >= `0.45`。
- speaker failed ratio <= `15%`。
- 每个主角色都有稳定 `character_id`。
- DialogueUnit 级翻译通过 backread QA。
- 自动导出前没有 `content_quality=blocked`。

当前还没有达到 Movie-OK。主要短板是 character-level speaker binding 和 TTS clone 后端。

## 4. 实施收益排序

1. **立刻收益：关闭 ASR 字幕导出，使用 movie-safe vNext 音频**  
   避免“人没说话但字幕挂着”的预览级问题。

2. **高确定收益：DialogueUnit + forced alignment**  
   直接解决时间轴和短句误翻，风险低。

3. **高价值但成本高：Qwen3-TTS/F5-TTS tournament**  
   解决音色和可懂度，但需要更长生成时间和缓存。本轮已落地 Qwen clone mode 与 reference tournament 开关，证明“多参考择优”有实际收益。

4. **电影级必须项：视觉 active speaker + Character Registry**  
   解决不同演员复用同一音色的问题，是根治方案。

## 5. 本轮 Dubai 验收口径

本轮执行不把“跑完 pipeline”当成功，而看这些结果：

- 是否生成新的可看视频。
- 是否比 `task-20260429-165133` 少明显字幕/配音错位。
- 是否比 MOSS 输出有更好的 speaker/text 综合指标。
- 是否给出未达标项和下一轮改造方向。
