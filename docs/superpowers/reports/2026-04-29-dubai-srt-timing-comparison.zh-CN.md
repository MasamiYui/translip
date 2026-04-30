# 《我在迪拜等你》SRT 时间轴实验对比报告

> 日期：2026-04-29  
> 测试视频：`test_video/我在迪拜等你.mp4`  
> 参考字幕：`test_video/我的迪拜等你.srt`  
> Baseline：`tmp/dubai-rerun-v3`，Qwen3TTS + ASR segment 时间轴  
> SRT v2：`tmp/dubai-srt-v2`，严格 SRT 对齐 + SRT-only 补段 + Qwen3TTS

## 1. 结论

SRT v2 验证了路线图里 Milestone 1 的方向是对的：用可靠字幕时间轴可以修正 ASR 文本、补出 ASR 漏掉的对白，并把 `dubbing_window` 传到混音阶段。但本轮结果不能直接作为最终默认方案上线，因为它暴露出两个新问题：

1. SRT-only 补段会显著增加短句和相邻重叠窗口，当前 Task E 的 overlap 处理会跳过一批片段。
2. Qwen3TTS 在补段后的短句/碎片句上 intelligibility 明显变差，整体失败段增加。

所以这次实验的结论不是“直接切到 SRT v2”，而是：**保留 SRT 严格对齐作为 DialogueUnit/Timing Resolver 的输入，但下一步必须先做 DialogueUnit 合并与 overlap-safe mixing，再让 SRT-only 短句进入 TTS。**

## 2. 核心指标

| 指标 | Baseline | SRT v2 | 结论 |
| --- | ---: | ---: | --- |
| 源片段/翻译片段数 | 157 | 197 | SRT v2 补出更多对白 |
| Task D speaker reports | 7 | 8 | SRT v2 多出 `spk_0007` |
| Task E placed | 156 | 157 | 基本持平 |
| Task E skipped | 0 | 40 | SRT v2 因 overlap 跳过 40 段 |
| overall failed | 78 | 105 | SRT v2 变差 |
| speaker passed | 48 | 64 | 音色相似度有改善 |
| speaker failed | 35 | 28 | 音色 hard fail 降低 |
| intelligibility failed | 38 | 84 | 短句补段导致可懂度变差 |
| avg speaker_similarity | 0.3491 | 0.3736 | SRT v2 稍好 |
| avg text_similarity | 0.7923 | 0.6416 | SRT v2 明显差 |
| SRT 窗口 dub_voice > -45 dBFS | 148/171 (86.5%) | 162/171 (94.7%) | SRT v2 可听覆盖提升，但整体质量下降 |

## 3. SRT 对齐效果

- 原始 ASR segment：`157`。
- 参考 SRT 行：`171`。
- 严格对齐后输出 segment：`197`。
- 与 ASR 匹配并修正：`115`。
- 保留 ASR：`42`。
- SRT-only 补段：`40`。

严格 SRT 对齐比直接 OCR correction 更适合人工字幕。直接把 SRT 当 OCR events 时，第一句会被错误合并成“你在哪呢奶奶你知道哈利法塔吗”；严格对齐后变成独立的 `srt-0002` 与 `seg-0001`，避免了明显串句。

## 4. 为什么 SRT v2 没有整体变好

SRT v2 的文本和时间轴更接近字幕，但当前下游还不是 DialogueUnit-aware：

- 40 条 SRT-only 补段进入了翻译/TTS，但很多是极短句，如“乐乐”“迪拜”“是的”。这些片段在 TTS 和 backread 上天然不稳定。
- SRT 行之间常有轻微时间重叠或与 ASR 修正窗口重叠，当前 Task E 会用 overlap resolver 跳过低分候选，造成 `skipped_overlap=40`。
- 当前翻译仍是 M2M100 逐段翻译，不理解剧情上下文，补出的短句会被翻成奇怪碎片，例如 `乐乐 -> pleasure`。
- 当前 Qwen3TTS 每个 speaker 单独加载模型且逐段多候选回读，本地完整跑完耗时很高；这条路线需要模型常驻和批量生成优化。

## 5. 产物路径

| 产物 | Baseline | SRT v2 |
| --- | --- | --- |
| final preview | `/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/tmp/dubai-rerun-v3/task-g/final-preview/final_preview.en.mp4` | `/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/tmp/dubai-srt-v2/task-g/final-preview/final_preview.en.mp4` |
| final dub | `/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/tmp/dubai-rerun-v3/task-g/final-dub/final_dub.en.mp4` | `/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/tmp/dubai-srt-v2/task-g/final-dub/final_dub.en.mp4` |
| dub voice | `/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/tmp/dubai-rerun-v3/task-e/voice/dub_voice.en.wav` | `/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/tmp/dubai-srt-v2/task-e/voice/dub_voice.en.wav` |
| mix report | `/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/tmp/dubai-rerun-v3/task-e/voice/mix_report.en.json` | `/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/tmp/dubai-srt-v2/task-e/voice/mix_report.en.json` |
| corrected segments | baseline raw ASR | `/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/tmp/dubai-srt-v2/asr-ocr-correct/voice/segments.zh.srt-strict.json` |

## 6. 下一步方案

下一轮不应该继续直接把 SRT 行当 TTS segment。正确推进顺序是：

1. 在 SRT strict alignment 后增加 `DialogueUnitBuilder`：把同 speaker、短间隔、语义连续的短句合并成可配音单元。
2. 对 SRT-only 行先进入 `needs_dialogue_unit`，不要直接逐行 TTS。
3. Task E 改成 group-aware placement：同一个 DialogueUnit 内可以内部切分，但不能互相 overlap-skip。
4. 翻译改成 unit-level dubbing script：例如 `乐乐 / 你在哪呢 / 奶奶你知道哈利法塔吗` 应整体翻译和配音，而不是三条短句分别生成。
5. Qwen3TTS backend 需要常驻模型，避免每个 speaker 重载；同时为短句接入更强的 rewrite/merge，而不是继续依赖 backread 淘汰。

## 7. 本轮执行记录

- 成功执行 baseline 导出。
- 成功生成 SRT OCR events：`171` 条。
- 发现并回退了直接 OCR correction 策略，因为它会误合并相邻字幕。
- 成功执行严格 SRT 对齐：输出 `197` 条 segment，其中 `40` 条 SRT-only。
- 成功重跑 Task B/C/D/E/G，Qwen3TTS 全部 speaker 无命令级失败。
- 指标 JSON：`/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/tmp/dubai-srt-v2/comparison_metrics.json`。
