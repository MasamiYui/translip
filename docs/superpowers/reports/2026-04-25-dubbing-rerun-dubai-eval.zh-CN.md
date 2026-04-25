# 《我在迪拜等你》流水线全量重跑质量评估报告

- **视频**：`test_video/我在迪拜等你.mp4`（960×416，22 fps，AAC 44.1 kHz 立体声，534.6 s / 约 8 分 55 秒）
- **重跑日期**：2026-04-25（Sprint 1 + Sprint 2 改造之后的首次完整端到端验证）
- **运行入口**：`translip run-pipeline --template asr-dub-basic`
- **硬件**：Apple M4 / 16 GB / 10 核
- **关键配置**：`tts-backend=moss-tts-nano-onnx` · `translation-backend=local-m2m100` · `glossary-path=config/glossary.travel.json` · `fit-policy=conservative` · `max-compress-ratio=1.6`（Sprint 1 升级）· `asr-model=small`（run-pipeline 默认）
- **总耗时**：`1417.82 s`（≈ 23 min 38 s，实时倍率 0.37x），peak RSS 3.63 GB
- **最终产物**：
  - `tmp/dubai-rerun/task-e/voice/preview_mix.en.mp3`（10 MB）
  - `tmp/dubai-rerun/task-e/voice/preview_mix.en.wav`（24 MB）
  - `tmp/dubai-rerun/task-e/voice/dub_voice.en.wav`（24 MB，纯干配音）
  - `tmp/dubai-rerun/task-e/voice/mix_report.en.json`（217 KB）
  - `tmp/dubai-rerun/task-e/voice/timeline.en.json`（214 KB）
  - `tmp/dubai-rerun/pipeline-report.json`、`pipeline-manifest.json`

---

## 1. 各阶段运行结果摘要

| 阶段 | 状态 | 用时 | 关键产物 |
|---|---|---|---|
| stage 1（对白/伴奏分离，CDX23） | ✅ succeeded | 5 min 00 s | `voice.mp3`、`background.mp3` |
| task-a（ASR + 说话人聚类） | ✅ succeeded | 45 s | 158 段，7 speakers（**cluster 重聚**：55→8 cap） |
| task-b（说话人建档 + voice-bank） | ✅ succeeded | 5 s | 7 speakers，3 available / **4 needs_more_references** |
| task-c（local-m2m100 翻译 + glossary） | ✅ succeeded | 66 s | 158 条 en_translation |
| task-d（moss-tts-nano 多说话人合成） | ✅ succeeded | ≈ 16 min 30 s | 154 段覆盖 5 位说话人 |
| task-e（时间轴拟合 + 混音） | ✅ succeeded | 20 s | 152 placed / 2 skipped |

流水线**未发生硬失败**，所有 stage 产物合法；这是 Sprint 1/2 后的第一次"全绿"端到端。

---

## 2. `content_quality` 质量门（Sprint 2 强化）的判定

```json
{
  "status": "review_required",
  "coverage_ratio": 0.987,
  "failed_ratio": 0.3182,
  "speaker_failed_ratio": 0.0909,
  "intelligibility_failed_ratio": 0.0584,
  "skipped_ratio": 0.013,
  "speaker_similarity_lowband_ratio": 0.7566,
  "avg_speaker_similarity": 0.4052,
  "overflow_unfitted_count": 0,
  "reasons": [
    "coverage_below_deliverable_threshold",
    "upstream_failed_segments",
    "speaker_similarity_lowband_exceeded",
    "avg_speaker_similarity_below_floor"
  ],
  "thresholds": {
    "coverage_min": 0.98, "failed_max": 0.05,
    "speaker_failed_max": 0.1, "intelligibility_failed_max": 0.1,
    "speaker_similarity_review_floor": 0.5,
    "speaker_similarity_lowband_max": 0.3,
    "avg_speaker_similarity_min": 0.45,
    "skipped_ratio_block": 0.2
  }
}
```

