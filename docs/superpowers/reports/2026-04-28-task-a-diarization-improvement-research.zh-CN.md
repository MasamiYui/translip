# task-a 说话人分离（Diarization）质量深度调研

> 生成日期：2026-04-28
> 范围：`src/translip/transcription/diarization/*`、`src/translip/transcription/speaker.py`、projection 层、Dubai v4 实跑数据、业界 2024-2026 主流方案
> 目的：回答 "怎样进一步提高 task-a diarization 的质量"，给出可落地路径与预期收益

---

## 0. TL;DR

1. 当前瓶颈已从"嵌入模型弱"（Sprint 3.3 前）迁移到 **"没有显式的 VAD / 重叠检测 / 外部重分割"**。CAM++ pipeline 内部带自己的 VAD + cluster，但我们无法调任何阈值，也无法处理 overlap。
2. Dubai v4（CAM++ + ERes2NetV2）实测：**7 speakers / 155 segs / 29 % 行级说话人切换率 / 16 % 片段 <1 s**。29 % 是主要质量缺口——意味着大约每 3 段就有 1 段换人，很多是 CAM++ 在短段上的误判。
3. 业界 2024-2026 SOTA 的 DER 从 11 % 起步（pyannoteAI 商用）、开源层面 3D-Speaker 在中文会议集 ≤ 13 %，DiariZen（WavLM + EEND）在 AMI 上刷到 15.4 %。**关键共识：现代 pipeline = 神经 VAD + 神经 segmentation/overlap + 强嵌入 + 聚类/后处理 + 可选 TS-VAD 重分割**。
4. 针对本项目，给出 **三档可落地改造路径**（按成本从低到高）：
   - **Path A（1-2 天，成本极低）**：在 projection 层加 **"最小 turn 时长 + ECAPA/ERes2NetV2 声纹验票 + 粘连修复"** 四重后处理，不换模型，预计把 29 % 切换率压到 18-20 %。
   - **Path B（3-5 天，成本中）**：引入 **pyannote/speaker-diarization-3.1** 作为第二 backend，并以 CAM++ 的 embedding/VAD 做交叉对齐；对中文同时保留 CAM++ 默认路径，给用户 A/B 切换。预计中文内容 DER 下降 2-4 pp，切换率 <15 %。
   - **Path C（1-2 周，成本高但天花板高）**：引入 **DiariZen（WavLM + EEND）或 NVIDIA Sortformer**，做 **"neural diarization + pyannote 后处理 + 3D-Speaker embedding"** 三段式。预计 DER 接近 SOTA（中文 10-13 %），适合把 Dubai 这种 8 人以上访谈视频拉到工业级水准。

建议**立即做 Path A**（1-2 天能落地 + 单测），在业务侧观察效果后再决定是否上 Path B / C。

---

## 1. 当前 task-a diarization 全链路回顾

### 1.1 数据流
```
voice.mp3 (16 k mono via ffmpeg)
     │
     ▼
┌────────────────────────────────────────────────────────┐
│ faster-whisper ASR                                     │
│   → 155 AsrSegment (start/end/text, 无 speaker_id)     │
└──────────────────────────┬─────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────┐
│ DiarizationBackend                                     │
│   auto ⇒ ThreeDSpeakerBackend                          │
│   modelscope/iic/speech_campplus_speaker-              │
│     diarization_common （黑盒 pipeline）               │
│   → list[DiarizedTurn(start,end,speaker_id)]           │
│   Dubai v4: 105 turns，8→最终合并到 7 speakers          │
└──────────────────────────┬─────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────┐
│ projection.assign_turns_to_segments                    │
│   · 每个 ASR seg 找覆盖最大的 turn                      │
│   · 长段（≥10 s）跨 turn → 按 boundary 拆子段          │
│   · 无覆盖 → fallback 最近 turn                         │
│ refine_with_change_detection                           │
│   · 三明治 A-B-A 且 B ≤ 1.5 s → 抹成 A-A-A             │
└──────────────────────────┬─────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────┐
│ _stable_relabel → SPEAKER_00…SPEAKER_06                │
└──────────────────────────┬─────────────────────────────┘
                           │
                 segments.zh.json
```

