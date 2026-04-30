# Dubai 样片自动配音返修执行报告

> 日期：2026-04-30
> 测试视频：`/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/test_video/我在迪拜等你.mp4`
> 主任务：`task-20260430-032858`
> 最终重跑任务：`task-20260430-042735`
> 输出根目录：`/Users/masamiyui/.cache/translip/output-pipeline/task-20260430-032858`

## 1. 本轮结论

本轮最明确的收益是：**“ASR/字幕有，但最终没有配音声音”的问题已在 Dubai 样片上压到 0 个失败字幕窗口**。

最终 Task E 指标：

| 指标 | 最终值 |
| --- | ---: |
| `placed_count` | `194` |
| `skipped_count` | `0` |
| `mix_status_counts.placed_overlap` | `55` |
| `audible_coverage.subtitle_window_count` | `132` |
| `audible_coverage.failed_count` | `0` |
| `audible_coverage.min_coverage_ratio` | `0.5168` |
| `audible_coverage.average_coverage_ratio` | `0.9084` |
| `content_quality.coverage_ratio` | `1.0` |
| `content_quality.status` | `review_required` |

这意味着本轮已经解决了最影响试听的“有字幕但没声音/被 overlap 静音”的问题。仍未达到可自动交付级别，原因是上游 TTS/音色克隆仍有较高失败比例：

| 残留指标 | 最终值 |
| --- | ---: |
| `failed_ratio` | `0.5206` |
| `speaker_failed_ratio` | `0.2216` |
| `intelligibility_failed_ratio` | `0.0619` |
| repair `selected_count` | `1 / 12` |

## 2. 执行过的文档

- 技术方案：`/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/docs/superpowers/specs/2026-04-30-character-ledger-tts-vc-repair-technical-design.zh-CN.md`
- 预期收益：`/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/docs/superpowers/reports/2026-04-30-character-ledger-tts-vc-repair-expected-benefits.zh-CN.md`
- 执行计划：`/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/docs/superpowers/plans/2026-04-30-auto-dub-repair-loop.md`

## 3. 实现内容

### 3.1 自动返修接入 Pipeline

新增 `dub_repair_*` 配置，从 server task config、CLI、orchestration 到 Task E 命令链路全部打通。

Task E 前自动执行：

1. `plan_dub_repair`
2. `run_dub_repair`
3. 读取 `selected_segments.en.json`
4. Task E 优先使用通过质量门的返修音频

本次 repair 队列：

| 指标 | 值 |
| --- | ---: |
| repair items | `12` |
| strict blockers | `12` |
| attempts | `34` |
| selected | `1` |
| manual required | `11` |

### 3.2 Overlap-safe Placement

改造前 Task E 会把较弱 overlap 段直接 `skipped_overlap`，导致字幕窗口完全没有配音。

本轮改为：

- 字幕窗口段优先保留，不允许被后续无字幕窗口的拆分短句替换。
- 短 overlap 使用 `placed_overlap` 低增益叠混。
- failed/review/passed overlap 使用不同衰减，避免重叠段过响。
- 字幕窗口覆盖率按 `placed` 与 `placed_overlap` 统一视为已渲染。

### 3.3 字幕窗口起点与 underflow 修复

新增两类 placement 修复：

- 当字幕开始时间略早于配音锚点时，允许把配音起点前移到字幕开始。
- 当 TTS 生成音频明显过短但仍可拉伸时，使用 atempo 链式 time-scale 扩展到源窗口，避免字幕后半段无声。

最终 `seg-0165` 从低覆盖修复为：

| 字段 | 值 |
| --- | --- |
| `fit_strategy` | `stretch` |
| `generated_duration_sec` | `0.64` |
| `fitted_duration_sec` | `1.19` |
| `subtitle_coverage_ratio` | `0.7879` |
| `notes` | `underflow_stretched`, `tail_trimmed_for:seg-0166` |

## 4. 指标对比

| 阶段 | 任务 | placed | skipped | placed_overlap | audible failed | coverage | 状态 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 旧基线 | `task-20260430-015606` | `166` | `15` | `0` | `8` | `0.9171` | `blocked` |
| 第一轮 Playwright 全流程 | `task-20260430-032858` | `178` | `16` | `8` | `9` | `0.9175` | `blocked` |
| overlap/起点修复后 | `task-20260430-041514` | `179` | `15` | `20` | `6` | `0.9227` | `blocked` |
| 字幕 owner 保留后 | `task-20260430-042247` | `194` | `0` | `55` | `1` | `1.0` | `blocked` |
| underflow 拉伸后 | `task-20260430-042735` | `194` | `0` | `55` | `0` | `1.0` | `review_required` |

关键变化：

- `skipped_overlap`: `15 -> 0`
- `audible_coverage.failed_count`: `8 -> 0`
- `content_quality.status`: `blocked -> review_required`
- `content_quality.reasons` 去掉了 `coverage_below_deliverable_threshold` 和 `audible_coverage_failed`

## 5. Playwright 全流程验证

已通过 Playwright 执行：

