# 说话人识别（Diarization + Voice-Print）改造调研报告

- 报告编号：`2026-04-25-speaker-identification-research`
- 作者：translip pipeline team
- 触发事件：Sprint 3 v2 A/B 人耳验证发现「说话人识别」仍是首要痛点（奶奶在 v1/v2 均缺席，v2 medium 反而把奶奶段并入 `spk_0000/0001`，`spk_0006` 丢失）
- 目标：给出一条可以在 Apple M4 / 16 GB / 模型 ≤500 MB 约束下、以工程化方式替换当前单层 ECAPA + Agglomerative 方案的完整路径

---

## 1. 问题回顾与根因定位

### 1.1 现有实现（单文件 297 行，路径 `src/translip/transcription/speaker.py`）

调用链：`transcription/runner.py:72` → `assign_speaker_labels(audio_path, segments, requested_device)`

```
ASR 段 (faster-whisper)
   │  silero-vad 已嵌在 whisper 内部
   ▼
_build_embedding_groups(gap=0.45s, group≤8s, ≤5 段)   ← speaker.py:86
   ▼
_expanded_bounds(margin=0.2s, min_window=2.0s)         ← speaker.py:64
   ▼
_segment_embedding: SpeechBrain ECAPA-TDNN             ← speaker_embedding.py
   ▼
_is_single_speaker: P20 ≥ 0.52                         ← speaker.py:156
   ▼
_cluster_embeddings:                                   ← speaker.py:173
   AgglomerativeClustering(cosine, average,
                           distance_threshold=0.38)
   cap = min(8, n//6+1)                                ← speaker.py:165
   ▼
_smooth_cluster_ids: 三段夹心且中间 ≤1.5s 向邻居靠拢    ← speaker.py:217
   ▼
_stable_relabel: SPEAKER_00..N                         ← speaker.py:205
   ▼
task-b: speakers/runner.py 做 voice bank 增强
```

### 1.2 五大症状（对应 Dubai 视频 v1/v2 观察）

| # | 症状 | 现象 | 根因 | 代码位置 |
|---|------|------|------|----------|
| S1 | 说话人合并 | 奶奶被并到 `spk_0000/0001` | embedding 窗口=整段 ASR + 0.2s，长段跨多人仍只出 1 个向量 | `_expanded_window` (speaker.py:37) |
| S2 | 组内混人 | 相邻但不同人的段被拼进同一组 | gap ≤0.45s 即合并，忽略说话人变化点 | `_build_embedding_groups` (speaker.py:86) |
| S3 | 说话人丢失 | `spk_0006` 彻底消失 | cap = `max(2, min(8, n//6+1))`，长视频、低频说话人被强行并入主说话人 | `_speaker_cap` (speaker.py:165) |
| S4 | 误判单人 | 短对话（两人轮流 3~4 句）整批打为 `SPEAKER_00` | `_is_single_speaker` 使用 P20≥0.52，噪声大场景阈值过松 | `_is_single_speaker` (speaker.py:156) |
| S5 | 漂移 | 背景音乐/笑声夹杂处 cluster id 抖动 | 仅有 1.5s 三段夹心平滑，窗口太短；无 VAD 预筛 | `_smooth_cluster_ids` (speaker.py:217) |

### 1.3 量化锚点（Dubai 9 分 12 秒样本）

- 人工标注：7 位说话人（含奶奶、小女孩等低频角色）
- v1 small：识别出 5 人，奶奶/小女孩缺失，DER ≈ 34%
- v2 medium：识别出 4 人（更严重），奶奶与主角合并，`spk_0006` 丢失
- 现有实现**没有独立 VAD**（silero 藏在 whisper 里）、**没有真正 diarization**，所有聚类都附生于 ASR 段边界——这是导致 S1–S5 的结构性原因

---

## 2. 2024–2026 开源项目与论文矩阵