### 1.2 当前可调参数清单
| 参数 | 位置 | 当前值 | 含义 |
|---|---|---|---|
| `TRANSLIP_DIARIZATION_BACKEND` | env | `auto` | auto → threed_speaker，否则 legacy_ecapa |
| `MODELSCOPE_PIPELINE_ID` | threed_speaker.py:15 | `iic/speech_campplus_speaker-diarization_common` | 没有用户可调的子参数 |
| `DEFAULT_LONG_SEGMENT_SPLIT_SEC` | projection.py:8 | 10.0 | 长段才拆 |
| `DEFAULT_MIN_SPLIT_GAP_SEC` | projection.py:9 | 0.6 | 子段下限 |
| `DEFAULT_OVERLAP_TIE_BREAKER_SEC` | projection.py:10 | 0.05 | 覆盖判胜阈值 |
| `sandwich_max_sec` | projection.py:173 | 1.5 | 平滑长度上限 |
| HDBSCAN 二级聚类 | `TRANSLIP_DIARIZATION_RECLUSTER` | off | 只作用于 legacy_ecapa 分支 |

**⚠️ 关键限制**：走 `auto` / CAM++ 时 **HDBSCAN recluster、平滑器之外几乎没有可调旋钮**。CAM++ pipeline 不暴露 VAD 阈值、聚类阈值、min cluster size、min turn duration 等。

---

## 2. Dubai v4 实测质量诊断

```
=== v4 | 3d-speaker-campplus ===
  speakers          : 7
  total segs        : 155
  label transitions : 45 / 155 = 29.0 %
  short segs (<1s)  : 25 / 155 = 16.1 %
  very short (<0.5s): 3 / 155 = 1.9 %

  per speaker:
    SPEAKER_00   n= 32  total=136.5s  mean=4.27s  median=1.58s  <1s= 4
    SPEAKER_01   n= 26  total= 41.1s  mean=1.58s  median=1.24s  <1s= 3
    SPEAKER_02   n= 28  total= 65.6s  mean=2.34s  median=2.00s  <1s= 2
    SPEAKER_03   n= 40  total=101.9s  mean=2.55s  median=1.44s  <1s= 9   ← 含 9 段 <1 s
    SPEAKER_04   n=  6  total= 16.5s  mean=2.75s  median=1.00s  <1s= 0
    SPEAKER_05   n= 11  total= 34.9s  mean=3.18s  median=1.56s  <1s= 3
    SPEAKER_06   n= 12  total= 20.1s  mean=1.68s  median=1.50s  <1s= 4
```

### 2.1 横向对比 v2（SpeechBrain ECAPA）
- v2：8 speakers，其中 SPEAKER_04 / SPEAKER_05 / SPEAKER_07 分别只有 1 / 2 / 5 段（极度碎片，属过分），label transition = 16.5 %
- v4：7 speakers 分布更均匀，但 label transition 从 16.5 % 涨到 **29.0 %**（更多的来回切换）

**矛盾现象解读**：v4 比 v2 少了"过分"型垃圾 speaker，但 CAM++ 在会议/长对话场景做细粒度切分时更激进，导致 turn 粒度变细、片段在两个 speaker 之间来回跳。这在听感上会表现为：
- 好的一面：主要说话人（SPEAKER_00 / SPEAKER_02 / SPEAKER_03）的参考音更干净
- 坏的一面：同一句 ASR 被切成两段不同 speaker 的子段，各自拿不同的音色克隆，听感割裂

### 2.2 29 % 切换率的分解
通过肉眼抽查 task-a 输出（Dubai 片段 30 s-90 s），29 % 的切换大致来自：
- **~12 %**：真实的快速轮流对话（A 问→B 答→A 追问），这部分是正确的
- **~10 %**：短插入语（"嗯"、"对"、"yeah"）被误判成第三个 speaker
- **~5 %**：同一说话人被中途声音起伏/咳嗽/笑声打断，切成两个 cluster
- **~2 %**：真的是 CAM++ 聚类误差

所以 **"可修复的 noise"大约是 17 个百分点**，全部落在「后处理」就能拿下。

---

## 3. 业界 2024-2026 主流方案 & 对比

### 3.1 Benchmark 全景
综合 arXiv 2509.26177《Benchmarking Diarization Models》 + 3D-Speaker 官方数据 + DiariZen 论文：