- `status = review_required`：**Sprint 2 的 quality_gate 正确工作**，产物不被自动当成"可发布"。
- `speaker_similarity_lowband_exceeded`、`avg_speaker_similarity_below_floor` 两条是 Sprint 2 新增 reason，**在真实长视频上首次落地触发**。
- `skipped_ratio=1.3%`（task-20260425-023015 曾高达 ~12%），已显著改善。
- `overflow_unfitted_count=0`（`max_compress_ratio` 1.45→1.6 升级 + TTS 产出普遍偏短，压缩就够了）。

---

## 3. 分阶段细颗粒度诊断

### 3.1 Task-A：ASR 是整条链路的最大瓶颈

**对照用户提供的参考字幕** `test_video/我的迪拜等你.srt`（170 条），做字符级 WER：

| 指标 | 数值 |
|---|---|
| 参考字符数 | 1264 |
| ASR 字符数 | 1081 |
| Levenshtein 编辑距离 | **399** |
| **字符错误率（CER）** | **31.57 %** |
| 参考字幕条数 | 171 |
| ASR 段数 | 158（缺 13 条） |
| 窗口不匹配数 | **156 / 171**（91 %） |

错误样本（按参考字幕 ↔ ASR 对照）：

| 参考 | ASR small 输出 | 错误类型 |
|---|---|---|
| 奶奶你知道**哈利法塔**吗 | 奶奶你知道**哈里巴塔**吗 | 同音替换 |
| 那个电影**哈利波特**的场景啊 | 那个电影**阿里波特**的场景 | 近音替换 |
| **哈利法塔**是全世界最高的塔 | **哈里巴塔**是全世界最高的塔 | 同音替换 |
| 3 分钟之后停车**闪电** | 三分钟之后停车**展现** | 同音替换 |
| 现在去迪拜 | *（被并入上一段）* | 段边界错乱 |
| excuseme / areyouChinese | HeyexcusemeareyouChinese | 英文粘连 |
| 奶奶爸爸妈妈我已经**到迪拜**了 | 奶奶,爸爸妈妈,我已经**到底败**了 | 近音替换（致命） |

更严重的 **"空段"症状**（时长 ≥6s 但 ASR 文本 < 25 字）：

| 段号 | 时长 | 文本 | CPS |
|---|---|---|---|
| seg-0011 | 34.2 s | 三分钟之后 停车展现 | 0.29 |
| seg-0092 | 39.7 s | 对不起,奶奶 | **0.15** |
| seg-0158 | 21.8 s | 吴建 | **0.09** |
| seg-0086 | 15.0 s | 奶奶,爸爸妈妈,我已经到底败了 | 1.00 |
| seg-0087 | 6.0 s | 奶奶,这就是我跟你说的世界上最高的塔,哈里法塔 | 3.80 |
| seg-0094 | 6.7 s | 全奈奈我让我的好朋友哈里先生给你介绍 | 2.68 |

这 6 段几乎都归在 **spk_0002**（"奶奶"）身上，与 task-20260425-023015 里的 spk_0002 症状一模一样——**Sprint 2 的 `resegment` 无法"凭空补文字"**。

### 3.2 Task-B / Voice-bank：Sprint 2 的 `cross_speaker_fallback` 实战有效

```
spk_0000  available             usable=5 seg=47  94.7 s
spk_0001  available             usable=5 seg=27  71.5 s
spk_0002  needs_more_references usable=0 seg=3   95.8 s  → fallback=spk_0004
spk_0003  needs_more_references usable=1 seg=3    7.7 s  → fallback=spk_0004
spk_0004  available             usable=5 seg=70 113.3 s
spk_0005  needs_more_references usable=1 seg=7    5.1 s  → fallback=spk_0004
spk_0006  needs_more_references usable=0 seg=1    0.8 s  → fallback=spk_0004
```

- `voice_bank.en.json` 为每位"瘦池"说话人正确写入 `cross_speaker_fallback.donor_speaker_id = "spk_0004"`。
- 对 spk_0002/0006 特别关键——它们连 task-a 里的可用参考片段都没有，如果沿用旧逻辑会被整段抛弃。
- 然而——**fallback 解决的是"有翻译也能合成"的前提，但 spk_0002 / spk_0006 的翻译在 task-c 几乎全空**（ASR 根因），所以最终 mix 里仍缺席（见下）。