| 方案 | 机构 / 发布 | License | 核心架构 | 中文/混合场景 DER | 离线可用 | 模型大小 | 对本机的适配难度 |
|------|-------------|---------|----------|------------------|---------|---------|------------------|
| **pyannote 3.1** `speaker-diarization-3.1` | HuggingFace / 2024 | MIT（权重 gated） | segmentation-3.0 + wespeaker-resnet34-LM embedding + Agglomerative | AISHELL-4 12.2% / AMI 18.8% / DIHARD3 21.7% / VoxConverse 11.3% | ✅（需 HF token 首次下载） | 约 95 MB | ⭐⭐（Metal 走 CPU 即可） |
| **pyannote community-1** (4.0) | HuggingFace / 2025-09-29 | MIT | segmentation-3.0 + wespeaker + **VBx** 聚类 + exclusive diarization | 与 3.1 同级，重叠段更稳 | ✅ | 约 100 MB | ⭐⭐（VBx 新依赖） |
| **NVIDIA Sortformer** `diar_sortformer_4spk-v1` | NVIDIA NeMo / 2024 | 商用-友好，Apache 2.0 | 端到端 Transformer，Arrival-Order Speaker Cache | CALLHOME-2spk 5.85% DER | ✅ | 约 110 MB | ⭐⭐⭐（NeMo 依赖较重，**最大 4 人**，9 分钟 7 人场景风险大） |
| **3D-Speaker (modelscope `iic/speech_campplus_speaker-diarization_common`)** | 阿里达摩院 / 2023–2025 持续 | Apache 2.0 | FSMN-VAD + CAM++ (Chinese 200k-Spkrs) + 频谱聚类 + 重分配 | **Meeting-CN_ZH 18.91%（优于 pyannote 22.37%）**；2–10 人真实对话 8.0% | ✅（modelscope 本地缓存即可） | CAM++ 7.2 MB / VAD 2 MB / 总 <30 MB | ⭐（中文最优，首选方案） |
| **ERes2NetV2** `iic/speech_eres2netv2_sv_zh-cn_16k-common` | 阿里达摩院 / 2024 | Apache 2.0 | ERes2Net 双分支 | VoxCeleb1-O EER 0.61% / CNCeleb EER 6.14% | ✅ | 17.8 MB | ⭐（作为跨视频 embedding 替换 ECAPA） |
| **DiariZen-Large** (BUT Speech@FIT) | 2024–2025 | MIT | EEND-VC + WavLM backbone + VBx | AMI/AISHELL-4 最新 SOTA | ⚠️（WavLM 约 317 MB，刚好卡在 500 MB 上限） | 约 330 MB | ⭐⭐⭐（Metal 推理需验证，性能回退风险） |
| **WeSpeaker** | WeNet / 2023–2025 持续 | Apache 2.0 | ResNet34-LM / CAM++ / ReDimNet 权重库 | VoxCeleb1-O 0.6%–0.8% | ✅ | 10–40 MB | ⭐⭐（作为 embedding 源与 pyannote 对齐） |
| **ReDimNet** | 2024 Interspeech | Apache 2.0 | 维度重组骨干 | VoxCeleb1-O 0.48% | ✅（权重需手动获取） | 8–30 MB | ⭐⭐（学术领先，工程资源相对少） |
| **EEND-TA** (Target-Speaker attention) | JSALT 2024 | 论文+复现代码 | 端到端 + 目标说话人注意力 | CALLHOME 10%–12% | ⚠️ | 50 MB | ⭐⭐⭐⭐（复现成本高，不推荐在本 Sprint 使用） |
| **UniSpeaker** | 2024 论文 | — | 多任务 SSL + diarization head | AMI 近 SOTA | ❌（无官方权重） | — | ⭐⭐⭐⭐（仅观望） |

### 2.1 关键论文锚点

1. Plaquet, Bredin. *Powerset multi-class cross entropy for neural speaker diarization.* Interspeech 2023. — pyannote segmentation-3.0 的理论基础，解决重叠段建模。
2. Park et al. *Sortformer: Seamless Integration of Speaker Diarization and ASR by Arrival-Time Ordering.* 2024. — Sortformer 架构与 AOSC 机制。
3. Chen et al. *CAM++: A Fast and Efficient Network for Speaker Verification Using Context-Aware Masking.* Interspeech 2023 + 3D-Speaker 技术报告。
4. Chen et al. *ERes2NetV2: Boosting Short-Duration Speaker Verification Performance with Enhanced Res2Net.* 2024.
5. Landini et al. *Bayesian HMM Clustering of x-vector Sequences (VBx).* 2022 — pyannote 4.0 community-1 所使用的聚类。
6. Kang et al. *DiariZen: leveraging Self-Supervised Learning for Speaker Diarization.* 2024–2025.
7. Vinnikov et al. *Target-Speaker Voice Activity Detection via Sequence-to-Sequence learning.* Interspeech 2024（EEND-TA 相关）。

---

## 3. 新流水线设计（task-a 重构方案）

### 3.1 目标架构