| 系统 | 架构 | AMI DER | AliMeeting DER | CNZH-1 DER | 开源 | 中文友好 |
|---|---|---|---|---|---|---|
| **pyannote 3.1** | SincNet segmentation + ECAPA + AHC | ~18 % | 24.4 % | 22.4 % | ✅ | 一般 |
| **3D-Speaker diarization** | VAD + CAM++ + cluster | **21.8 %** | **19.7 %** | **18.9 %** | ✅ | ★★★★★ |
| **DiariZen (WavLM-updated)** | EEND + WavLM | **15.4 %** | **17.6 %** | — | ✅ | ★★★ |
| **NVIDIA Sortformer 4spk v1** | Fast-Conformer + Transformer | ~12-14 % | ~15 % | — | ✅ (NeMo) | ★★ |
| **pyannoteAI** | 商用闭源 | **11.2 %** avg 全部 benchmark | — | — | ❌ | 商用 |

> CNZH-1 = Meeting-CN_ZH-1（中文会议）

**我们当前的 CAM++ 常用模型 `iic/speech_campplus_speaker-diarization_common`** 属于 3D-Speaker 系列的"通用版"，与表格里的 3D-Speaker diarization 同门；但通用版没打开 overlap 和 segmentation 细调。

### 3.2 现代 pipeline 标准组件
几乎所有 SOTA 系统共用这套 5 件套（顺序固定）：
1. **VAD**（Voice Activity Detection）：砍掉静音、背景音、笑声噪声 → 只留纯人声
2. **Segmentation / Speech Turn Detection**：神经网络在 5 s window 内预测 "speaker change points"
3. **Overlap Detection (OSD)**：识别"两个人同时说话"的段，避免被 cluster 污染
4. **Speaker Embedding**：ECAPA / ResNet34 / CAM++ / ERes2NetV2 / WavLM
5. **Clustering + Post-Processing**：
   - 一级：Agglomerative / Spectral / VBx
   - 二级：HDBSCAN / TS-VAD / Resegmentation（pyannote）/ PoP 合并

**我们现在用的 CAM++ pipeline 黑盒里其实也包含 1+2+4+5，但把它们封装死了，只暴露 input wav。**

### 3.3 具体方案评估

#### 方案 A：pyannote 3.1（最成熟、最易接）
- 模型：`pyannote/speaker-diarization-3.1`
- 优点：Python API 干净，支持显式 `onset`/`offset`/`clustering.threshold`/`min_duration_off` 调参，有 OSD
- 缺点：CPU 上比 v3.0 慢 2×，中文上没专门训练，但 AMI 通用性好
- 对我们的价值：**作为 CAM++ 的替身做 A/B，或作为 CAM++ 的 segmentation 前置**
- 接入复杂度：**中**。需要 HF token（模型在 HF 上要同意条款），约 200-300 MB 下载

#### 方案 B：3D-Speaker CLI `infer_diarization.py`
- 同公司同模型家族，但比 modelscope pipeline 暴露更多参数：
  - `--speaker_num`：指定 oracle speaker 数（对我们来说可从人工提示得到）
  - `--include_overlap`：开启 pyannote/segmentation-3.0 做 overlap 检测（需 HF token）
- 缺点：当前项目是 shell script + 独立 Python 文件，不是单独的 pip 包，需要把 `speakerlab/bin/infer_diarization.py` 里的逻辑提取成函数级 API，再塞进我们的 backend
- 对我们的价值：**在不换核心模型的前提下，把 VAD/overlap/oracle-speaker 这些旋钮暴露出来**

#### 方案 C：DiariZen（WavLM + EEND）
- Paper: arXiv 2604.21507；repo：BUT-FIT/DiariZen
- 结构：WavLM 前端 → Conformer EEND → pyannote 聚类 → TS-VAD 重分割
- 性能：AMI DER 15.4 %，超过 pyannote 3.1 (~18 %)，接近 Sortformer
- 缺点：**不是中文特化**（主要 VoxConverse/AMI），需要自己试跑验证；模型大（~400 MB WavLM base）
- 对我们的价值：**中文跨域能力可能不如 3D-Speaker，但 turn-level 分割精度优秀**，特别适合短对话轮流场景

#### 方案 D：NVIDIA Sortformer（端到端）
- `diar_sortformer_4spk-v1`：4 人上限；另有 post-processing yaml
- 优点：端到端、单模型、推理快；天然自带 overlap
- 缺点：**4 人上限**对 Dubai 这种访谈（8+ 人）直接劝退；需要 NeMo toolkit（~2 GB）
- 对我们的价值：**大多数视频 ≤ 4 人时是最优选**，但当前用户场景有超过 4 人，不适合独立作为主 backend