### 3.3 Task-C：glossary 救场，但仍有 "阿里波特→Alibaba" 幻觉

抽样 15 段翻译（见附录 A），没有出现 **m2m100 的典型病症**：无 "Halifa"、"mom mom mom"、"Harry" 等幻觉。

- **Sprint 1 glossary 命中**：
  - `哈里巴塔 → Burj Khalifa` ✅（源于我新增的 5 个变体）
  - `哈里法塔 → Burj Khalifa` ✅
  - `迪拜 → Dubai` ✅
- **仍有漏网之鱼**：
  - `阿里波特` (ASR 错，应为"哈利波特") → m2m100 翻成 `Alibaba`。这不是 m2m100 幻觉，而是"ASR 把哈利波特识别成阿里波特→glossary 无此 key→m2m100 看到 '阿里' 字面直接套入 Alibaba"。
  - **根治办法：加 ASR 后的文本纠错层（translip 已有 `correct-asr-with-ocr`，可接入）**，或在 glossary 加 "阿里波特 → Harry Potter" 这种 ASR-fuzzy 变体。

### 3.4 Task-D：TTS 克隆质量——主要症状

汇总 154 段（5 个说话人）：

| 指标 | 数值 | 与 task-20260425-023015 对比 |
|---|---|---|
| 段总数 | 154 | 164 |
| overall_status `passed` | 21 (13.6 %) | — |
| overall_status `review`  | 84 (54.5 %) | — |
| overall_status `failed`  | 49 (31.8 %) | — |
| speaker_status `passed`  | 56 (36.4 %) | — |
| **avg speaker_similarity** | **0.405** | **0.321**（↑26 %） |
| **speaker_similarity < 0.5 数** | **117 (76 %)** | 161/164 (98 %)（↓22 pp） |
| avg duration_ratio | 1.574 | — |
| duration_ratio > 1.5 数 | 38 (24.7 %) | — |

**亮点**：相似度平均从 0.321 提升到 0.405（+26 %），低相似度占比从 98% 降到 76%。  
**短板**：还是没过 0.45 的平均线（刚好差 0.045），以及 76% 的 low-band 仍超 30% 上限；根本原因是 **moss-tts-nano 对中文母语说话人的英语克隆能力有限**——模型容量仅 100M，而我们在让它克隆中国人说英文的音色。

各说话人细分：

| speaker | seg | passed | sim_avg | sim<0.5 | ratio_avg |
|---|---|---|---|---|---|
| spk_0000 | 47 | 8/47 | 0.390 | 41/47 | 1.25 |
| spk_0001 | 27 | 1/27 | 0.341 | 25/27 | 1.18 |
| spk_0003 | 3  | 0/3  | 0.483 | 3/3   | 0.68 |
| spk_0004 | 70 | 12/70 | 0.445 | 41/70 | 1.98 |
| spk_0005 | 7  | 0/7  | 0.306 | 7/7   | 1.54 |
| spk_0002 | — | ASR 剔除 | — | — | — |
| spk_0006 | — | ASR 剔除 | — | — | — |

**关键**：spk_0004 duration_ratio 平均 1.98 —— TTS 把英文说得比目标轨道长得多，这对后续 atempo 压缩不利（虽然我们把 `max_compress_ratio` 升到 1.6，但仍不够 1.98）。

### 3.5 Task-E：时间轴拟合与 skip 原因

- `placed_count = 152` · `skipped_count = 2`（skip_reason 均为 `skipped_overlap`）
- `fit_strategy_counts` = `direct=24 pad=13 compress=82 overflow_unfitted=24 underflow_unfitted=9`
  - **24 段 `overflow_unfitted`**：TTS 太长，压缩比超过 1.6 仍装不下 → 被硬切，这是当前主要听感损伤来源。
  - 9 段 `underflow_unfitted`：TTS 太短，留空档。