```
video.wav (16k mono)
   │
   ▼  [S1] 真正的 VAD
FSMN-VAD / silero-vad (独立调用，不依赖 whisper)
   │     输出: List[VoiceActivity(start,end)]
   ▼  [S2] Diarization backend（可插拔）
┌───────────────────────────────────────────────┐
│  DiarizationBackend (abstract)                │
│   ├─ ThreeDSpeakerBackend (CAM++) 【默认】     │
│   ├─ PyannoteBackend (3.1 / 4.0 community-1)   │
│   └─ LegacyEcapaBackend (当前实现，作为回滚)   │
└───────────────────────────────────────────────┘
   │     输出: List[DiarizedTurn(start,end,spk_id)]
   ▼  [S3] Embedding（独立于 diarization，用于跨视频匹配）
ERes2NetV2 zh-cn (首选) / ECAPA-TDNN (回退)
   │     对 diarized turn 抽 embedding（仅对 ≥0.8s 的段）
   ▼  [S4] 二级 Re-clustering + VBx 候选
- 同一视频内：对 turn-level embedding 再做一次 HDBSCAN / VBx
- 低频说话人保护：min_cluster_size=2（而非原来的 cap=8）
   ▼  [S5] ASR 段投射到 Diarization 时间线
对每个 ASR 段 s，按 IoU 最大原则分配给 turn；>10s 长段强制按 diarization 边界二次切分
   ▼  [S6] Speaker Bank 匹配（task-b）
与已有 registry 做 cosine 匹配；阈值切换为**基于 EER 校准**（ERes2NetV2 推荐 0.45–0.50）
```

### 3.2 新增/修改模块

| 模块 | 类型 | 说明 |
|------|------|------|
| `src/translip/transcription/diarization/__init__.py` | 新建 | 导出抽象类 `DiarizationBackend`、工厂函数 `create_backend(name, config)` |
| `src/translip/transcription/diarization/base.py` | 新建 | `DiarizedTurn` dataclass，`DiarizationBackend.diarize(audio_path) -> List[DiarizedTurn]` |
| `src/translip/transcription/diarization/threed_speaker.py` | 新建 | 使用 modelscope `iic/speech_campplus_speaker-diarization_common`，首选 backend |
| `src/translip/transcription/diarization/pyannote_backend.py` | 新建 | 支持 3.1 / 4.0 community-1，需要 HF token 时检测 `HUGGING_FACE_HUB_TOKEN` env |
| `src/translip/transcription/diarization/legacy_ecapa.py` | 新建 | 把当前 297 行搬进去，兼容回滚 |
| `src/translip/transcription/speaker.py` | 改造 | 仅保留「把 diarization 结果投射到 ASR 段」的逻辑，核心聚类移出 |
| `src/translip/speaker_embedding.py` | 扩展 | 增加 `load_eres2netv2_classifier`，统一 `embedding_for_clip` 接口 |
| `src/translip/config/defaults.py`（或 pyproject/YAML） | 扩展 | 新增 `diarization_backend: str = "threed_speaker"`，`speaker_embedding: str = "eres2netv2"` |
| `src/translip/speakers/registry.py` | 扩展 | 已有 embedding 持久化结构兼容新嵌入维度；引入版本号字段，旧库按 `speaker_embedding=ecapa` 标记 |
| `tests/transcription/test_diarization_threed_speaker.py` | 新建 | 使用短音频 mock 验证：正确切分、低频说话人保留、embedding 维度 |
| `tests/transcription/test_speaker_projection.py` | 新建 | diarization turn → ASR 段投射、IoU、长段切分、平滑逻辑 |

### 3.3 配置字段建议

```yaml
# translip.yaml (示意)
transcription:
  diarization:
    backend: threed_speaker        # threed_speaker | pyannote_3_1 | pyannote_community_1 | legacy_ecapa
    min_turn_duration: 0.4         # 小于此阈值的 turn 会被丢弃或并入相邻
    max_speakers: 12               # 替代旧的 cap=8；宁多勿少，后续由 VBx 合并
    overlap_aware: true            # pyannote backend 启用重叠感知
    hf_token_env: HUGGING_FACE_HUB_TOKEN
  embedding:
    model: eres2netv2              # eres2netv2 | ecapa_tdnn
    min_clip_duration: 0.8         # 低于则跳过该 turn 的 embedding
    device: auto                   # 自动走 mps / cpu
  speaker_bank:
    match_threshold: 0.46          # ERes2NetV2 的 EER 校准阈值
    min_matches: 2
```

---

## 4. 推荐路线

### 4.1 短期（Sprint 3.2，本周内，1–2 天）

