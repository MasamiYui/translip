# 任务 D 测试报告: Qwen3-TTS 单模型声音克隆

- 项目: `video-voice-separate`
- 对应设计: [task-d-single-speaker-voice-cloning.md](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/docs/task-d-single-speaker-voice-cloning.md)
- 测试日期: 2026-04-14
- 当前开发后端: `Qwen/Qwen3-TTS-12Hz-0.6B-Base`
- 测试机器: `MacBook M4 16GB`

## 1. 本轮范围

本轮验证覆盖 4 件事:

1. 旧 `F5-TTS / OpenVoice` 代码与依赖已从任务 D 主链路移除
2. `Qwen3-TTS` 后端与 CLI 默认值切换完成
3. 单元测试回归
4. 从 `test_video/我在迪拜等你.mp4` 全量跑到任务 D，并继续跑通到任务 E

## 2. 本轮实现结论

任务 D 现在已经完成 `F5-TTS -> Qwen3-TTS` 的单模型迁移。

当前状态:

- `synthesize-speaker` 默认后端已经改为 `qwen3tts`
- 旧的 `f5tts_backend.py`、`openvoice_backend.py` 和相关依赖代码已删除
- 首次下载不再卡在 `hf_xet`
- 端到端脚本已经改成“每个阶段一个子进程”，避免本地多模型常驻在同一 Python 进程里
- 对重复词或异常长句，任务 D 现在会按时长预算传递 `max_new_tokens`，避免 Qwen 进入 runaway generation

结论不是“已经达到成品级”，而是:

- **任务 D 主后端迁移已成立**
- **本地全量链路可重复运行**
- **质量瓶颈仍然主要在时长控制，不是声纹链路崩溃**

## 3. 关键修复

这轮真实打到并修掉了 4 个问题:

1. Hugging Face 下载会卡在 `hf_xet`
   - 处理: 在更早的配置入口设置 `HF_HUB_DISABLE_XET=1`

2. 旧 A→D / A→E 脚本把所有模型放在同一 Python 进程里
   - 结果: 前面阶段的模型状态会拖慢任务 D
   - 处理: `scripts/run_task_a_to_d.py` 和 `scripts/run_task_a_to_e.py` 改成分阶段子进程执行

3. Qwen 默认流式模拟不适合 segment 级 TTS
   - 处理: 显式传 `non_streaming_mode=True`

4. 重复词句会触发极慢或超长生成
   - 代表性 hard case: `seg-0115`
   - 处理: 根据 `duration_budget_sec / source_duration_sec` 推导 `max_new_tokens`

## 4. 自动测试

执行命令:

```bash
uv run pytest -q
```

结果:

- `35 passed`

任务 D 直接覆盖的回归包括:

- `DubbingRequest` 默认后端
- CLI `--backend` 解析
- Qwen prompt 复用
- `non_streaming_mode=True`
- `max_new_tokens` 预算传递
- report / manifest 生成

## 5. 独立冒烟验证

### 5.1 单句最小合成

执行命令:

```bash
env HF_HUB_DISABLE_XET=1 HF_HUB_ENABLE_HF_TRANSFER=0 \
uv run video-voice-separate synthesize-speaker \
  --translation ./tmp/e2e-task-a-to-e-full/task-c/voice/translation.en.json \
  --profiles ./tmp/e2e-task-a-to-e-full/task-b/voice/speaker_profiles.json \
  --speaker-id spk_0000 \
  --backend qwen3tts \
  --segment-id seg-0001 \
  --output-dir ./tmp/task-d-qwen-smoke \
  --device auto
```

结果:

- 成功生成 `speaker_demo.en.wav`
- 成功生成 `speaker_segments.en.json`
- 首次完整运行耗时约 `37.70s`

### 5.2 hard case 复测: `seg-0115`

执行命令:

