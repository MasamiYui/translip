# task-20260425-023015 配音质量问题分析报告

日期：2026-04-29  
任务目录：`/Users/masamiyui/.cache/translip/output-pipeline/task-20260425-023015`  
输入视频：`/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/test_video/我在迪拜等你.mp4`  
工作流：`asr-dub+ocr-subs`  
TTS：`moss-tts-nano-onnx`  
翻译：`local-m2m100`  

## 结论

这个任务的问题不是单点故障，而是三个阶段叠加导致：

1. **说话人识别/聚类不稳定**：Task A 日志显示 speaker clustering 先产生了 `50 clusters / 64 embedding groups`，随后被强制重聚类到 `cap=8`。这说明自动 speaker id 更像“音频聚类标签”，不是稳定的人物角色标签。
2. **Task D 生成前已经丢了 6 段**：翻译阶段有 192 段、8 个 speaker；Task D 只生成了 186 段、7 个 speaker。`spk_0002` 的 6 段完全没有进入配音报告，最终纯配音轨在这些字幕窗口为数字静音。
3. **TTS 音色克隆和时长控制质量不足**：186 个 Task D 段里只有 5 个 overall passed；speaker 相似度仅 15 段 passed，33 段 failed，138 段 review。Task E 又因为时长/重叠跳过 22 段，导致 18 个字幕窗口可听覆盖失败。

最终 Task G 虽然 `succeeded`，但 `content_quality.status=blocked`，原因包括：

- `coverage_below_deliverable_threshold`
- `upstream_failed_segments`
- `speaker_similarity_failed`
- `audible_coverage_failed`

因此用户感知到的“人物音色不对”和“语音丢失”是成立的。

## 关键指标

| 阶段 | 指标 | 结果 |
| --- | ---: | ---: |
| Task A | ASR 段数 | 192 |
| Task A | speaker 数 | 8 |
| Task A | speaker 聚类 | 50 clusters / 64 groups，重聚类 cap=8 |
| ASR-OCR Correct | corrected | 141 |
| ASR-OCR Correct | review | 27 |
| ASR-OCR Correct | OCR-only | 8，策略为 `report_only` |
| Task C | 翻译段数 | 192 |
| Task C | `duration_risky` | 56 |
| Task C | `duration_may_overrun` | 25 |
| Task D | 生成段数 | 186 |
| Task D | overall passed/review/failed | 5 / 98 / 83 |
| Task D | speaker passed/review/failed | 15 / 138 / 33 |
| Task D | duration passed/review/failed | 93 / 44 / 49 |
| Task E | placed/skipped | 164 / 22 |
| Task E | audible coverage failed | 18 |
| Task G | content status | blocked |

## 语音丢失：直接原因

### 1. `spk_0002` 未进入 Task D

Task C 里 `spk_0002` 有 6 段，但 Task D stage manifest 的 report 列表没有 `spk_0002`：

- `seg-0013`
- `seg-0072`
- `seg-0078`
- `seg-0083`
- `seg-0106`
- `seg-0107`

这些段在最终纯配音轨 `task-e/voice/dub_voice.en.wav` 的字幕窗口 RMS 都是 `-120.0 dBFS`，等同数字静音。

| Segment | 时间 | 中文 | 英文 | 字幕窗口 RMS |
| --- | ---: | --- | --- | ---: |
| `seg-0013` | 70.909-73.182 | 三分钟之后停车场见 | After three minutes, we saw the parking lot. | -120.0 dBFS |
| `seg-0072` | 196.818-197.727 | 把篷打开 | Open the cage. | -120.0 dBFS |
| `seg-0078` | 224.091-233.909 | 我来为您服务先等一下 | I will wait for you first. | -120.0 dBFS |
| `seg-0083` | 242.727-243.227 | 这边请 | Please here. | -120.0 dBFS |
| `seg-0106` | 319.318-320.227 | 对不起我弄错了 | Sorry I was wrong. | -120.0 dBFS |
| `seg-0107` | 320.520-332.080 | 奶奶 | The grandmother | -120.0 dBFS |

代码原因在 `src/translip/dubbing/planning.py`：

- `pick_task_d_speaker_ids()` 只统计 `is_usable_task_d_segment()` 通过的 speaker。
- `is_usable_task_d_segment()` 要求 `1.0 <= duration_sec <= 6.0`，且不能带 `too_short_source`。
- `spk_0002` 的 6 段 ASR 时长分别是 `34.91 / 20.03 / 11.95 / 8.90 / 17.94 / 11.56` 秒，全部超过 6 秒或带 `too_short_source`。
- 结果是 `usable_counts["spk_0002"] == 0`，整个 speaker 被跳过。

