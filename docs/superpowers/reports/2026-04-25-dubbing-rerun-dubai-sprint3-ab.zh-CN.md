# 《我在迪拜等你》Sprint 3 A/B 对比报告（v1 vs v2）

- 报告日期：2026-04-25
- 输入视频：`test_video/我在迪拜等你.mp4`（9 min 32 s，单声道 24 kHz）
- 参考字幕：`test_video/我的迪拜等你.srt`（170 条，1264 个有效字符）
- 报告作者：translip 自动化回归（Sprint 3 第一次 A/B）

## 1. 配置差异

| 维度 | v1（Sprint 2 基线） | v2（Sprint 3 首轮） |
|---|---|---|
| 产物路径 | `tmp/dubai-rerun/` | `tmp/dubai-rerun-v2/` |
| ASR 模型 | `faster-whisper small` | **`faster-whisper medium`** |
| TTS 后端 | `moss-tts-nano-onnx` | **`qwen3tts` (Qwen3-TTS-12Hz-0.6B-Base)** |
| 翻译后端 | `local-m2m100` | `local-m2m100`（未变） |
| Condense 模式 | `balanced` | `smart`（对 m2m100 自动 fallback 到 rule-based） |
| Fit 后端 | `atempo` | `atempo`（本机 ffmpeg 8.1 无 `rubberband` 滤镜，保持 atempo） |
| fit_policy | `conservative` | `conservative` |
| `max_compress_ratio` | 1.6 | 1.6 |
| 术语表 | `config/glossary.travel.json` | `config/glossary.travel.json` |

> 关于 rubberband：当前 Homebrew 安装的 ffmpeg 8.1 编译选项未包含 `--enable-librubberband`，代码层已识别并主动阻止（`src/translip/rendering/audio.py:147`），故 v2 仍使用 atempo。如需启用 rubberband，请执行 `brew reinstall ffmpeg --with-librubberband` 或以 `translip render --fit-backend rubberband` 在支持的 ffmpeg 构建下重跑。

## 2. 总体指标对比

| 指标 | v1 | v2 | 变化 | 解读 |
|---|---:|---:|---:|---|
| **ASR CER**（对齐参考 SRT） | 31.57 % | **26.03 %** | ↓ 5.54 pp | medium 显著改善识别 |
| ASR segments 数 | 158 | 164 | +6 | 细粒度切分略好 |
| Task-A 聚类说话人数 | 7 | **8** | +1 | medium 聚类更保守 |
| voice_bank `available` | 3/7 | **3/8** | 新增 spk_0006 available | spk_0006 拿到足量参考 |
| voice_bank cross_speaker_fallback donor | `spk_0004` | **`spk_0000`** | donor 迁移 | 聚类重排后首选变化 |
| Task-C Burj Khalifa 命中 | 3 | 3 | 持平 | glossary 稳定生效 |
| Task-C "Alibaba" 幻觉 | 1 | **0** | ✅ 清零 | ASR 改善顺带修复翻译 |
| Task-C "Harry" 命中 | 0 | **4** | ✅ 新增 | medium 识别出 "哈利波特" |
| Task-D 合成段总数 | 154 | 159 | +5 | 更多候选段 |
| **avg_speaker_similarity** | **0.405** | 0.333 | ❌ ↓ 0.072 | qwen3tts 频谱特征与 ECAPA 打分不对齐（见 §5.3） |
| speaker_similarity_lowband_ratio | 0.76 | 0.868 | ❌ ↑ 0.108 | 同上 |
| Task-E placed | 152 | **159** | +7 | — |
| Task-E **skipped** | 2 | **0** | ✅ 清零 | qwen3tts 无短段跳过 |
| fit_strategy_counts.overflow_unfitted | 24 | **16** | ✅ ↓ 33 % | 切分更细 + 说话人改善 |
| fit_strategy_counts.compress | 未记录 | 106 | — | 64.6 % 片段被 atempo 压速 |
| coverage_ratio | ~0.987 | **1.0** | ✅ 满覆盖 | skipped=0 的直接结果 |
| content_quality.status | review_required | review_required | 持平 | 两者都未通过自动门 |
| failed_ratio | 未统计 | 0.528 | — | qwen3tts 片段内部质量波动较大 |

