# Voice Bank 与 Qwen3TTS 本机执行报告

日期：2026-04-22

任务样本：`task-20260421-075513`

## 1. 本次执行范围

本次先落地“更强 speaker reference bank + 本机 TTS 模型可运行性验证”的第一阶段，不直接把 Qwen3TTS 切成生产默认模型。

已完成内容：

1. 新增 Voice Bank 生成能力，从 Task B 的 `speaker_profiles.json` 汇总每个说话人的可用参考音频。
2. 自动生成 composite reference，把同一说话人的多段参考音频拼成更长样本，供后续人工试听和模型 benchmark 使用。
3. 纳入已有 Task D 合成评估结果，给 reference 增加候选质量分、状态计数和风险标记。
4. 新增 CLI 命令 `translip build-voice-bank`，可独立为任意任务生成 voice bank、报告和 manifest。
5. 对 Qwen3TTS 做本机 smoke test，验证这台电脑可以加载模型并完成 1 段合成。
6. 补充单元测试，并跑完整测试集。

## 2. 代码变更

新增：

- `src/translip/dubbing/voice_bank.py`
- `tests/test_voice_bank.py`
- `docs/superpowers/reports/2026-04-22-voice-bank-qwen3tts-execution-report.zh-CN.md`

修改：

- `src/translip/cli.py`
- `tests/test_cli.py`

新增 CLI：

```bash
uv run translip build-voice-bank \
  --profiles <task-b/voice/speaker_profiles.json> \
  --output-dir <task-b/voice> \
  --target-lang en \
  --task-d-report <task-d/voice/<speaker>/speaker_segments.en.json>
```

输出文件：

- `voice_bank.<target_lang>.json`
- `voice_bank_report.<target_lang>.md`
- `voice-bank-manifest.json`
- `reference_bank/<profile_id>/composite_0001.wav`

## 3. Voice Bank 生成结果

样本任务输出目录：

`/Users/masamiyui/.cache/translip/output-pipeline/task-20260421-075513/task-b/voice`

生成文件：

- `/Users/masamiyui/.cache/translip/output-pipeline/task-20260421-075513/task-b/voice/voice_bank.en.json`
- `/Users/masamiyui/.cache/translip/output-pipeline/task-20260421-075513/task-b/voice/voice_bank_report.en.md`
- `/Users/masamiyui/.cache/translip/output-pipeline/task-20260421-075513/task-b/voice/voice-bank-manifest.json`

汇总指标：

| 指标 | 数值 |
| --- | ---: |
| speaker 数 | 8 |
| 有 speaker_id 的 speaker | 5 |
| reference 总数 | 25 |
| source reference | 21 |
| composite reference | 4 |
| 已推荐 reference 的 speaker | 5 |
| 纳入 Task D report 数 | 6 |
| available speaker | 5 |
| needs_speaker_review speaker | 3 |

推荐结果：

| speaker | 状态 | reference 数 | 推荐 reference | 推荐分 | 风险 |
| --- | --- | ---: | --- | ---: | --- |
| `spk_0000` | available | 6 | `profile_0000_clip_0001` | 0.8572 | `long_reference_will_be_trimmed` |
| `spk_0001` | available | 6 | `profile_0001_clip_0001` | 0.8572 | `long_reference_will_be_trimmed` |
| `spk_0002` | available | 6 | `profile_0002_clip_0001` | 0.7980 | `long_reference_will_be_trimmed` |
| `spk_0003` | available | 6 | `profile_0003_clip_0005` | 0.8824 | - |
| `spk_0005` | available | 1 | `profile_0005_clip_0001` | 0.6100 | - |
| `SPEAKER_04` | needs_speaker_review | 0 | - | - | 需人工映射 |
| `SPEAKER_06` | needs_speaker_review | 0 | - | - | 需人工映射 |
| `SPEAKER_07` | needs_speaker_review | 0 | - | - | 需人工映射 |

结论：

1. 这条样本任务已有 5 个 speaker 可以直接进入后续 repair candidate grid。
2. 3 个 speaker 没有稳定 `speaker_id`，问题不在 TTS，而在 speaker attribution，需要先做人工映射或 reference 上传。
3. composite reference 已生成，但当前默认推荐仍优先选择 source reference；原因是 composite 拼接文本与实际音频只能近似对齐，未经 benchmark 前不应自动替代原始参考音频。