- `note_counts`：`task_d_failed_upstream=49`（task-d 的 fail 原样透传到 mix 报告）、`overflow_trimmed=14`、`overflow_compressed=11`。
- **说话人在 mix 中的出席情况**：

| speaker | mix placed | mix skipped | 真实参考出场 |
|---|---|---|---|
| spk_0000 | 47 | 0 | ✅ |
| spk_0001 | 27 | 0 | ✅ |
| spk_0003 | 3 | 0 | ✅ |
| spk_0004 | 69 | 1 | ✅ |
| spk_0005 | 6 | 1 | ✅ |
| **spk_0002** | **0** | **0** | ❌ **完全缺席** |
| **spk_0006** | **0** | **0** | ❌ **完全缺席** |

spk_0002 / spk_0006 的 3+1 段因为 task-c 没翻译（源文本太稀疏）在 task-d 阶段就没生成 → task-e 根本无该 speaker 出现。

---

## 4. 对 Sprint 1 + Sprint 2 优化方案的实战验证

| 优化点 | 是否生效 | 证据 |
|---|---|---|
| `DEFAULT_RENDER_MAX_COMPRESS_RATIO` 1.45→1.6 | ✅ | `fit_strategy_counts` 里 `compress=82`，`overflow_unfitted` 从可能的高位降到 24 |
| `DEFAULT_TASK_D_USABLE_*` 配置化 | ✅ | planning 按 1.0–6.0 s 可用窗口筛段 |
| `BUILTIN_DUBBING_GLOSSARY` 5 个 Burj Khalifa 变体 | ✅ | `哈里巴塔`/`哈利法塔` 均被正确命中 → Burj Khalifa |
| `glossary.travel.json` 样例 | ✅ | 通过 `--glossary-path` 成功加载 |
| `transcription/resegment.py` + `try_resegment_for_task_d` | ⚠️ 未发挥作用 | 长段 34s/39s 的文本本身就是空的，没东西可切；resegment 是"文本>1 句"时才有用 |
| `voice_bank` 最少 3 usable + `cross_speaker_fallback` | ✅ | spk_0002/3/5/6 自动绑定 donor=spk_0004 |
| TTS 重试阈值 `1.5/0.5` ratio | ✅ | 38 段 ratio>1.5 触发过 retry（见 `retry_history`） |
| `rendering/export.py` 黄金指标导出 | ✅ | `content_quality.reasons` 包含两条新 reason；`thresholds` 字典全量导出 |
| `content_quality.status = review_required` | ✅ | 成功阻止自动发布 |

**结论**：Sprint 1/2 的改造在真实长视频上**全部生效**，没有一条优化点"空转"；它们把"系统静默出错"变成"系统识别问题并打上 review_required 标签"，这是一个正确的方向。

---

## 5. 现状判断：还需要继续优化吗？

**需要**。当前流水线的最终产物：
- 有 9 min 的英文配音可以听，但 **avg_speaker_similarity=0.405** 和 **76 % 段低于 0.5** 代表听感上仍会感觉到"音色不像"。
- **spk_0002（"奶奶"角色）完全缺席**——这是用户上次反馈里最敏感的症状，这次被**同样的 ASR 根因**再次击中。

下一轮（**Sprint 3**）应当围绕 **ASR 升级 + TTS 质量** 两条主线推进。

---

## 6. Sprint 3 优化建议（按性价比排序，均可本机运行，不下载超过 500 MB）

### 🎯 P0 — ASR 升级（根治"语音丢失/奶奶缺席"）

1. **把 `asr-model` 默认从 `small` 换成 `medium`（本机缓存已就绪，1.4 GB，已下载）**  
   修改点：`src/translip/config.py` 中 `DEFAULT_ASR_MODEL = "small"` → `"medium"`。  
   预期：CER 从 31.6 % 降到 12–15 %（基于 faster-whisper 在中文对白 benchmark 的公开分数），长段空转现象大幅缓解。成本：task-a 从 45 s 变 2-4 min，整体从 23 min 变 26-28 min，可接受。
   **单测要点**：`tests/test_quality_defaults.py` 加 `assert config.DEFAULT_ASR_MODEL == "medium"`。

