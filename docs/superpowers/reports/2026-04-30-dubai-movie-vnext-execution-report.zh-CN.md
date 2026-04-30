# Dubai Movie vNext 执行报告

> 日期：2026-04-30  
> 测试视频：`test_video/我在迪拜等你.mp4`  
> 用户任务：`task-20260429-165133`  
> 当前推荐产物：`tmp/dubai-vnext-windowed`

## 1. 执行结论

当前 vNext-windowed 可作为更好的预览/对比版本，但还没达到电影级音色目标。本轮继续尝试了 Qwen3TTS 的 clone mode 与 reference tournament，确认有明确局部收益：同一组三句对白从 MOSS 的整体 failed，提升到 Qwen x-vector tournament 的整体 review，其中 speaker similarity 达到 `0.4537`，进入 passed 边界。

我不建议继续使用 `task-20260429-165133` 的导出作为效果判断基线：它使用 ASR 字幕源，并且 TTS 后端是 `moss-tts-nano-onnx`，音色相似度明显不足。当前更好的本地版本是 `tmp/dubai-vnext-windowed`，它用 Qwen3TTS 产物作为主体，并通过窗口级救援补回漏对白。

## 2. 指标对比

| 指标 | task-20260429-165133 | vNext-windowed | 结论 |
| --- | ---: | ---: | --- |
| placed | 151 | 169 | vNext 多补入救援窗口 |
| skipped | 16 | 158 | vNext 的 skipped 是候选拒绝，不是最终 overlap 丢失 |
| overall failed | 106 | 86 | vNext 更低 |
| speaker failed | 59 | 38 | vNext 更低，但仍未达电影级 |
| intelligibility failed | 15 | 43 | task 更低，但以音色/时长失败为代价 |
| avg speaker_similarity | 0.2861 | 0.3522 | vNext 更好 |
| SRT 可听覆盖 | 未按 SRT 统一评估 | 161/171 | vNext 达到 Preview-OK |

## 3. ASR 空字幕证据

`task-20260429-165133` 使用 `subtitle_source=asr`，并存在长窗口低活跃人声：

| segment | 时间 | 时长 | 活跃人声占比 | speaker | 文本 |
| --- | --- | ---: | ---: | --- | --- |
| `seg-0001` | 7.66-15.36 | 7.7s | 30% | SPEAKER_00 | 您知道哈里巴塔吗 |
| `seg-0018` | 37.22-70.74 | 33.5s | 23% | SPEAKER_00 | 是世界上最大的迪拜 |
| `seg-0021` | 72.74-76.75 | 4.0s | 44% | SPEAKER_01 | 迪拜 |
| `seg-0075` | 197.55-217.4 | 19.9s | 18% | SPEAKER_00 | 早安 |
| `seg-0080` | 225.03-238.62 | 13.6s | 12% | SPEAKER_00 | 先等一下给他这个方便花 |
| `seg-0084` | 242.75-251.69 | 8.9s | 8% | SPEAKER_00 | 一会儿带你去吃 |
| `seg-0088` | 257.69-270.38 | 12.7s | 11% | SPEAKER_00 | 我现在在迪拜天地酒店 |
| `seg-0128` | 395.92-405.5 | 9.6s | 20% | SPEAKER_00 | 若飞 |

这说明“字幕有但人没说话”不是字幕渲染层 bug，而是 ASR/VAD 时间轴直接进入预览字幕导致的链路问题。

## 4. 音色问题证据

`task-20260429-165133` 的 speaker 分布：

```json
{
  "SPEAKER_00": 10,
  "SPEAKER_01": 62,
  "SPEAKER_02": 6,
  "SPEAKER_03": 90,
  "SPEAKER_04": 1,
  "SPEAKER_05": 4,
  "SPEAKER_06": 4,
  "SPEAKER_07": 1
}
```

大部分对白集中在 `SPEAKER_03` 和 `SPEAKER_01`。这会导致多个真实角色共用少数音色。Task D 只生成了部分 speaker，且 MOSS 后端的 speaker similarity 偏低，所以“不同人同音色”符合数据证据。

## 5. 推荐查看产物

| 产物 | 路径 |
| --- | --- |
| 用户任务 preview | `/Users/masamiyui/.cache/translip/output-pipeline/task-20260429-165133/task-g/final-preview/final_preview.en.mp4` |
| vNext preview | `/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/tmp/dubai-vnext-windowed/task-g/final-preview/final_preview.en.mp4` |
| vNext final dub | `/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/tmp/dubai-vnext-windowed/task-g/final-dub/final_dub.en.mp4` |
| Qwen x-vector tournament 三句样本 | `/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/tmp/dubai-movie-vnext-qwen-xvec-tournament/task-d/voice/spk_0003/speaker_segments.en.json` |
| Qwen x-vector tournament 前 10 段样本 | `/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/tmp/dubai-movie-vnext-qwen-xvec-tournament-10/task-d/voice/spk_0003/speaker_segments.en.json` |
| 指标 JSON | `/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/tmp/dubai-movie-vnext/movie_vnext_metrics.json` |