## 4. Qwen3TTS 本机 Smoke Test

执行命令：

```bash
uv run translip synthesize-speaker \
  --translation /Users/masamiyui/.cache/translip/output-pipeline/task-20260421-075513/task-c/voice/translation.en.json \
  --profiles /Users/masamiyui/.cache/translip/output-pipeline/task-20260421-075513/task-b/voice/speaker_profiles.json \
  --speaker-id spk_0000 \
  --backend qwen3tts \
  --device auto \
  --max-segments 1 \
  --output-dir /Users/masamiyui/.cache/translip/output-pipeline/task-20260421-075513/_analysis/qwen3tts-smoke
```

输出：

- `/Users/masamiyui/.cache/translip/output-pipeline/task-20260421-075513/_analysis/qwen3tts-smoke/voice/spk_0000/speaker_demo.en.wav`
- `/Users/masamiyui/.cache/translip/output-pipeline/task-20260421-075513/_analysis/qwen3tts-smoke/voice/spk_0000/speaker_segments.en.json`
- `/Users/masamiyui/.cache/translip/output-pipeline/task-20260421-075513/_analysis/qwen3tts-smoke/voice/spk_0000/task-d-manifest.json`

运行结果：

| 项目 | 结果 |
| --- | --- |
| manifest status | `succeeded` |
| backend | `qwen3tts` |
| model | `Qwen/Qwen3-TTS-12Hz-0.6B-Base` |
| resolved device | `cpu` |
| segment count | 1 |
| elapsed | 45.237 秒 |
| overall_status | `review` |
| duration_status | `passed` |
| speaker_status | `review` |
| intelligibility_status | `passed` |
| speaker_similarity | 0.3019 |
| text_similarity | 1.0 |
| duration_ratio | 1.2 |

结论：

1. 这台电脑可以运行 Qwen3TTS，依赖和本地模型缓存可用。
2. 当前自动解析到 CPU，单段耗时约 45 秒，不适合直接跑完整 Task D。
3. 该单段文本可懂度通过，但 speaker similarity 仍为 review，不能仅凭 smoke test 判断音色克隆显著优于现有模型。
4. Qwen3TTS 现阶段适合作为候选 benchmark 后端，不建议直接作为默认生产后端。

## 5. 测试结果

聚焦测试：

```bash
uv run pytest tests/test_voice_bank.py tests/test_cli.py -q
```

结果：

```text
21 passed, 2 warnings
```

全量测试：

```bash
uv run pytest tests -q
```

结果：

```text
166 passed, 4 warnings in 18.00s
```

警告主要来自现有依赖和 FastAPI `on_event` deprecation，不是本次新增代码引入的失败。

## 6. 技术结论

当前最确定的收益来自 Voice Bank，而不是立刻换 TTS 模型。

原因：

1. 现有任务的音色问题有一部分来自 reference 不稳定、speaker attribution 不稳定，而不是单纯 TTS 后端能力不足。
2. Voice Bank 可以把同一 speaker 的多个候选 reference 结构化保存，并结合历史 Task D 评估结果选择更稳的参考音频。
3. Qwen3TTS 可以在本机运行，但当前 CPU 性能不足以直接替代生产链路，需要先做小样本 benchmark 和设备加速确认。
4. 对于 `needs_speaker_review` 的 speaker，任何 TTS 模型都会受到错误 speaker 归因影响，必须先通过人工 review 或 diarization 优化解决。

## 7. 后续建议

短期建议：

1. 将 `voice_bank.en.json` 接入 repair queue 的候选生成逻辑，让每个失败片段优先尝试推荐 reference。
2. 在 Speaker Review UI 中增加 Voice Bank 试听入口，让人工可以比较 source reference 与 composite reference。
3. 对 `needs_speaker_review` speaker 优先做人工映射，不进入自动换模型策略。
4. 为 Qwen3TTS 增加小样本 benchmark 命令，一次只跑每个主要 speaker 的 2 到 3 段，用于比较 speaker similarity、文本可懂度和耗时。

中期建议：

1. 引入多候选重生成：同一 segment 尝试不同 reference、不同 rewrite、不同 TTS backend。
2. 建立 reference benchmark 表，把“哪段 reference 对哪个 speaker 最稳”从经验判断变成数据。
3. 如果 Qwen3TTS 后续能稳定走 MPS 或 GPU 加速，再考虑把它加入生产 fallback，而不是默认主模型。

