# 哪吒预告片配音质量修复结论报告

日期：2026-04-25  
输入视频：`/Users/masamiyui/Downloads/哪吒预告片.mp4`  
本次验证任务：`/Users/masamiyui/.cache/translip/output-pipeline/task-20260425-014929`  
原问题任务：`/Users/masamiyui/.cache/translip/output-pipeline/task-20260424-094948`

## 结论

本次修复解决了“部分桥段看字幕时没有英文配音”的主问题。

复查后可以确认，原问题不是 Task D 没有生成英文音频，而是渲染阶段把英文配音锚定在 ASR 起点，导致部分英文在硬字幕出现前已经播放完。典型场景是 ASR 段很长、OCR 硬字幕很晚才出现，例如原任务里 `seg-0006`、`seg-0021`、`seg-0030` 的 OCR 字幕窗口在最终纯配音轨里接近数字静音。

修复后，OCR 校正产物会写入字幕时间窗和配音时间窗，Task E 会按 `dubbing_window` 放置配音，并统计每个字幕窗口的可听覆盖率。新任务跑完后：

- Task D 生成英文配音 wav：`30/30`
- Task E 放置：`30/30`
- Task E 跳过：`0`
- OCR 字幕窗口覆盖失败：`0`
- OCR 字幕窗口最小覆盖率：`0.7176`
- OCR 字幕窗口平均覆盖率：`0.9512`
- 6 个 `late_ocr_anchor` 晚字幕窗口均检测到非静音英文配音

最终视频已导出：

- Preview：`/Users/masamiyui/.cache/translip/output-pipeline/task-20260425-014929/task-g/final-preview/final_preview.en.mp4`
- Dub：`/Users/masamiyui/.cache/translip/output-pipeline/task-20260425-014929/task-g/final-dub/final_dub.en.mp4`

## 关键修复

1. OCR 校正不再只替换文本

文件：`src/translip/transcription/ocr_correction.py`

新增 `timing` 元数据：

- `asr_window`
- `ocr_window`
- `subtitle_window`
- `dubbing_window`
- `warnings`

当 OCR 字幕明显晚于 ASR 起点时，系统会使用 `late_ocr_anchor`，把配音起点移动到 OCR 起点前的安全预卷位置。

2. Task E 按配音窗口渲染

文件：`src/translip/rendering/runner.py`

Task E 现在优先读取 `timing.dubbing_window`，而不是盲目使用 ASR `start/end`。Timeline 中新增：

- `anchor_source`
- `subtitle_window`
- `subtitle_coverage_ratio`
- `dubbing_window_policy`

3. 增加 audible coverage 质检

文件：`src/translip/rendering/export.py`

Mix report 新增 `stats.audible_coverage`。如果某个字幕窗口没有被最终配音轨覆盖，`content_quality` 会加入 `audible_coverage_failed` 并阻断交付质量。

4. 修复 review 段抢占 OCR 时间窗

本次真实跑测暴露出一个细节问题：如果一个 OCR 事件同时被短 ASR 片段和完整 ASR 片段命中，短片段即使进入 `review`，也不应该声明这个 OCR 的配音时间窗。现在只有真正 `use_ocr/merge_ocr` 的段才会写入 OCR timing。

5. 清理未请求的旧 final dub

文件：`src/translip/delivery/runner.py`、`src/translip/delivery/export.py`

当 `export_dub=false` 时：

- manifest/report 不再写入 dub audio 路径
- 清理同输出目录下旧的 `final_dub.<lang>.*`

这可以避免旧成品文件误导验收。

## 跑测结果

### Pipeline

Playwright 从浏览器完整创建并跑完任务，所有节点成功：

- `stage1`
- `ocr-detect`
- `task-a`
- `asr-ocr-correct`
- `task-b`
- `task-c`
- `ocr-translate`
- `task-d`
- `task-e`
- `task-g`

状态：`succeeded`

### Task E 指标

```json
{
  "placed": 30,
  "skipped": 0,
  "audible_coverage": {
    "subtitle_window_count": 29,
    "failed_count": 0,
    "failed_segment_ids": [],
    "min_coverage_ratio": 0.7176,
    "average_coverage_ratio": 0.9512
  },
  "content_quality": {
    "status": "review_required",
    "coverage_ratio": 1.0,
    "failed_ratio": 0.4667,
    "speaker_failed_ratio": 0.1,
    "intelligibility_failed_ratio": 0.3333,
    "reasons": [
      "upstream_failed_segments",
      "intelligibility_failed"
    ]
  }
}
```