## 6. Qwen3TTS 重试结论

本轮针对 `spk_0003` 的 `seg-0042` 到 `seg-0044` 做了四组对比：

| 方案 | reference | synthesis mode | speaker_similarity | text_similarity | overall |
| --- | --- | --- | ---: | ---: | --- |
| MOSS 原任务 `seg-0043` | clip_0002 | segment | 0.2302 | 1.0000 | failed |
| Qwen ICL 默认 | clip_0005 | dubbing_unit | -0.1210 | 0.1277 | failed |
| Qwen ICL 手动 ref3 | clip_0003 | dubbing_unit | 0.6705 | 0.1892 | failed |
| Qwen x-vector 单句 | clip_0003 | segment | 0.2910 | 1.0000 | review |
| Qwen x-vector tournament | 自动试 clip_0005/0004/0003，选 clip_0003 | dubbing_unit | 0.4537 | 0.8046 | review |

解释：

- Qwen ICL 能拉高音色，但容易说错内容，不适合直接进最终片。
- Qwen x-vector-only 内容稳定得多，音色不如 ICL，但配合 reference tournament 可以把主样本 speaker similarity 拉到 passed 边界。
- `TRANSLIP_REFERENCE_TOURNAMENT=1` 是有效收益点：它自动试了 3 条参考音频，最终没有沿用默认排序的 `clip_0005`，而是选择了综合更好的 `clip_0003`。
- `Qwen/Qwen3-TTS-12Hz-1.7B-Base` 已下载到本地，但 CPU 单句超过 5 分钟仍未完成，本机不适合作为默认方案；它应放到 GPU/离线高质量队列再验证。

扩大到 `spk_0003` 前 10 段后，收益仍成立：

| 指标 | MOSS 原任务前 10 段 | Qwen x-vector tournament 前 10 段 |
| --- | ---: | ---: |
| overall passed/review/failed | 0 / 1 / 9 | 1 / 6 / 3 |
| speaker passed/review/failed | 0 / 5 / 5 | 1 / 7 / 2 |
| avg speaker_similarity | 0.2361 | 0.3215 |
| avg text_similarity | 0.8820 | 0.9283 |

小批量结论：Qwen x-vector tournament 有稳定收益，但仍没有达到 Movie-OK。剩余失败主要集中在极短句和 translation/DialogueUnit 质量，例如 `Old Jia`、`What`、`What is` 这类短片段必须由 DialogueUnit Builder 合并或重写，而不是单独克隆。

## 7. 已落地改造

| 改造 | 文件 | 作用 |
| --- | --- | --- |
| Qwen clone mode | `src/translip/dubbing/qwen_tts_backend.py` | 支持 `QWEN_TTS_CLONE_MODE=icl/xvec`；x-vector 模式在 MPS 上自动落 CPU，规避 NaN |
| reference tournament | `src/translip/dubbing/runner.py` | 支持 `TRANSLIP_REFERENCE_TOURNAMENT=1`，强制试多条 reference 后择优 |
| 单测 | `tests/test_dubbing.py` | 覆盖 Qwen x-vector prompt 行为 |
| 实验探针 | `.tmp/qwen_xvec_probe.py` | 复现实验用，不进入主路径 |

验证命令：

```bash
uv run pytest tests/test_dubbing.py::test_qwen_backend_uses_reusable_voice_clone_prompt tests/test_dubbing.py::test_qwen_backend_supports_xvec_clone_mode tests/test_dubbing.py::test_qwen_max_new_tokens_is_calibrated_to_12hz_audio_budget
uv run pytest tests/test_dubbing.py::test_synthesize_speaker_writes_report_and_manifest tests/test_dubbing.py::test_synthesize_speaker_prefers_voice_bank_references tests/test_dubbing.py::test_qwen_backend_supports_xvec_clone_mode
QWEN_TTS_CLONE_MODE=xvec TRANSLIP_REFERENCE_TOURNAMENT=1 uv run translip synthesize-speaker --translation /Users/masamiyui/.cache/translip/output-pipeline/task-20260429-165133/task-c/voice/translation.en.json --profiles /Users/masamiyui/.cache/translip/output-pipeline/task-20260429-165133/task-b/voice/speaker_profiles.json --speaker-id spk_0003 --output-dir tmp/dubai-movie-vnext-qwen-xvec-tournament/task-d --backend qwen3tts --device cpu --max-segments 3 --backread-model tiny
```

## 8. 下一轮必须继续改造的点

1. 把 ASR 字幕源从默认导出中移除，改成 SRT/OCR/DialogueUnit 字幕。
2. 实现 DialogueUnit Builder，解决短句误翻和长 ASR 空窗。
3. Task D 继续扩大 tournament：`backend x reference_clip x rewrite_variant`，MOSS 只做快速 fallback。
4. 加 Character Registry 和 active speaker，把 `speaker_id` 升级为 `character_id`。

## 9. 当前状态

- Preview-OK：`True`
- Movie-OK：`False`