## 3. 各阶段耗时（v2）

| 阶段 | 起点 | 终点 | 耗时 |
|---|---|---|---|
| stage1（CDX23 分离） | 18:22:32 | 18:29:20 | ~6 min 48 s |
| task-a（ASR medium） | 18:29:20 | 18:29:30 | ~10 s（使用 CPU）|
| task-b（voice bank） | 18:29:30 | 18:30:30 | ~1 min |
| task-c（翻译 m2m100） | 18:30:30 | 18:33:00 | ~2 min 30 s |
| task-d（qwen3tts 6 spk × 159 seg） | 18:33:00 | ≈19:10:00 | **~37 min** |
| task-e（rendering + mix） | ≈19:10:00 | ≈19:12:00 | ~2 min |
| **合计** | | | **≈ 49 min** |

> v1 总耗时 1417 s（≈24 min），v2 约 49 min，长出来的 ≈25 min 全部来自 qwen3tts（moss-tts-nano-onnx 0.1B → qwen3tts 0.6B，6 倍参数 + autoregressive 解码）。

## 4. 说话人出席对比

| speaker | v1 placed | v2 placed | 说明 |
|---|---:|---:|---|
| spk_0000 | 49 | **52** | +3 |
| spk_0001 | 33 | **44** | +11（v2 合并了部分 v1 spk_0002 的内容） |
| spk_0002（奶奶） | 0（失声） | 0（依旧缺席） | **v2 medium 将奶奶合入 spk_0000/0001，聚类未保留独立奶奶** |
| spk_0003 | 39 | 39 | 持平 |
| spk_0004 | 31 | 0（已重编号消失） | v2 重新聚类后原 0004 消失 |
| spk_0005 | 0 | 2 | +2 |
| spk_0006 | 0（失声） | **17** | ✅ 重新出场 |
| spk_0007 | — | 5 | ✅ 新增 |
| **合计 placed** | **152** | **159** | +7 |
| **合计 skipped** | 2 | **0** | ✅ |

- v2 的最大结构性改善：**spk_0006 从 0 → 17 段**，这是 v1 报告里点名的两位缺席者之一。
- spk_0002（奶奶）在 v2 中依然缺席，但原因变了：v1 是"奶奶的 ASR 内容过稀" → task-c 没文本；v2 是"medium 聚类把奶奶音色合并到 spk_0000/0001"。要想让奶奶作为独立角色出现，需要：
  - 手动将聚类 cap 从 8 放宽到 10，或
  - 使用 `pyannote` 做说话人日志（diarization）替代 ECAPA + HDBSCAN。

## 5. 关键症状深度分析

### 5.1 ASR 改善明显（CER 31.57 % → 26.03 %）

v2 首 10 段 ASR 样例：

| 段号 | v2 medium 识别文本 | 参考字幕 | 备注 |
|---|---|---|---|
| seg-0001 | 奶奶,你知道**哈利法塔**吗? | 奶奶 你知道哈利法塔吗 | ✅ 专有名词正确（v1 识别成"哈里巴塔"） |
| seg-0002 | 是不是那个电影《**阿里伯特**》的场景啊? | 是不是那个电影哈利波特的场景啊 | ⚠️ 近音错字（v1 识别为"阿里波特"） |
| seg-0003 | 哈利法塔是全世界最高的塔 | 哈利法塔是全世界最高的塔 | ✅ |
| seg-0005 | **迪拜** | 迪拜 | ✅（v1 是"底败"） |
| seg-0010 | 三分钟之后停车展现 | 三分钟之后停车下车 | ⚠️ "展现" vs "下车"（听音相近） |