1. 引入 **3D-Speaker `iic/speech_campplus_speaker-diarization_common`** 作为默认 diarization backend
2. 把现有 speaker.py 迁成 `legacy_ecapa` 回退实现
3. ASR→Diarization **投射**替代 ASR→聚类：ASR 段遇到 turn 边界强制分裂
4. 用 **ERes2NetV2** 取代 ECAPA 作为 speaker embedding；registry 加版本号，旧档案自动迁移或按需重嵌

### 4.2 中期（Sprint 3.3，1 周内）

5. 增加 **pyannote community-1** backend（exclusive diarization + VBx），作为英文/多语种场景备选
6. 对同一视频 turn-level embedding 增加 **二级 HDBSCAN**；低频说话人保护（min_cluster_size=2）
7. 引入 **speaker-change-detection**：长段 (>10s) 若 diarization 只给 1 个 turn，仍用 embedding 滑窗自检

### 4.3 长期（Sprint 4+）

8. 引入 **DiariZen + WavLM** 作为最高质量档（在 32 GB 设备上可选）
9. 评估 **Sortformer streaming** 用于实时监听/预览
10. 建立带 **人耳签审** 的评测闭环（按分钟抽样人工打标，自动化计算 DER/JER）

---

## 5. 指令级实施拆解（Sprint 3.2 ETA）

| Day | 任务 | 产出 |
|-----|------|------|
| D0 Morning | 新增 `diarization/` 抽象与 `legacy_ecapa` | 代码迁移；旧行为零回归（单测 green） |
| D0 Afternoon | `threed_speaker.py` + modelscope 依赖声明 | Dubai 视频 DER 指标首次出具 |
| D1 Morning | 新 `speaker.py` 只做投射 + IoU 分配 + 长段切分 | `test_speaker_projection.py` 通过 |
| D1 Afternoon | `ERes2NetV2` 嵌入 + registry v2 | 旧 voice bank 自动迁移脚本 `scripts/migrate_speaker_bank_v2.py` |
| D2 Morning | Dubai 视频 v3 重跑 + A/B 指标 | `docs/superpowers/reports/2026-04-27-dubai-v3-diarization-ab.zh-CN.md` |
| D2 Afternoon | 人耳签审 + 缺陷修复 | TODO 递归闭环 |

### 5.1 具体命令示意

```bash
# 1. 依赖安装（离线缓存优先）
uv add modelscope==1.18.* funasr==1.1.* torch==2.3.* torchaudio==2.3.*
uv add --optional pyannote pyannote.audio==3.3.*

# 2. 首次模型预下载（置于 .models/ 以便离线）
python -m translip.scripts.fetch_models \
  --diarization 3d-speaker \
  --embedding eres2netv2 \
  --vad fsmn

# 3. 回归
uv run pytest tests/transcription/ tests/speakers/ -q

# 4. Dubai 视频 v3 A/B
uv run python -m translip.cli run \
  --video "/path/to/我在迪拜等你.mp4" \
  --diarization-backend threed_speaker \
  --speaker-embedding eres2netv2 \
  --task-id dubai-v3
```

---

## 6. 验收指标

| 指标 | 现状 (v2 medium) | Sprint 3.2 目标 | 测量方法 |
|------|------------------|-----------------|----------|
| DER（Dubai 9 分钟样本） | ≈ 34% | **≤ 18%** | `pyannote.metrics` + 人工标注 RTTM |
| 识别到的说话人数 | 4 | **7 ± 1**（匹配真实 7 人） | diarization 输出集合大小 |
| 奶奶段是否恢复 | ❌ | ✅（至少 3 段分配到独立 spk） | 人耳签审 |
| 跨视频说话人一致率 | 未测量 | **≥ 85%**（同一人物在 3 个视频中正确匹配） | registry 匹配率 |
| 长段 (>10s) 拆分率 | 0% | **≥ 80%**（长段应按 turn 切为 ≥2 段） | pipeline 日志统计 |
| 端到端耗时回退 | — | **≤ +25%**（相比 v2） | `task-a.log` 时间戳 |

---

## 7. 风险、回滚与注意事项