### OCR 晚字幕窗口 RMS 抽检

对最终 `dub_voice.en.wav` 按 OCR 字幕窗口测 RMS，6 个 `late_ocr_anchor` 段均非数字静音：

| Segment | OCR Window | RMS dB |
|---|---:|---:|
| `seg-0014` | `38.5-40.0` | `-24.21` |
| `seg-0017` | `51.499-54.999` | `-32.11` |
| `seg-0019` | `57.749-58.749` | `-19.49` |
| `seg-0020` | `59.999-61.249` | `-39.36` |
| `seg-0021` | `66.999-69.999` | `-25.56` |
| `seg-0028` | `84.749-85.249` | `-57.33` |

## 与原任务对比

| 指标 | 原任务 `task-20260424-094948` | 新任务 `task-20260425-014929` |
|---|---:|---:|
| Pipeline 状态 | succeeded | succeeded |
| Task E placed | 31 | 30 |
| Task E skipped | 0 | 0 |
| 字幕窗口覆盖 QA | 无 | 有 |
| 字幕窗口覆盖失败 | 无法自动发现 | 0 |
| overall failed | 18/31 | 14/30 |
| speaker failed | 5/31 | 3/30 |
| intelligibility failed | 5/31 | 10/30 |
| content status | review_required | review_required |

注意：新任务从 OCR/ASR 校正后合并为 30 个有效配音段，而原任务是 31 个段。新任务的主要改进是“每个应有配音的字幕窗口都有英文声音”；整体音色/可懂度仍未达到可直接交付的标准。

## 剩余问题

本次修复的目标是解决“桥段没有英文配音/字幕窗口静音”。这个目标已经达成。

但最终 `content_quality.status` 仍是 `review_required`，原因是：

- `overall failed`: `14/30`
- `intelligibility failed`: `10/30`
- `duration failed`: `8/30`
- `speaker failed`: `3/30`

这些主要来自 TTS 合成质量、英文翻译/改写长度、回听 ASR 可懂度、音色相似度，而不是缺段或放置错误。典型症状包括：

- 英文文本太长，被压缩或裁剪后可懂度下降
- MOSS-TTS 在部分短句/情绪句上发音不稳定
- speaker clustering 仍然偏“时间块聚类”，不是真实角色级识别
- 语气、角色音色和电影预告片风格仍不稳定

## 建议下一步

1. 对 `failed/review` 段跑自动修复队列

优先处理：

- `intelligibility_status=failed`
- `duration_status=failed`
- `speaker_status=failed`

策略：

- 更短英文改写
- 每段多候选 TTS
- reference clip 重新选择
- 用 Task E 的 subtitle coverage 作为硬门槛

2. 替换或扩展 TTS 后端

MOSS-TTS 可以完成流程验证，但要达到成片效果，需要更强的 voice clone / expressive TTS。建议继续接入候选池：

- Qwen3TTS
- F5-TTS / E2-TTS 类 flow-matching TTS
- CosyVoice2
- Chatterbox / Seed-VC 作为音色迁移候选

3. 做角色级 speaker review

当前 speaker id 仍然更像自动聚类结果。建议加入角色级人工确认或半自动合并：

- 哪吒
- 敖丙
- 父王
- 旁白/群体

这样可以明显提升音色克隆稳定性。

## 验证命令

后端全量测试：

```bash
uv run pytest -q
```

结果：

```text
178 passed, 4 warnings in 16.50s
```

浏览器端到端：

- 使用 Playwright 打开 `http://127.0.0.1:5173/tasks/new`
- 通过 UI 创建任务
- 输入 `/Users/masamiyui/Downloads/哪吒预告片.mp4`
- 选择带 OCR 的双语审片工作流
- 等待任务跑到 `task-g`
- 任务最终状态：`succeeded`

最后一次页面/API 校验：

```text
api_status succeeded
current_stage task-g
last_export_files 2
```

## 最终判断

本轮修复已经把“英文配音缺失/字幕窗口静音”从不可观测问题变成了可检测、可阻断、可验证的问题，并在《哪吒预告片.mp4》完整浏览器工作流中验证通过。

当前系统仍不能算“最终成片质量达标”，但已经从“链路有结构性错位”推进到“链路完整，剩余问题集中在 TTS/翻译改写/音色质量”。下一阶段应集中做配音候选池、失败段自动修复和角色级 speaker review。