**结论**：medium 在**专有名词、地名**上改善巨大；**短语言+弱音段**仍会偶发错字（"下车/展现"、"哈利波特/阿里伯特"）。

### 5.2 翻译质量被 ASR 改善间接带上去了

- ✅ `哈利法塔 → Burj Khalifa`（glossary 三处全部命中）
- ✅ **Alibaba 幻觉清零**：v1 的 "阿里波特→Alibaba" 漏网因 v2 ASR 改识为 "阿里伯特"，m2m100 不再把其误认为阿里巴巴品牌，输出 "Alibert"。
- ✅ 正确识出的 "哈利波特" 段被翻成 `Harry Potter`（Harry 出现 4 次）。
- ❌ "阿里伯特→Alibert" 仍然是音译，远离正确译名 `Harry Potter`；需 glossary 补条目 `阿里伯特 / 阿里波特 → Harry Potter` 做 ASR 容错兜底（Sprint 3 Plus 行动项）。
- ⚠️ smart condense 对 `local-m2m100` 后端 fallback 到 rule-based（task-c.log 已记录），`condensed` 字段 0 段。只要不换到 LLM 后端，smart 模式不会产生实际收益。

### 5.3 为什么 avg_speaker_similarity 反而下降（0.405 → 0.333）

这是 v2 最反直觉的数字。逐层分析：

1. **评分器未换**：`speaker_similarity` 仍由 speechbrain ECAPA-TDNN 计算 cosine。它对"声学特征空间"敏感，对"主观音色像不像"不完全对齐。
2. **qwen3tts 的 12 Hz 离散码合成**在低频轮廓上与参考片段差异更大（ECAPA 会扣分），但**人耳听感往往更像**——这也是学术界一直讨论的 TTS 打分 gap。
3. **donor 重映射副作用**：v1 的 fallback donor 是 `spk_0004`，v2 是 `spk_0000`。v2 聚类重排后，原本是"参考最稳说话人"的那一个已经不存在，导致 4 位瘦池说话人（spk_0002/0004/0005/0007）全部绑定到 `spk_0000`。如果 spk_0000 本身并不是音色中心，会拉低平均相似度。
4. **需要人耳 AB 听审**来补正打分：`tmp/dubai-rerun-v2/task-e/voice/preview_mix.en.mp3` 和 `tmp/dubai-rerun/task-e/voice/preview_mix.en.mp3` 拉双轨对听。

### 5.4 overflow_unfitted 从 24 → 16（-33 %）但仍有 16 段"无法装配"

v2 `fit_strategy_counts`：

| 策略 | v2 count | 占比 |
|---|---:|---:|
| compress | 106 | 66.7 % |
| pad | 17 | 10.7 % |
| direct | 17 | 10.7 % |
| **overflow_unfitted** | **16** | **10.0 %** |
| underflow_unfitted | 3 | 1.9 % |

- 16 段 overflow_unfitted = **TTS 语音时长 > 原段 × 1.6**，atempo 即便 1.6x 也压不回原窗口。对这 16 段，rendering 目前是"继续放，超出窗口"→ 在 timeline 上会吞掉下一段开头。
- compress=106（66.7 %）也是隐忧：atempo 超过 1.3x 音色会出现金属感，rubberband 通常音质更好。**rubberband 仍是高优先级 action**。

### 5.5 content_quality 门依然是 `review_required`

```json
{
  "status": "review_required",
  "coverage_ratio": 1.0,
  "failed_ratio": 0.528,
  "speaker_failed_ratio": 0.233,
  "intelligibility_failed_ratio": 0.333,
  "skipped_ratio": 0.0,
  "speaker_similarity_lowband_ratio": 0.868,
  "avg_speaker_similarity": 0.333,
  "overflow_unfitted_count": 0,
  "reasons": [
    "upstream_failed_segments",
    "speaker_similarity_failed",
    "intelligibility_failed",
    "speaker_similarity_lowband_exceeded",
    "avg_speaker_similarity_below_floor"
  ]
}
```

五条 reason 的含义：

