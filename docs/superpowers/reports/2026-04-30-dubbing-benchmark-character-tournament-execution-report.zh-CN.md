# 配音 Benchmark / Character Ledger / Tournament 执行报告

> 日期：2026-04-30
> Playwright 任务：`task-20260430-083427`
> 测试视频：`/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/test_video/我在迪拜等你.mp4`
> 输出目录：`/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/.tmp/playwright-dub-benchmark/20260430-163427`

## 1. 本次完成内容

- 新增 `Character Ledger v1`：生成角色级音色台账，记录 pitch class、声纹失败率、音色漂移和 review 状态。
- 新增 `TTS/VC Tournament v1` 质量门：返修候选会计算角色音色一致性，明显 pitch-class 漂移的候选不会自动入选。
- 新增 `Dub Benchmark v0`：汇总时间线覆盖、Task D 质量、角色台账、返修候选，输出可比较的质量分和状态。
- 新增配音返修审查「质量总览」页签：前端可直接查看 Benchmark、角色风险、覆盖失败数和人工返修数。
- Task E 已自动接入：先生成角色台账，再跑返修，再渲染时间线，最后生成 Benchmark。

## 2. 验证结果

### 2.1 自动化测试

- `uv run pytest tests/test_character_ledger.py tests/test_repair.py tests/test_dub_benchmark.py tests/test_orchestration.py tests/test_dubbing_review_routes.py tests/test_cli.py -q`
- 结果：`54 passed`
- `npm --prefix frontend run build`
- 结果：通过

### 2.2 Playwright 全流程

使用 Playwright 创建并跑完整流水线：

- `stage1`: succeeded
- `task-a`: succeeded
- `task-b`: succeeded
- `task-c`: succeeded
- `task-d`: succeeded
- `task-e`: succeeded
- `task-g`: succeeded

前端任务详情与「配音返修审查 / 质量总览」均已打开验证。截图：

- `.playwright-cli/page-2026-04-30T13-30-29-228Z.png`

## 3. 核心产物

- 角色台账：`.tmp/playwright-dub-benchmark/20260430-163427/task-d/voice/character-ledger/character_ledger.en.json`
- 返修尝试：`.tmp/playwright-dub-benchmark/20260430-163427/task-d/voice/repair-run/repair_attempts.en.json`
- 时间线报告：`.tmp/playwright-dub-benchmark/20260430-163427/task-e/voice/mix_report.en.json`
- Benchmark：`.tmp/playwright-dub-benchmark/20260430-163427/benchmark/voice/dub_benchmark.en.json`
- 预览成片：`.tmp/playwright-dub-benchmark/20260430-163427/task-g/final-preview/final_preview.en.mp4`
- 纯配音质检版：`.tmp/playwright-dub-benchmark/20260430-163427/task-g/final-dub/final_dub.en.mp4`

## 4. 指标结论

### 4.1 时间线与无声问题

- `placed_count`: `185`
- `skipped_count`: `0`
- `coverage_ratio`: `1.0`
- `audible_failed_count`: `0`

结论：本轮没有出现“字幕/片段存在但最终无配音音频”的阻断问题。覆盖类问题通过。

### 4.2 Benchmark

- `status`: `review_required`
- `score`: `54.84`
- `reasons`:
  - `upstream_failed_segments`
  - `speaker_similarity_failed`
  - `character_voice_review_required`
  - `repair_manual_required`

结论：可以完整生成成品，但还不能判断为自动可交付，需要人工审听与角色级修正。

### 4.3 角色台账

- `character_count`: `8`
- `review_count`: `3`
- `blocked_count`: `0`
- `voice_mismatch_count`: `0`

需要复核的角色：

| speaker | pitch | risk | speaker_failed_ratio |
| --- | --- | --- | --- |
| `spk_0001` | `mid` | `speaker_similarity_failed` | `0.2745` |
| `spk_0002` | `mid` | `speaker_similarity_failed` | `0.3333` |
| `spk_0004` | `mid` | `speaker_similarity_failed` | `0.3108` |

结论：本轮没有检测到明显 low/mid/high pitch-class 漂移，所以“男声变女声”的粗粒度漂移没有在该轮产物中出现；但 3 个角色的 speaker consistency 仍然不稳定。

### 4.4 返修 Tournament

- `input_count`: `12`
- `attempt_count`: `32`
- `selected_count`: `0`
- `manual_required_count`: `12`
- `voice_consistency_status`: `passed=19`, `review=13`, `failed=0`

结论：新质量门没有误选音色不稳的候选，但当前 MOSS-TTS-Nano 返修候选在综合文本、时长、声纹指标上仍未达到自动替换标准，因此本轮没有自动替换收益。

## 5. 效果判断

本次有明确工程收益：

- 无声覆盖问题维持住了：`placed_count=185`、`skipped_count=0`、`audible_failed_count=0`。
- 已经能系统性拦截明显音色类别漂移候选，不再只依赖 speaker similarity。
- 每次完整流水线都会产出可比较 Benchmark，不再只能靠主观试听。
- 前端已能直接看到质量分、角色风险、人工返修数和台账详情。

但从真实样片最终质量看，还没有达到“自动完美配音”：

- Benchmark 仍是 `review_required`。
- Task D 的 `overall_failed_ratio=0.5297` 偏高。
- `speaker_failed_ratio=0.2162` 超过 0.15 的 review 阈值。
- 返修候选全部转人工，说明当前 MOSS-TTS-Nano 的自动返修能力有限。

## 6. 下一步建议

短期最有收益的是两条线并行：

1. 接入更强的 TTS/VC 候选进入 Tournament，例如 Qwen3TTS、IndexTTS2、CosyVoice2 或 TTS+Seed-VC 两阶段方案。
2. 做专业配音编辑能力：让审听人员在质量总览中直接处理 3 个风险角色和 12 个人工返修片段。

当前这版适合作为后续迭代基线：它已经能稳定跑完整流水线、定位风险、避免坏候选自动入选，但模型级音色自然度和 speaker consistency 仍需下一轮模型策略升级。