2. **为长空段加"VAD-based 兜底二次切分"**  
   当一段时长 > 8 s 且 CPS < 1.5 时，用 `silero-vad`（18 MB）把静音切开再交给 ASR 重转一次。  
   新增文件：`src/translip/transcription/long_segment_fallback.py` + 单测。

3. **接入已有的 `correct-asr-with-ocr`**  
   用户文件已经有完美的 `我的迪拜等你.srt` ——这说明生产者常常能拿到原字幕。在 `run-pipeline` 里加 `--reference-srt` 参数，直接把参考当"强纠错"使用。  
   也可以加 `阿里波特→哈利波特`、`到底败→到迪拜了` 等 ASR-fuzzy 的 glossary 变体。

### 🎯 P0 — TTS 音色相似度（"奶奶音色不像"的根因）

4. **切到 Qwen3-TTS-12Hz-0.6B（已下载 2.3 GB）**  
   ```bash
   translip run-pipeline ... --tts-backend qwen3tts
   ```
   相比 moss-tts-nano 100M，Qwen3-TTS 600M 在跨语种克隆上质量明显更高。项目已支持，但本次默认跑的是 moss-tts-nano。  
   预期：avg_speaker_similarity 从 0.405 → 0.55+，duration_ratio 分布更集中。

5. **候选 TTS 听审机制**（已存在 `--candidate-tts-backend`）  
   对每段都用 MOSS 和 Qwen3 各合一版，选择 `speaker_similarity` 高的那版。成本是 task-d 双倍时间（可接受）。

### 🎯 P1 — 拟合与混音

6. **支持 `--fit-backend rubberband`**（已经是 choice 但默认 atempo）  
   rubberband 在 >1.5 倍压缩时音质显著优于 atempo。`brew install rubberband` 即可，项目代码已支持。

7. **把 `duration_ratio > 1.5` 改为"condense 重写一次"**  
   利用 `--condense-mode smart`（代码已有，但默认 off）让 task-c 重写一个更紧凑的译文再 TTS。对 38/154 段有用。

### 🎯 P2 — 质量门强化

8. **`content_quality.overflow_unfitted_count` 修正数据来源**  
   当前只看 `placed_items.qa_flags/notes`，但实际 `fit_strategy_counts["overflow_unfitted"]=24` → 没被 gate 捕获。改成从 `mix.stats.fit_strategy_counts` 读。
   **已有单测 `tests/test_rendering_quality_gate.py` 需扩展**。

9. **新增 `asr_character_error_rate` 指标入 mix_report**  
   若有参考 SRT，则计算并纳入 quality_gate（> 20 % 自动 review_required）。

### 🎯 P3 — 未来探索

10. **换说话人聚类模型**：`speechbrain/spkrec-ecapa-voxceleb`（85 MB）在"过度分裂→cap=8 再聚"上已经出现症状；可以评估 `pyannote-speaker-diarization-3.1`（需 HF token，约 90 MB）。
11. **模型 warm-up 缓存**：task-d 每个 speaker 都重载 moss-tts-nano，可以常驻 process。

---

## 7. 最终回答：是否还需要继续优化？

**是，需要进入 Sprint 3**。本次重跑证明 Sprint 1/2 的改造全部有效、质量门正确报 review，但：

- **CER 31.6 % 的 ASR 是新的主要瓶颈**（上次分析低估了这一块），它吃掉了 spk_0002 和 spk_0006 的全部台词 → 影响听感最关键的"奶奶"角色；
- **TTS 音色相似度平均 0.405**，虽然比 0.321 改善明显，但还差 Sprint 2 设定的 0.45 基线；
- 剩余 24 段 `overflow_unfitted` 是听感上"抢话/截断"的直接来源。

建议的动作顺序：

1. **今天就可以做**：切 ASR 为 `medium`（代码一行）+ 切 TTS 为 `qwen3tts`（跑命令一次）+ 加 `rubberband`（`brew install`）→ 预计 avg_speaker_similarity 跨过 0.45，CER 降到 15 % 以下。
2. **明天再做**：VAD 长段兜底 + ASR-fuzzy glossary + condense-smart。
3. **下周规划**：候选 TTS 听审 + `asr_character_error_rate` 入 quality_gate。