这里的根因不是 `spk_0002` 真有 105 秒有效台词，而是 ASR/diarization 时间窗被拉得过长。例如 `seg-0013` 原始 ASR 窗口是 `37.94-72.85`，但 OCR 字幕窗口只有 `70.909-73.182`。

### 2. Task E overlap 策略跳过了 22 段

Task E 的 `mix_report.en.json` 显示：

- `placed_count=164`
- `skipped_count=22`
- `skip_reason_counts.skipped_overlap=22`

其中 12 段有 `subtitle_window_not_rendered` 和 `subtitle_window_not_covered`，表示本段台词没有按自己的字幕窗口渲染。典型段：

| Segment | Speaker | 中文 | 英文 | 结果 |
| --- | --- | --- | --- | --- |
| `seg-0010` | spk_0001 | 我现在就要去迪拜了 | I am going to Dubai now. | skipped，replaced_by `seg-0011` |
| `seg-0087` | spk_0004 | 一会儿带你去吃阿拉伯餐 | Take you to the Arab meal. | skipped，replaced_by `seg-0088` |
| `seg-0108` | spk_0001 | 奶奶这个就是我跟你说 | My grandmother, that’s what I told you. | skipped，replaced_by `seg-0109` |
| `seg-0149` | spk_0006 | 我们之间哪不合适你跟我说 | What is not right between us, you tell me. | skipped，replaced_by `seg-0150` |
| `seg-0166` | spk_0000 | 你就当在那旅游一趟 | You are on that trip. | skipped，replaced_by `seg-0167` |
| `seg-0186` | spk_0006 | 反正不管你走到天涯海角 | No matter what you are going to the coast of the world. | skipped，replaced_by `seg-0187` |

这些窗口不一定完全静音，因为相邻段的音频可能覆盖到了同一时间段；但从台词层面看，当前 segment 的英文配音确实被跳过或替换了。

### 3. OCR-only 字幕没有进入配音脚本

ASR-OCR correction 报告里有 8 个 `ocr_only_events`，策略是 `report_only`：

- `创业`
- `小莉`
- `终于找到你了`
- `我求求你别来烦我了`
- `我们不合适`
- `我妈说了`
- `感情是需要磨合的`
- `我妈还说`

这些 OCR 字幕会出现在 OCR 字幕/翻译产物中，但不会新增为 Task C/Task D 的配音段。若最终字幕使用 OCR 事件，用户会看到字幕但听不到对应英文配音。

## 音色对不上：直接原因

### 1. Speaker id 不是人物级角色

Task A 使用 speechbrain embedding 做聚类。日志里出现：

```text
Speaker clustering produced 50 clusters for 64 embedding groups. Re-clustering with cap=8.
```

这表示原始相似度阈值下音频被切成了很多簇，系统为了控制 speaker 数量强行压到 8 个。压缩后每个 `spk_xxxx` 不能等同于真实人物。

后续 Task B 只把这些自动聚类结果注册成 speaker profile，没有人工角色映射。因此后面所有 voice clone 都依赖这个不稳定标签。

### 2. Reference clip 质量和选择不足

Voice bank 报告虽然显示 8 个 speaker 都 `available`，但多个 reference 有风险：

- `spk_0000`、`spk_0002`、`spk_0003`、`spk_0007` 被标记 `long_reference_will_be_trimmed`。
- `spk_0002` 的参考片段来自很长 ASR 窗口，但文本只有短句，例如 `224.06-236.01` 的文本是“我来为您服务先等一下”，`320.52-332.08` 的文本只有“奶奶”。这说明 reference 里可能混入大量非目标语音、静音、背景或错位内容。

### 3. MOSS-TTS-Nano 的克隆相似度不达标

Task D 的 speaker similarity 阈值是：

- `>=0.45` passed
- `0.25-0.45` review
- `<0.25` failed

本任务整体：

- 平均 speaker similarity：`0.3211`
- speaker passed：`15/186`
- speaker review：`138/186`
- speaker failed：`33/186`

按 speaker 看，质量最差的是：

| Speaker | 段数 | speaker failed | 平均 speaker similarity |
| --- | ---: | ---: | ---: |
| spk_0005 | 5 | 4 | 0.170 |
| spk_0006 | 17 | 11 | 0.204 |
| spk_0000 | 28 | 3 | 0.326 |
| spk_0001 | 65 | 11 | 0.334 |
| spk_0003 | 24 | 2 | 0.325 |
| spk_0004 | 45 | 2 | 0.357 |

这说明“音色对不上”不只是 speaker 识别问题；就算 speaker/ref 选对，当前 TTS 后端也经常无法稳定贴近参考音色。