1. 从浏览器/API 创建完整任务 `task-20260430-032858`，跑到 `task-g`，生成 ASR 字幕 + 配音成品。
2. 每次后端策略改动后，通过 Playwright 触发从 `task-e` 到 `task-g` 重跑：
   - `task-20260430-041514`
   - `task-20260430-042247`
   - `task-20260430-042735`
3. 最终任务详情页截图：
   - `/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/output/playwright/task-20260430-042735-detail.png`

最终产物：

- ASR 英文字幕：`/Users/masamiyui/.cache/translip/output-pipeline/task-20260430-032858/task-c/voice/translation.en.srt`
- Task E 报告：`/Users/masamiyui/.cache/translip/output-pipeline/task-20260430-032858/task-e/voice/mix_report.en.json`
- Task E 时间线：`/Users/masamiyui/.cache/translip/output-pipeline/task-20260430-032858/task-e/voice/timeline.en.json`
- 预览成品：`/Users/masamiyui/.cache/translip/output-pipeline/task-20260430-032858/task-g/final-preview/final_preview.en.mp4`
- 纯配音质检版：`/Users/masamiyui/.cache/translip/output-pipeline/task-20260430-032858/task-g/final-dub/final_dub.en.mp4`

视频元数据：

| 文件 | 时长 | 视频 | 音频 | 大小 |
| --- | ---: | --- | --- | ---: |
| `final_preview.en.mp4` | `534.593s` | H.264 `960x416` | AAC mono `24000Hz` | `101M` |
| `final_dub.en.mp4` | `534.593s` | H.264 `960x416` | AAC mono `24000Hz` | `98M` |

## 6. Qwen3TTS 试验结论

为了评估是否值得直接换模型，我对 repair 队列最高优先级段 `seg-0092` 做了两次 Qwen3TTS 单段试跑。

### 6.1 Qwen3TTS ICL

| 指标 | 值 |
| --- | --- |
| `speaker_similarity` | `0.4745` |
| `speaker_status` | `passed` |
| `duration_ratio` | `2.286` |
| `text_similarity` | `0.44` |
| `overall_status` | `failed` |

结论：音色相似度有提升，但文本和时长失败，不能自动纳入主流水线。

### 6.2 Qwen3TTS xvec

| 指标 | 值 |
| --- | --- |
| `speaker_similarity` | `0.3182` |
| `speaker_status` | `review` |
| `duration_ratio` | `2.286` |
| `text_similarity` | `0.70` |
| `overall_status` | `failed` |

结论：文本比 ICL 稳一点，音色不如 ICL，仍未通过。当前不建议把 Qwen3TTS 作为全局替换，只适合作为 tournament 候选，并必须经过 backread/duration gate。

## 7. 当前效果判断

可以给用户试听对比，尤其验证“有字幕但没声音”是否明显改善。按指标看，这个问题在 Dubai 样片已达到阶段目标。

不建议宣布“音色克隆已经好”。目前音色/角色一致性仍然是下一轮主问题：

- `speaker_failed_ratio=0.2216`，比旧基线高，说明更多段被保留下来后，上游 TTS 质量问题暴露得更完整。
- `repair selected_count=1/12`，MOSS 返修对内容/音色同步修复能力有限。
- Qwen3TTS 单段试验显示“音色像”和“文本正确/时长合适”仍会互相拉扯。

## 8. 下一轮建议

下一轮不要继续小调 Task E，应转向角色级生成链路：

1. **Character Ledger**：把 `speaker_id` 升级为 `character_id`，加入角色性别、声纹中心、参考音频白名单和人工可修正账本。
2. **Reference Bank 重建**：每个角色选择 3-12 秒单人、清晰、文本可信参考音频，剔除混声/背景音乐/电话声。
3. **TTS/VC Tournament**：同时跑 MOSS、Qwen3TTS ICL/xvec、IndexTTS2/F5-TTS/CosyVoice2 候选；用 backread、speaker similarity、gender consistency、duration fit 选择。
4. **两阶段 TTS + VC**：先生成内容正确的英文，再用 Seed-VC/OpenVoice 类 VC 转角色音色，减少“说错词”和“音色不像”互相牵制。
5. **性别/角色守门**：对主角色加入 gender hint 和声纹聚类一致性，不允许男声/女声明显冲突的候选自动通过。

## 9. 参考来源

- [IndexTTS2 arXiv](https://arxiv.org/abs/2506.21619)
- [IndexTTS project](https://github.com/index-tts/index-tts)
- [F5-TTS arXiv](https://arxiv.org/abs/2410.06885)
- [CosyVoice2 arXiv](https://arxiv.org/abs/2412.10117)
- [Seed-VC GitHub](https://github.com/Plachtaa/seed-vc)
- [pyannote.audio GitHub](https://github.com/pyannote/pyannote-audio)
- [WhisperX paper](https://huggingface.co/papers/2303.00747)
- [AVA-ActiveSpeaker Google Research](https://research.google/pubs/ava-activespeaker-an-audio-visual-dataset-for-active-speaker-detection/)