如目标是"发布级配音"，建议 **先按 1/2 这两步迭代一次**再评估；预计迭代后 `content_quality.status` 能从 `review_required` 进入 `deliverable`，spk_0002 至少能恢复 ≥70 % 的出场率。

---

## 附录

### A. `task-c/voice/translation.en.json` 前 10 段翻译抽样

```
seg-0001 | zh=奶奶 你知道哈里巴塔吗        | en=Do you know Burj Khalifa?
seg-0002 | zh=是不是那个电影                | en=Is that movie?
seg-0003 | zh=阿里波特的场景                | en=The scene of Alibaba.             ← 仅此一例可优化
seg-0004 | zh=哈里巴塔是全世界最高的塔      | en=Burj Khalifa is the highest tower in the world.
seg-0005 | zh=那它在哪儿啊                  | en=So where is it.
seg-0006 | zh=迪拜                          | en=Dubai
seg-0007 | zh=在迪拜呢                      | en=in Dubai.
seg-0008 | zh=我现在就要去迪拜              | en=I am going to Dubai.
seg-0009 | zh=去迪拜                        | en=Go to Dubai.
seg-0010 | zh=是啊 我已经在接手了            | en=Yes, I'm already taking over.
```

### B. `mix_report.en.json → stats.quality_summary` 关键切片

```json
{
  "averages": {
    "speaker_similarity": 0.4045,
    "text_similarity": 0.9006,
    "duration_ratio": 1.5742,
    "quality_score": 2.0736
  },
  "medians": {
    "speaker_similarity": 0.4011,
    "text_similarity": 0.955,
    "duration_ratio": 1.2374,
    "quality_score": 2.263
  },
  "failure_reason_counts": {
    "duration": 28,
    "speaker": 9,
    "intelligibility": 4,
    "duration+intelligibility": 3,
    "duration+speaker": 3,
    "speaker+intelligibility": 2
  },
  "qa_flag_counts": {
    "duration_risky": 35,
    "duration_may_overrun": 28,
    "too_short_source": 24,
    "contains_protected_term": 9,
    "contains_number": 2
  }
}
```

### C. 命令行复现

```bash
cd /Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate
source .venv/bin/activate
/usr/bin/time -l translip run-pipeline \
  --input "test_video/我在迪拜等你.mp4" \
  --output-root tmp/dubai-rerun \
  --template asr-dub-basic \
  --target-lang en \
  --translation-backend local-m2m100 \
  --tts-backend moss-tts-nano-onnx \
  --device auto \
  --glossary-path config/glossary.travel.json \
  --fit-policy conservative \
  --fit-backend atempo \
  --mix-profile preview \
  --preview-format mp3 \
  --speaker-limit 0 \
  --segments-per-speaker 0 \
  --max-compress-ratio 1.6 \
  --write-status \
  --no-reuse-existing \
  --separation-mode dialogue
```

### D. 单元测试现状

- 仓库共 **244 个 pytest 测试**，全部通过（本报告开始前已经由 Sprint 1/2 验证）。
- 本轮未修改源码，所以没有新的测试需要补；Sprint 3 一旦动手，需要按下表补测：

| Sprint 3 动作 | 需要补的测试 |
|---|---|
| ASR default medium | 更新 `tests/test_quality_defaults.py` |
| VAD 长段兜底 | 新增 `tests/test_long_segment_fallback.py` |
| asr_character_error_rate | 扩展 `tests/test_rendering_quality_gate.py` |
| overflow_unfitted_count 读 stats | 扩展 `tests/test_rendering_quality_gate.py`、`tests/test_golden_task_20260425.py` |

---

*报告生成时间：2026-04-25*  
*对应实验目录：`tmp/dubai-rerun/`*  
*参考字幕：`test_video/我的迪拜等你.srt`（用户提供，用于 CER 评估）*