Task D 的 retry 原因也支持这个判断：

- `poor_speaker_match`: 79
- `pathological_duration`: 55
- `poor_backread`: 19

## 时长和翻译进一步放大问题

Task C 配置为 `condense_mode=off`，没有做英文改写压缩。结果：

- `duration_risky=56`
- `duration_may_overrun=25`
- `too_short_source=27`

Task D 里有 49 段 duration failed。部分段出现明显病理时长：

- `seg-0074`：`Good Morning`，生成时长/source 时长比 `30.4x`
- `seg-0173`：`The dream of independence.`，比例 `10.87x`
- `seg-0089`：`Happy mom mom mom mom mom mom mom`，比例 `7.143x`
- `seg-0149`：`What is not right between us, you tell me.`，比例 `5.214x`

这些过长音频进入 Task E 后会造成压缩、裁剪、相邻段覆盖或 overlap 跳过，最终表现为某些字幕处没有正确台词、或台词被前后段抢占。

## 分阶段根因归类

| 问题 | 所属阶段 | 证据 | 影响 |
| --- | --- | --- | --- |
| speaker 聚类不稳定 | Task A | 50 clusters 被压到 cap=8 | speaker id 不等于真实人物 |
| ASR 时间窗过长 | Task A / ASR-OCR correction | `spk_0002` 多个短台词被标成 8.9-34.91 秒 | Task D 规划跳过整个 speaker |
| OCR-only 不进配音脚本 | ASR-OCR correction | 8 个 `ocr_only_events`，`report_only` | 字幕有内容但没有配音段 |
| 翻译/改写未控时长 | Task C | `duration_risky=56`，`condense_mode=off` | TTS 过长，后续压缩/重叠 |
| TTS 音色克隆弱 | Task D | speaker passed 15/186，平均相似度 0.321 | 大量人物音色不对 |
| overlap 策略丢台词 | Task E | 22 skipped_overlap，18 coverage failed | 某些字幕窗口没有对应英文台词 |
| 交付未阻断成功状态 | Task G | pipeline succeeded，但 content blocked | UI/任务状态容易误导验收 |

## 建议

### P0：先修“丢段”

1. Task D 调度不能因为 `usable_counts == 0` 跳过整个 speaker。对这种 speaker 应至少走 fallback：
   - 使用 `dubbing_window` 或 `subtitle_window` 时长判断可配音性；
   - 对长 ASR 窗口但短 OCR 字幕的段，按 OCR/dubbing window 生成；
   - 对确实不可用的 speaker 写入显式 skipped report，让 Task E/Task G 能统计为缺段。
2. `ocr_only_policy=report_only` 不适合作为配音交付默认策略。需要提供：
   - `promote_to_dubbing_segment`；
   - 或在最终报告中明确列为“字幕有、配音无”的阻断项。
3. Task E 的 overlap 不能只用 quality_score 取舍。对带 subtitle_window 的短台词，应优先保证每个字幕窗口有自己的音频覆盖；无法同时覆盖时应进入 repair 队列，而不是静默替换。

### P1：再修音色

1. 加入 speaker review/角色映射，把自动 `spk_xxxx` 合并或改名成真实角色。
2. Reference 选择增加硬过滤：
   - 排除过长 ASR 窗口；
   - 排除低 RMS/高背景/多说话人片段；
   - 优先使用 3-8 秒、单人、干净 reference。
3. 对每个 speaker 不要只用单一 reference，保留候选池并按 Task D speaker similarity 回写 reference 排名。
4. MOSS-TTS-Nano 只能作为流程验证后端；成片级质量建议加入更强 voice clone/expressive TTS 后端，并做多候选选择。

### P2：修时长和可懂度

1. 默认开启英文 dubbing rewrite/condense，至少处理 `duration_risky` 与 `duration_may_overrun`。
2. 对短 source window 禁止生成过长音频；超过上限时重写文本或重试 TTS，而不是直接进入 Task E。
3. Repair 队列优先处理：
   - `speaker_status=failed`
   - `duration_status=failed`
   - `mix_status=skipped_overlap`
   - `subtitle_coverage_ratio < 0.5`

## 最终判断

`task-20260425-023015` 当前不能作为可交付配音结果。  

最直接的语音缺失来自 Task D 漏生成 `spk_0002` 的 6 段，以及 Task E overlap 跳过 22 段。音色不对则由 speaker 聚类不稳定、reference 质量不足、MOSS-TTS-Nano 克隆相似度低共同造成。修复顺序应先保证每条字幕有对应配音，再做角色级 speaker review 和 TTS 候选优化。