```bash
env HF_HUB_DISABLE_XET=1 HF_HUB_ENABLE_HF_TRANSFER=0 \
uv run video-voice-separate synthesize-speaker \
  --translation ./tmp/e2e-task-a-to-e-qwen-full/task-c/voice/translation.en.json \
  --profiles ./tmp/e2e-task-a-to-e-qwen-full/task-b/voice/speaker_profiles.json \
  --speaker-id spk_0001 \
  --backend qwen3tts \
  --segment-id seg-0115 \
  --output-dir ./tmp/task-d-qwen-0115 \
  --device auto
```

结果:

- 之前会长时间卡住
- 加入 `max_new_tokens` 后正常完成
- 本次真实耗时约 `39.92s`

## 6. 全量验证

### 6.1 全量命令

```bash
env HF_HUB_DISABLE_XET=1 HF_HUB_ENABLE_HF_TRANSFER=0 \
uv run python scripts/run_task_a_to_e.py \
  --input ./test_video/我在迪拜等你.mp4 \
  --output-root ./tmp/e2e-task-a-to-e-qwen-full \
  --target-lang en \
  --translation-backend local-m2m100 \
  --tts-backend qwen3tts \
  --device auto \
  --speaker-limit 0 \
  --segments-per-speaker 0 \
  --fit-policy high_quality \
  --max-compress-ratio 1.7
```

### 6.2 任务 D 真实产物

目录:

- [spk_0001](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/tmp/e2e-task-a-to-e-qwen-full/task-d/voice/spk_0001)
- [spk_0004](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/tmp/e2e-task-a-to-e-qwen-full/task-d/voice/spk_0004)
- [spk_0003](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/tmp/e2e-task-a-to-e-qwen-full/task-d/voice/spk_0003)
- [spk_0000](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/tmp/e2e-task-a-to-e-qwen-full/task-d/voice/spk_0000)
- [spk_0007](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/tmp/e2e-task-a-to-e-qwen-full/task-d/voice/spk_0007)
- [spk_0002](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/tmp/e2e-task-a-to-e-qwen-full/task-d/voice/spk_0002)

全量统计:

- 总句段数: `168`
- `passed = 9`
- `review = 32`
- `failed = 127`

分 speaker 统计:

- `spk_0001`: `58` 条, `passed=8`, `review=11`, `failed=39`
- `spk_0004`: `39` 条, `review=3`, `failed=36`
- `spk_0003`: `29` 条, `passed=1`, `review=11`, `failed=17`
- `spk_0000`: `26` 条, `review=6`, `failed=20`
- `spk_0007`: `10` 条, `review=1`, `failed=9`
- `spk_0002`: `6` 条, `failed=6`

代表性结果可以直接查看:

- [spk_0001/speaker_segments.en.json](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/tmp/e2e-task-a-to-e-qwen-full/task-d/voice/spk_0001/speaker_segments.en.json)
- [spk_0003/speaker_segments.en.json](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/tmp/e2e-task-a-to-e-qwen-full/task-d/voice/spk_0003/speaker_segments.en.json)

### 6.3 结果解释

这轮结果说明两点:

1. `Qwen3-TTS` 本地链路已经比旧开发路线更稳
   - 不再出现整条流水线首条句子卡死的问题
   - 重复词 hard case 已被预算上限收住

2. 当前主要失败项仍然是 `duration_status`
   - 很多句子不是“完全听不出来”，而是目标语言在原时长窗口里仍偏长
   - 因此任务 E 最终仍会跳过大量 `overall_status=failed` 的句段

## 7. 当前限制

- 当前 `Qwen3-TTS` 本地实现会频繁把短句说得偏长
- `Task D` 的总通过率仍不高，尤其是 `1s-2s` 的短句
- 回读评测 `faster_whisper` 仍然是整条任务 D 的主要耗时来源
- 任务 D 虽然已经不再需要 `F5-TTS`，但还不能称为“成品配音质量”

## 8. 结论

截至 **2026-04-14**:

- 任务 D 的单模型 `Qwen3-TTS` 迁移已经完成
- 旧 TTS 后端代码已从主链路清理
- 全量测试视频已真实跑通到任务 E
- 当前下一步最值得优化的是:
  1. 缩短译文或在任务 C 增加更强的时长约束
  2. 降低任务 D 对极短句的失败率
  3. 视需要继续优化回读评测耗时
