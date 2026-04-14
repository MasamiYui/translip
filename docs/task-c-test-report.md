# 任务 C 测试报告: 多语种翻译脚本生成

- 项目: `translip`
- 测试日期: 2026-04-12
- 对应设计文档: [task-c-dubbing-script-generation.md](/Users/masamiyui/OpenSoureProjects/Forks/translip/docs/task-c-dubbing-script-generation.md)

## 1. 本轮实现范围

本轮任务 C 已实现并验证以下能力:

- 本地翻译后端: `facebook/m2m100_418M`
- 第三方 API 后端: `SiliconFlow`
- 段级翻译导出
- `translation.<target_tag>.json`
- `translation.<target_tag>.editable.json`
- `translation.<target_tag>.srt`
- 时长预算和风险标记
- glossary 预处理与单术语强制归一化
- 简单的 A -> B -> C 串行脚本

## 2. 自动测试

执行命令:

```bash
uv run pytest -q
```

结果:

- `25 passed`

覆盖范围:

- CLI 参数解析
- context unit 分组
- glossary 预处理
- glossary 单术语目标归一化
- SiliconFlow JSON 响应解析
- 时长预算判定
- 任务 C 导出物结构

## 3. 本地后端验证

### 3.1 小样本 smoke test

输入:

- `output-task-a/voice/segments.zh.json` 前 12 条
- `output-task-b/voice/speaker_profiles.json`
- glossary: [config/glossary.example.json](/Users/masamiyui/OpenSoureProjects/Forks/translip/config/glossary.example.json)

执行命令:

```bash
uv run translip translate-script \
  --segments ./tmp/task-c-smoke/segments.zh.json \
  --profiles ./tmp/task-c-smoke/speaker_profiles.json \
  --target-lang en \
  --backend local-m2m100 \
  --device auto \
  --batch-size 4 \
  --glossary ./config/glossary.example.json \
  --output-dir ./tmp/output-task-c-smoke
```

结果:

- 成功输出 `translation.en.json`
- 成功输出 `translation.en.editable.json`
- 成功输出 `translation.en.srt`
- 首次真实加载模型耗时约 `131.873s`
- 缓存后复跑耗时约 `23.422s`

观察:

- `M2M100` 在 `MacBook M4 16GB` 上可运行，实际解析到 `mps`
- glossary 对 `Burj Khalifa`、`Dubai` 这类单术语句段有明显帮助
- 本地译文整体偏保守、偏字面
- ASR 错字仍会污染翻译结果

### 3.2 单术语归一化修复

本轮真实测试中暴露了一个问题:

- 单独一句 `迪拜`
- 本地后端会产出 `The Dubai`

已修复:

- 当句段本身就是 glossary 单术语时，直接强制回写 glossary 目标词

修复后:

- `迪拜` -> `Dubai`
- `哈里巴塔` -> `Burj Khalifa`

## 4. SiliconFlow API 验证

### 4.1 小样本 smoke test

输入:

- 前 6 条句段
- 模型: `deepseek-ai/DeepSeek-V3`

结果:

- 成功输出 `translation.en.json`
- 成功解析 JSON 返回
- 总耗时约 `12.37s`

观察:

- API 译文自然度明显优于本地 `M2M100`
- 初版 prompt 存在过度脑补问题
- 在 ASR 错字句段上会擅自联想电影或实体

已修复:

- 强化系统提示，要求“保守翻译，不补上下文”
- 去掉请求里的整段上下文输入，避免放大 ASR 噪声

### 4.2 扩大样本验证

输入:

- 前 20 条句段
- 模型: `deepseek-ai/DeepSeek-V3`

结果:

- `segment_count = 20`
- `unit_count = 8`
- `speaker_count = 3`
- `elapsed_sec = 74.215`
- 成功覆盖多批次调用与多 unit 导出

结论:

- SiliconFlow 后端已达到可用状态
- 当前实现适合作为质量更高的可选翻译后端
- 密钥未写入仓库，只通过环境变量读取

## 5. 真实视频端到端验证

### 5.1 执行方式

新增脚本:

- [scripts/run_task_a_to_c.py](/Users/masamiyui/OpenSoureProjects/Forks/translip/scripts/run_task_a_to_c.py)

执行命令:

```bash
uv run python scripts/run_task_a_to_c.py \
  --input ./test_video/我在迪拜等你.mp4 \
  --output-root ./tmp/e2e-task-a-to-c-local \
  --target-lang en \
  --translation-backend local-m2m100 \
  --device auto
```