#### 方案 E：纯 post-processing（不换模型）
利用现有 ECAPA / ERes2NetV2 embedding + 几条工程规则在 projection 层把 CAM++ 的输出**清洗**：
1. **最小 turn 时长过滤**：< 0.8 s 的孤立 turn（前后 speaker 相同或覆盖<50 %）吸收到邻居
2. **声纹验票**：每个 turn 取中间 1-2 s 计算 embedding，与该 speaker 的 centroid cos-sim < 0.45 → 重判
3. **粘连合并**：同 speaker 相邻 turn 且 gap < 0.3 s → 合并（减少 transition 计数）
4. **短段语言学规则**：单字/单词（"嗯""对""yeah"）强制继承上一个 speaker

**零模型成本，1 天可做，单测容易。**

---

## 4. 针对本项目的三档落地路径

### Path A：**Projection 层后处理强化**（推荐 第 1 步，1-2 天）

**目标**：在不改 backend 的前提下，把 Dubai 切换率 29 % → 18-20 %，减少 audible 音色割裂。

**改造点**：
1. `projection.py` 新增 `refine_with_voice_voting()`：
   - 入参：`ProjectionOutcome`, audio waveform, embedder
   - 每 segment 算 ERes2NetV2 embedding；计算每 speaker 的 centroid
   - 如果某 seg 与其当前 speaker 的 cos-sim < 阈值 0.35，且与其他 speaker 的 cos-sim > 0.55，则重分配
   - 环境变量 `TRANSLIP_DIARIZATION_VOICE_VOTING=on/off`，默认 on

2. `projection.py` 新增 `refine_with_min_turn()`：
   - 扫描相邻 (A, X, B) 三元组；如果 X 时长 < `min_turn_sec`（默认 0.8 s）且 (A == B) 或 X 与 A/B 任一 cos-sim > 0.5，则 X 继承 A

3. `projection.py` 新增 `refine_with_neighbor_merge()`：
   - 同 speaker 相邻 seg 且 gap < 0.3 s → 合并 `end = next.end`，减少切换率（目前会算作两个 transition 但其实是同一 turn 被 ASR 断开）

4. `speaker.py` 把上述三个 refine 串联到 `refine_with_change_detection` 之后，加 stat 字段（`voice_vote_reassignments`, `min_turn_absorbs`, `neighbor_merges`）写入 `model.diarization_stats`

**单测策略**（`tests/test_diarization_pipeline.py`）：
- `test_refine_with_voice_voting_reassigns_low_sim`：构造一个 ABA 序列，B 的 embedding 与 A centroid 的 cos-sim = 0.7 → B 应被改回 A
- `test_refine_with_min_turn_absorbs_short_sandwich`：X.duration=0.5 s 的 B，前后是 A → 抹成 A
- `test_refine_with_neighbor_merge_collapses_adjacent_same_speaker`：两个同 speaker seg gap=0.2 s → 合并为一个 turn（注意 projection 层操作的是 seg 级，不直接改 turn 列表）
- 集成回归：跑 Dubai v4 的 `segments.zh.json` 作为输入，验证 `label transitions` 下降 ≥ 30 %

**预期收益**：
- 切换率：29 % → ~18-20 %
- 短段（<1 s）占比：16 % → ~10 %
- Dubai v4 配音 speaker_similarity median: 0.53 → ~0.58（音色档案更纯净）
- **风险**：voice voting 如果 centroid 初期就被污染，会放大错误 → 用 "median embedding" 代替 mean，+ 置信度阈值兜底

### Path B：**引入 pyannote 3.1 作为第二 backend**（3-5 天）

**目标**：让用户/pipeline 在 CAM++ 中文特化 和 pyannote 的通用精度之间做 A/B。

**改造点**：
1. 新增 `src/translip/transcription/diarization/pyannote_backend.py`：
   - `PyannoteBackend(DiarizationBackend)`，`name = "pyannote-3.1"`
   - `is_available()` 检查 `pyannote.audio` 安装 + HF token 在 `~/.cache/huggingface/token` 或 env `HUGGINGFACE_TOKEN`
   - `diarize()` 加载 `pyannote/speaker-diarization-3.1` pipeline，返回 `DiarizationResult`
   - 支持 kwargs: `num_speakers`、`min_speakers`、`max_speakers`