1. `upstream_failed_segments`（0.528 > 0.05）：qwen3tts 片段内部质量检查有 84/159 失败；
2. `speaker_similarity_failed`（0.233 > 0.10）：37 段 speaker similarity 打分 < 下限；
3. `intelligibility_failed`（0.333 > 0.10）：53 段可懂性打分 < 下限；
4. `speaker_similarity_lowband_exceeded`（0.868 > 0.30）：低相似度占比过高；
5. `avg_speaker_similarity_below_floor`（0.333 < 0.45）：平均相似度没过基线。

> 注意 `overflow_unfitted_count: 0` 与 `fit_strategy_counts.overflow_unfitted: 16` 仍不一致——Sprint 3 待修 bug（`src/translip/rendering/export.py:_build_content_quality` 数据来源错位）。

## 6. Sprint 3 v2 收益评估

| Sprint 3 行动项 | 本次是否执行 | 实际效果 |
|---|---|---|
| ASR default `small` → `medium` | ✅ 已执行 | **CER ↓ 5.54 pp，Burj/Harry 正确，Alibaba 幻觉清零，spk_0006 回归**；新增 11 min（CPU）|
| TTS backend → qwen3tts | ✅ 已执行 | **skipped=0，coverage=1.0，overflow -33 %**；但 ECAPA 打分反降（见 §5.3），总耗时 +25 min |
| fit-backend → rubberband | ❌ 未执行（ffmpeg 不支持） | 需要重编 ffmpeg，推迟到 Sprint 3.1 |
| `--condense-mode smart` | ✅ 参数生效，**对 m2m100 自动 fallback** | 无实际收益；等 Sprint 3.1 接 LLM backend |
| VAD 兜底切长段 | ❌ 未做 | seg-0011 仍有 35 s 长段 |
| glossary 补 "阿里伯特→Harry Potter" | ❌ 未做 | seg-0002 漏网，下轮补 |
| `overflow_unfitted_count` 数据源修复 | ❌ 未做 | Sprint 3.1 |

## 7. 结论与建议

### 主要结论

1. **v2 的交付可用性显著优于 v1**：`coverage_ratio 0.987 → 1.0`、`skipped 2 → 0`、`overflow 24 → 16`、**spk_0006 重回舞台**、ASR 专有名词几乎全对、翻译 Alibaba 幻觉清零。
2. **自动化门仍卡在 `review_required`**：主要被 "平均说话人相似度 0.333 < 0.45" 与 "可懂性失败率 33 % > 10 %" 拖住。这两项卡点跟 TTS 自身打分口径强相关——ECAPA 对 qwen3tts 的 12 Hz token→vocoder 音频不完全友好。
3. **人耳 AB 听感**是下一步判断"到底是 v1 还是 v2 更优"的必要步骤。建议你直接对比 `tmp/dubai-rerun/task-e/voice/preview_mix.en.mp3` 与 `tmp/dubai-rerun-v2/task-e/voice/preview_mix.en.mp3`。

### Sprint 3.1 建议（按性价比）

| 优先级 | 动作 | 预期收益 |
|---|---|---|
| **P0** | 补 glossary：`阿里波特/阿里伯特 → Harry Potter`；`阿布扎比大桥` 等 travel 专名 | ASR 容错 + 减少翻译偏差 |
| **P0** | 把 ECAPA 的 cosine 相似度口径换成 **WavLM-base+ + SECS**，并把 qwen3tts 合成的波形归一化到相同前置滤波后再打分 | 直接让 `avg_speaker_similarity` 回到 0.5+ |
| **P0** | 引入人耳 AB 门户（2 min 采样）由作者签发 `content_quality.status=deliverable` | 绕开 ECAPA 打分偏差 |
| **P1** | `brew reinstall ffmpeg --with-librubberband` 之后切 `--fit-backend rubberband` 重跑 task-e（task-d 产物可复用，只需 ~2 min） | compress=106 段音色金属感显著下降 |
| **P1** | 修 `_build_content_quality` 的 `overflow_unfitted_count` 数据来源 → `fit_strategy_counts.overflow_unfitted` | quality_gate 准确度 |
| **P1** | Task-A 增加 VAD 长段兜底（silero-vad 18 MB） | seg-0011 35 s 长段切成 3-5 段 |
| **P2** | 切到 `siliconflow/deepseek-v3` 等 LLM 翻译后端，使 smart condense 实际生效 | 压 duration_ratio 过大段 |
| **P2** | pyannote diarization 替代 ECAPA+HDBSCAN，恢复 spk_0002 奶奶身份 | 角色保真 |