### 5.2 Stage 1 结果

产物:

- [voice.mp3](/Users/masamiyui/OpenSoureProjects/Forks/translip/tmp/e2e-task-a-to-c-local/stage1/我在迪拜等你/voice.mp3)
- [background.mp3](/Users/masamiyui/OpenSoureProjects/Forks/translip/tmp/e2e-task-a-to-c-local/stage1/我在迪拜等你/background.mp3)
- [manifest.json](/Users/masamiyui/OpenSoureProjects/Forks/translip/tmp/e2e-task-a-to-c-local/stage1/我在迪拜等你/manifest.json)

统计:

- 输入时长 `534.636s`
- 后端 `cdx23`
- 总耗时 `402.787s`

### 5.3 任务 A 结果

产物:

- [segments.zh.json](/Users/masamiyui/OpenSoureProjects/Forks/translip/tmp/e2e-task-a-to-c-local/task-a/voice/segments.zh.json)
- [segments.zh.srt](/Users/masamiyui/OpenSoureProjects/Forks/translip/tmp/e2e-task-a-to-c-local/task-a/voice/segments.zh.srt)
- [task-a-manifest.json](/Users/masamiyui/OpenSoureProjects/Forks/translip/tmp/e2e-task-a-to-c-local/task-a/voice/task-a-manifest.json)

统计:

- `segment_count = 170`
- `speaker_count = 7`
- `elapsed_sec = 77.592`

### 5.4 任务 B 结果

产物:

- [speaker_profiles.json](/Users/masamiyui/OpenSoureProjects/Forks/translip/tmp/e2e-task-a-to-c-local/task-b/voice/speaker_profiles.json)
- [speaker_matches.json](/Users/masamiyui/OpenSoureProjects/Forks/translip/tmp/e2e-task-a-to-c-local/task-b/voice/speaker_matches.json)
- [speaker_registry.json](/Users/masamiyui/OpenSoureProjects/Forks/translip/tmp/e2e-task-a-to-c-local/task-b/voice/speaker_registry.json)
- [task-b-manifest.json](/Users/masamiyui/OpenSoureProjects/Forks/translip/tmp/e2e-task-a-to-c-local/task-b/voice/task-b-manifest.json)

统计:

- `profile_count = 7`
- `registry_speaker_count = 7`
- `match_decisions = { new_speaker: 7 }`
- `elapsed_sec = 2.321`

说明:

- 这次是真实新 registry，因此首次全是 `new_speaker`，属于预期结果

### 5.5 任务 C 结果

产物:

- [translation.en.json](/Users/masamiyui/OpenSoureProjects/Forks/translip/tmp/e2e-task-a-to-c-local/task-c/voice/translation.en.json)
- [translation.en.editable.json](/Users/masamiyui/OpenSoureProjects/Forks/translip/tmp/e2e-task-a-to-c-local/task-c/voice/translation.en.editable.json)
- [translation.en.srt](/Users/masamiyui/OpenSoureProjects/Forks/translip/tmp/e2e-task-a-to-c-local/task-c/voice/translation.en.srt)
- [task-c-manifest.json](/Users/masamiyui/OpenSoureProjects/Forks/translip/tmp/e2e-task-a-to-c-local/task-c/voice/task-c-manifest.json)

统计:

- `translation_backend = local-m2m100`
- `device = mps`
- `segment_count = 170`
- `unit_count = 55`
- `speaker_count = 7`
- `glossary_match_count = 7`
- `duration_fit_counts = { fit: 96, review: 29, risky: 45 }`
- `elapsed_sec = 102.693`

结论:

- 从 `test_video/我在迪拜等你.mp4` 到任务 C 全链路已跑通
- 本地 `M2M100` 在目标机器上可完成真实视频翻译任务

## 6. 当前结论

当前最稳的工程结论是:

1. 默认本地后端可用，`MacBook M4 16GB` 能完成任务 C
2. API 后端已接通，且质量高于本地基线
3. 任务 C 的产物结构、时长预算和 QA 标记已达到后续任务 D/E 可消费的程度

## 7. 当前限制

1. 本地 `M2M100` 质量仍明显受 ASR 错字影响
2. API 后端虽然更自然，但仍可能受 ASR 噪声误导
3. 时长预算目前是规则估计，不是 TTS 实测时长
4. glossary 目前是轻量实现，还没有形成大规模术语管理能力