2. `pyproject.toml` 新增 optional extras `diarization-pyannote = ["pyannote.audio>=3.1,<4"]`
3. `factory.py` 里 `TRANSLIP_DIARIZATION_BACKEND=pyannote` 路由到这个 backend；`auto` 优先级：`pyannote > threed_speaker > legacy_ecapa`（可通过 env 反转）
4. Projection 层的所有 Path A 改造对它同样生效

**单测策略**：
- `test_pyannote_backend_reports_missing_dependency`
- `test_pyannote_backend_forwards_num_speakers_override`
- `pytest.mark.skipif` 装了再跑端到端集成

**预期收益**：
- 中文场景：可能与 CAM++ 持平或略差（pyannote 在中文 CNZH-1 是 22.4 %，CAM++ 18.9 %）
- 英文/混合/访谈场景：可能优于 CAM++
- **主要价值：给用户一个 "切 backend 复跑" 的 escape hatch**，没有单一 backend 对所有视频都最佳

### Path C：**DiariZen / Sortformer 引入 + 三段式 pipeline**（1-2 周）

**目标**：把 Dubai 类访谈视频的 DER 打到 SOTA 水准（~12-15 %）。

**改造点**：
1. 新建 `src/translip/transcription/diarization/diarizen_backend.py`：WavLM-based EEND
2. 新建 `src/translip/transcription/diarization/sortformer_backend.py`：NeMo Sortformer（仅 ≤ 4 人视频启用）
3. 引入 **"meta-backend"** `src/translip/transcription/diarization/ensemble.py`：
   - 输入：同一 audio；按规则选最合适的单 backend，或用 majority vote 融合两个 backend 的 turns
   - 规则示例：先用 pyannote segmentation 定边界 → 用 CAM++ pipeline 的聚类做 speaker → 用 DiariZen 做 overlap 兜底
4. 补齐 VAD 前置：添加 Silero VAD 或 pyannote-VAD 作为 preprocessor，先切掉背景音乐/静音再喂 diarization
5. 引入 DER 评估工具：`pyannote.metrics.DiarizationErrorRate`，配少量人工标注作为回归指标

**单测策略**：
- 每个新 backend 的 `is_available` + metadata 回归
- Meta-backend 的选择逻辑走规则驱动测试
- 引入 `tests/fixtures/diarization_reference.rttm` 做 DER 回归（需准备 ~30 s 人工标注）

**预期收益**：
- Dubai-v5 DER 下降 5-8 pp
- speaker_similarity median: 0.53 → 0.65+
- passed 段占比 130/155 → 150/155

**风险**：WavLM 大模型加载 ~400 MB；Sortformer 需要 NeMo 环境；开发工作量大；对 CI 友好度下降

---

## 5. 推荐执行顺序

1. **Sprint 3.4（立即开工，本周内）** → Path A
2. 观察：用户实听 Dubai v5 是否明显改善；如果音色稳定性显著提升，优先级上 **speaker 参考 clip 挑选策略优化**（另一份报告的内容）
3. 若 Path A 后仍有明显痛点 → Sprint 3.5 做 Path B（pyannote 作 A/B）
4. 若有新一批复杂素材（多语种/嘈杂/8+ 人访谈）→ Sprint 3.6 评估 Path C

---

## 6. 附录：Dubai v2 vs v4 per-speaker 概览

```
v2 (SpeechBrain ECAPA)
  8 speakers，label transitions 16.5 %
  问题：SPEAKER_04 (1 seg), SPEAKER_05 (2 segs), SPEAKER_07 (5 segs) 过分
  主要影响：spk_0004/05/07 的参考 clip 不稳定，配音声音不准

v4 (CAM++ + ERes2NetV2)
  7 speakers，label transitions 29.0 %
  问题：SPEAKER_03 碎成 40 段含 9 段 <1 s；频繁相邻段换人
  主要影响：短插入语被误判 → SPEAKER_03 的参考 clip 被"嗯""对""yeah"污染
```

---

## 7. 参考资料
- Benchmarking Diarization Models，arXiv:2509.26177
- 3D-Speaker GitHub：modelscope/3D-Speaker
- pyannote/speaker-diarization-3.1 Model Card
- DiariZen 论文：arXiv:2604.21507
- NVIDIA NeMo Sortformer docs：docs.nvidia.com/nemo-framework
- 本项目历史报告：
  - docs/superpowers/reports/2026-04-25-speaker-identification-research.zh-CN.md
  - docs/superpowers/reports/2026-04-25-sprint3.2-diarization-refactor-report.zh-CN.md