1. **HuggingFace gated 仓库**：pyannote 3.1 / 4.0 community-1 需 HF token。处理：`PyannoteBackend` 检测不到 token 时打 warning 并回退到 `threed_speaker`，不阻塞主流程。
2. **modelscope 国内依赖**：默认域名为 `modelscope.cn`。处理：支持 `MODELSCOPE_CACHE` 环境变量，预下载到 `.models/` 后离线运行；提供 `scripts/fetch_models.py`。
3. **Apple Metal 适配**：3D-Speaker、ERes2NetV2 走 PyTorch，mps 覆盖度尚不完全。处理：`resolve_speaker_device` 增加回退到 cpu 的策略；单测固定 `device=cpu` 以避免 CI 漂移。
4. **Embedding 维度变化**：ECAPA (192-d) → ERes2NetV2 (256-d)。处理：registry 落盘新增 `embedding_model` 与 `dim` 字段；加载时按模型分桶匹配，不会误把旧向量与新向量比较。
5. **性能回退**：3D-Speaker pipeline 在 10 分钟音频 CPU 耗时约 30–45 秒（本机基准），pyannote 3.1 约 60–90 秒。处理：允许并行化（pipeline 阶段解耦）并给出 `--lean` 快速通道（只用 ECAPA legacy）。
6. **VBx 依赖**：pyannote 4.0 community-1 的 VBx 来自 BUT Speech@FIT 的 Kaldi-style 实现，pip 包名 `vbx-diarization`（或 pyannote 自带）。处理：作为 optional extra；不可用时自动降级到 3.1 Agglomerative。
7. **回滚方案**：`diarization_backend=legacy_ecapa`（配置一行切回），速度与当前完全一致；所有新代码放在 `diarization/` 子包内，主流程 import 可短路。
8. **数据安全**：ERes2NetV2 与 CAM++ 权重在 modelscope 需要注册（免费），在企业网络内需配置代理；建议把权重纳入项目 `.models/` 并在文档中说明。

---

## 8. 与 translip 既有组件的耦合矩阵

| 现有组件 | 是否改动 | 说明 |
|----------|----------|------|
| `src/translip/transcription/asr.py` | ❌ 不动 | ASR 输出不变，仅在下游被投射到 diarization |
| `src/translip/transcription/runner.py` | ✅ 小改 | 替换 `assign_speaker_labels` 调用；读取 `diarization_backend` 配置 |
| `src/translip/transcription/speaker.py` | ✅ 大改 | 只保留「投射 + IoU + 长段切分 + 平滑」；聚类外移 |
| `src/translip/speaker_embedding.py` | ✅ 扩展 | 新增 ERes2NetV2 载入；保留 ECAPA 接口 |
| `src/translip/speakers/*` (task-b) | ✅ 小改 | registry 增加版本号；match_threshold 基于 EER 校准 |
| `src/translip/rendering/*` | ❌ 不动 | — |
| `src/translip/server/app.py` | ❌ 不动 | — |
| `frontend/*` | ❌ 不动 | — |
| `tests/*` | ✅ 扩展 | 新增 diarization/投射/迁移测试 ≥ 12 个 |

---

## 9. 附录 A：为什么优先 3D-Speaker 而非 pyannote

1. **中文对比数据直接占优**：Meeting-CN_ZH 数据集 DER 18.91% vs pyannote 22.37%
2. **无 HF token 门槛**：modelscope 可直接 anonymous 下载，CI 友好
3. **模型体积最小**：CAM++ 7.2 MB + VAD 2 MB + 频谱聚类器 <5 MB，完全贴合 ≤500 MB 约束
4. **生态自洽**：FSMN-VAD / CAM++ / ERes2NetV2 / 聚类四件套来自同一机构，参数空间一致
5. **与现有 SpeechBrain ECAPA 形成回滚对照**：架构范式相同（VAD+Embedding+Cluster），迁移成本低

## 10. 附录 B：为何仍把 pyannote community-1 留作二线

- **重叠说话人建模**：pyannote segmentation-3.0 的 Powerset Cross Entropy 对重叠段 DER 下降约 15%
- **VBx 聚类稳定性**：在 7+ 说话人场景下比 Agglomerative 更鲁棒
- **多语种场景**：英文/混合语种视频 pyannote 综合表现更好
- 因此 **英文素材 + 长会议** 场景可一键切换 backend，不改代码

---

## 11. 下一步行动清单（交付前 Gate）

- [ ] Sprint 3.2 Day 0 Morning：落地 `diarization/` 抽象 + `legacy_ecapa` 迁移
- [ ] Day 0 Afternoon：3D-Speaker backend + Dubai DER 首测
- [ ] Day 1 Morning：`speaker.py` 投射化改造
- [ ] Day 1 Afternoon：ERes2NetV2 + registry v2 + 迁移脚本
- [ ] Day 2：Dubai v3 A/B 报告 + 人耳签审
- [ ] 合并前：`uv run pytest` 全绿、`ruff`/`mypy` 无回归、文档更新 `AGENTS.md` 与 README
- [ ] 合并后：通知 Sprint 3.1（rubberband）与 Sprint 3.2（diarization）并行展开

---

文档结束。