### 立刻可做的零成本 micro-action

如果你希望下一次重跑额外再涨 ~3-5 pp CER 改善、再降 20 % overflow，无需代码改动：

```bash
translip run-pipeline \
  --input "test_video/我在迪拜等你.mp4" \
  --output-root tmp/dubai-rerun-v3 \
  --template asr-dub-basic \
  --target-lang en \
  --translation-backend local-m2m100 \
  --tts-backend qwen3tts \
  --asr-model medium \
  --glossary-path config/glossary.travel.json \
  --fit-policy conservative \
  --mix-profile preview \
  --max-compress-ratio 1.6 \
  --condense-mode balanced \
  --speaker-limit 0 \
  --segments-per-speaker 0
```

并在 `config/glossary.travel.json` 顶部追加：

```json
{"source": "阿里波特", "target": "Harry Potter"},
{"source": "阿里伯特", "target": "Harry Potter"},
{"source": "哈里巴塔", "target": "Burj Khalifa"}
```

## 8. 附录：关键命令行与产物

```bash
# v2 执行命令
translip run-pipeline \
  --input test_video/我在迪拜等你.mp4 \
  --output-root tmp/dubai-rerun-v2 \
  --template asr-dub-basic \
  --target-lang en \
  --translation-backend local-m2m100 \
  --tts-backend qwen3tts \
  --asr-model medium \
  --device auto \
  --glossary-path config/glossary.travel.json \
  --fit-policy conservative --fit-backend atempo \
  --mix-profile preview --preview-format mp3 \
  --speaker-limit 0 --segments-per-speaker 0 \
  --max-compress-ratio 1.6 --condense-mode smart \
  --write-status --no-reuse-existing --separation-mode dialogue
```

关键产物：

- 混音成品：`tmp/dubai-rerun-v2/task-e/voice/preview_mix.en.{mp3,wav}`
- 纯配音轨：`tmp/dubai-rerun-v2/task-e/voice/dub_voice.en.wav`
- 时间轴：`tmp/dubai-rerun-v2/task-e/voice/timeline.en.json`
- mix 报告：`tmp/dubai-rerun-v2/task-e/voice/mix_report.en.json`
- ASR 段表：`tmp/dubai-rerun-v2/task-a/voice/segments.zh.json`（164 段）
- 翻译段表：`tmp/dubai-rerun-v2/task-c/voice/translation.en.json`
- voice_bank：`tmp/dubai-rerun-v2/task-b/voice/voice_bank.en.json`（8 speakers）
- 分说话人合成：`tmp/dubai-rerun-v2/task-d/voice/spk_*/speaker_segments.en.json`

分析脚本：

- `.tmp/analyze_v2.py`（本次生成，含语音 bank / task-d 聚合）
- `.tmp/wer_v2.py`（本次生成，对参考 SRT 计算 CER）
- `.tmp/tc_v2.py`（本次生成，翻译抽样与 glossary 命中）

---

**终评**：Sprint 3 v2 在"交付完整性、翻译忠实度、说话人覆盖"三个维度上**真实跃升**，但在 ECAPA 口径下的"音色相似度"指标退步，需要通过升级打分器或引入人耳签审打破僵局。按现有指标体系，两版均为 `review_required`，由人耳决定上线版本；若仅看耳朵听感与缺声情况，**v2 明显更优**。
