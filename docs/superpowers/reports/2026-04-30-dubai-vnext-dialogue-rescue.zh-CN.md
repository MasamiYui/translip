# Dubai vNext Dialogue Rescue 对比报告

> 日期：2026-04-30  
> 测试视频：`test_video/我在迪拜等你.mp4`  
> Baseline：`tmp/dubai-rerun-v3`  
> SRT v2：`tmp/dubai-srt-v2`  
> vNext：`tmp/dubai-vnext-windowed`

## 1. 结论

vNext-windowed 是本轮最好的可交付版本：它保留 baseline 的稳定主体，只把 SRT v2 中可听的弱窗口切片补回去，同时拒绝明显坏短句。覆盖率接近 SRT v2，但没有继承 SRT v2 的 40 段 overlap skip。

这不是最终形态的“大重构”，但它验证了一个关键收益点：**配音链路需要候选级/窗口级选择器，不能把某一种转录或某一种 TTS 结果整包接受。** 后续真正的大重构应该把这个选择器前移到 DialogueUnit 级别，让 ASR/SRT/视觉说话人/TTS 候选都进入同一个评分与回退框架。

## 2. 核心指标

| 指标 | Baseline | SRT v2 | vNext-windowed | 结论 |
| --- | ---: | ---: | ---: | --- |
| SRT 窗口可听 `> -45 dBFS` | 148/171 (86.5%) | 162/171 (94.7%) | 161/171 (94.2%) | vNext 比 baseline 多 13 个窗口，接近 SRT v2 |
| Task E placed / rescue | 156 | 157 | 156 + 13 | vNext 是 baseline 主体 + 13 个窗口救援 |
| overlap skip | 0 | 40 | 0 | vNext 不引入 SRT v2 的 overlap skip |
| overall failed | 78 | 105 | 86 | vNext 只因新增 rescue 计数略升，远低于 SRT v2 |
| intelligibility failed | 38 | 84 | 43 | vNext 接近 baseline，明显优于 SRT v2 |
| avg text_similarity | 0.7923 | 0.6416 | 0.7867 | vNext 保住 baseline 文本稳定性 |
| avg speaker_similarity | 0.3491 | 0.3736 | 0.3522 | vNext 没有解决音色上限，只是避免恶化 |

## 3. 本轮 vNext 做了什么

- 保留 baseline 的完整 `dub_voice.en.wav` 作为稳定主体。
- 找出 baseline 中 SRT 窗口低于 `-45 dBFS` 的 23 个弱/静音窗口。
- 从 SRT v2 的完整 `dub_voice.en.wav` 中切出对应窗口，叠加到 baseline。
- 对明显坏短句做保护：本轮拒绝了 `4` 个坏短句/坏名字翻译，例如 `乐乐 -> pleasure`、`喂 -> Hye`。
- 最终补入 `13` 个窗口，覆盖从 `148` 提升到 `161`。

## 4. 被补入的窗口

| SRT event | 来源段 | 英文音频文本 | 状态 | speaker sim | text sim |
| --- | --- | --- | --- | ---: | ---: |
| srt-0002 | srt-0002 | Where are you. | failed | 0.2201 | 1.0000 |
| srt-0029 | srt-0029 | Goodbye goodbye | review | 0.6341 | 0.7358 |
| srt-0038 | srt-0038 | Hey Hey | review | 0.2751 | 1.0000 |
| srt-0079 | seg-0080 | Mom, mom and grandmother, I’ve been to Dubai. | failed | 0.5087 | 0.6588 |
| srt-0080 | seg-0080 | Mom, mom and grandmother, I’ve been to Dubai. | failed | 0.5087 | 0.6588 |
| srt-0110 | seg-0101 | The Halifa Tower | failed | 0.2458 | 1.0000 |
| srt-0129 | srt-0129 | Little Lily | failed | 0.3661 | 0.2000 |
| srt-0130 | srt-0130 | I finally found you. | review | 0.3616 | 1.0000 |
| srt-0132 | srt-0132 | We are not suitable. | failed | 0.6162 | 0.2222 |
| srt-0137 | srt-0137 | Emotions need to be mixed. | review | 0.3817 | 1.0000 |
| srt-0138 | srt-0138 | My mom also said. | review | 0.2725 | 0.8182 |
| srt-0139 | seg-0123 | Girls deal with emotions. | failed | 0.5130 | 0.3243 |
| srt-0164 | seg-0149 | Don’t get home for money. | failed | 0.1723 | 0.7333 |

## 5. 产物路径

| 产物 | 路径 |
| --- | --- |
| vNext preview | `tmp/dubai-vnext-windowed/task-g/final-preview/final_preview.en.mp4` |
| vNext final dub | `tmp/dubai-vnext-windowed/task-g/final-dub/final_dub.en.mp4` |
| vNext dub voice | `tmp/dubai-vnext-windowed/task-e/voice/dub_voice.en.wav` |
| vNext mix report | `tmp/dubai-vnext-windowed/task-e/voice/mix_report.en.json` |
| comparison metrics | `tmp/dubai-vnext-windowed/comparison_metrics.json` |

## 6. 下一步

这版已经有确定收益，但还不是我认为的最终好结果。下一步应该继续大胆重构到 DialogueUnit 级：

1. 用 `DialogueUnitBuilder` 把短 SRT/ASR 行合并后再翻译和 TTS，不再靠窗口切片补丁。
2. 对 `乐乐`、`小丽`、`奶奶` 这类角色名/称谓加入人物词典，避免机器翻译成普通名词。
3. 让 Qwen3TTS/F5-TTS 作为候选后端同时生成，使用 backread + speaker similarity + duration fit 选最佳 take。
4. 引入视觉 active speaker/人脸轨迹，把 `speaker_id` 升级为 `character_id`，从根上减少音色对错人的问题。
