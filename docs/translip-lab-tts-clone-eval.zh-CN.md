# translip-lab：配音/音色克隆评测（tts-clone）设计文档

> 文档版本：v1.0 · 日期：2026-06-23
> 范围：在 `translip_lab` 评测台中新增 **`tts-clone`** 场景 + **说话人相似度（SIM）/可懂度（CER）** 指标 + **`synthetic-clone`** 合成数据集，把「配音/TTS」环节从「无客观 ground-truth 打分」补成「可量化、可回归、可对比」。
> 关联调研：`中文影视剧/邻近语料数据集调研`（seed-tts-eval 的 WER+SIM 方法学）；关联现状：Lab 模块 PRD（`docs/superpowers/specs/2026-06-22-lab-module-product-requirements.zh-CN.md`）。

---

## 1. 背景与要解决的问题

`translip_lab` 当前对 5 个环节有真值打分（分离 SI-SDR、ASR CER、说话人 DER、OCR 文本/框 F1、字幕擦除 PSNR/SSIM），但**配音/TTS 这条核心能力没有独立的客观指标**：

- `e2e-dub` 场景（`scenarios/e2e_dub.py`）的主指标是 translip 自带的 **intrinsic「honest score」**（`benchmark-dub` 的 0–100 分），**不依赖任何外部 ground truth**。
- 该 intrinsic 分有已知盲点：它是一个偏薄的 JOIN，会**漏报 0.25–0.45 的音色相似度带、把节奏问题混进总分**（见既往 dub-eval 复盘）。把评测台的配音头牌指标压在它上面，等于把它的盲点一起带进 leaderboard。
- PRD（§4.2.1）把 `e2e_dub` 主指标列为 **`mcd`（越小越好）**，但代码里实际是 `primary_metric_key = "score"`（intrinsic，越大越好）——**说明作者本想要一个 GT 锚定的客观指标，但最终没落地**。

**本设计提供那个「本想要却没落地」的客观指标**：参照 2024+ 零样本音色克隆的事实标准 **seed-tts-eval**，用两个互补的、有 ground truth 的指标评配音：

| 指标 | 含义 | 真值 | 复用 |
|---|---|---|---|
| **SIM**（说话人相似度） | 合成音是否保住了**目标音色** | 参考音色 wav | translip 自带 **ECAPA** 嵌入（`speaker_embedding.py`） |
| **CER**（可懂度） | 合成音**说对了没有**（重转写后比对目标文本） | 目标文本 | translip ASR（`transcribe`）+ lab 的 `metrics/text.py` |

> 设计取向：**SIM 设为 `tts-clone` 的主指标**（越大越好）。理由——CER 已被 `asr` 场景覆盖，而 SIM（音色保真）恰是 intrinsic 分**最会漏报**、且当前**全台没有任何指标覆盖**的维度。CER 作为次要指标同屏报出。

---

## 2. 设计总览

完全遵循 Lab 既有架构「加能力＝加一个文件」，不改动核心引擎、不破坏单向依赖：

```
新增：
  metrics/speaker.py            cosine_similarity + speaker_similarity（懒加载 ECAPA，可注入 embedder）
  datasets/synthetic_clone.py   synthetic-clone：造「参考音色 wav + 目标文本」配对（离线可测）
  scenarios/tts_clone.py        tts-clone：invoke（TTS→转写）+ score（SIM + CER）
  tts_synth.py                  lab 侧 TTS worker（python -m），镜像 translip 语音克隆核心
  suites/tts-clone-synthetic.toml
  tests/lab/test_metrics_speaker.py
  tests/lab/test_datasets_synthetic_clone.py
  tests/lab/test_scenario_tts_clone.py

改动（最小）：
  core/sample.py            GroundTruth 增 clone_text / clone_ref_wav 两字段
  metrics/__init__.py       导出 cosine_similarity / speaker_similarity
  datasets/__init__.py      import synthetic_clone（注册）
  scenarios/__init__.py     import tts_clone（注册）
  datasets/folder.py        识别 <stem>.clone.txt / <stem>.ref.wav 边车（自带数据走真实路径）
  cli.py                    gen-synthetic 增 --kind clone
  README.md                 场景表补 tts-clone 行
```

---

## 3. 数据契约

### 3.1 GroundTruth 新增字段（`core/sample.py`）

```python
clone_text: str | None = None        # 要合成的目标文本 → CER 真值
clone_ref_wav: Path | None = None    # 目标音色参考 wav → SIM 真值（缺省回退到 sample.media_path）
```

两者皆 optional，与既有字段一致：场景按需校验（`tts-clone` 的 `required_gt = ["clone_text"]`）。

### 3.2 `synthetic-clone` 合成数据布局（离线可造、可测）

每个 case 在 `<cache>/synthetic-clone/clip_NNN/` 生成：

```
prompt.wav     一段「带说话人特征（共振峰由 speaker_seed 决定）」的合成参考音色
               —— 既是 sample.media_path（scenario 的输入参考音），也是 SIM 真值
meta:          clone_text = 取自固定中文句库（按 index 轮换，确定性）
```

- 同一 `speaker_seed` → 同一音色（共振峰一致）；不同 seed → 不同音色。供测试构造「高 SIM / 低 SIM」对照。
- 纯 numpy + soundfile 合成，**不需要任何模型、不需要下载**，与既有 `synthetic-mix` / `synthetic-subtitle` 同一思路（验证管路与指标；真实数字用 `folder` 喂真实素材）。

### 3.3 `folder` 真实数据边车（自带影视素材走真实路径）

为 `<stem>.<media>` 增加两个可选边车：

```
<stem>.clone.txt   目标文本（要让 TTS 用该片段音色去说的话）
<stem>.ref.wav     目标音色参考（可选；缺省用媒体自身做参考）
```

这样把「自建中文影视音色样本」直接变成可量化 case，零摩擦（呼应调研里「自建影视评测集」的落地建议）。

---

## 4. 场景执行流（`scenarios/tts_clone.py`）

```
invoke(sample, work_dir, invoker, config):
    ref  = sample.ground_truth.clone_ref_wav or sample.media_path
    text = sample.ground_truth.clone_text
    # 1) TTS 语音克隆（隔离子进程，复用 translip 核心）
    r_tts = invoker.module("translip_lab.tts_synth",
              ["--text", text, "--reference", ref, "--output", work_dir/"synth.wav",
               "--backend", config.tts_backend or "qwen3tts", "--language", lang])
    if not r_tts.ok: return r_tts          # 失败 → 场景标 failed（不崩整轮）
    synth = r_tts.outputs["synth_wav"]
    # 2) 重转写合成音（可懂度用），复用 translip ASR
    r_asr = invoker.translip("transcribe", ["--input", synth, "--language", lang, ...])
    r_asr.outputs["synth_wav"] = synth     # 把合成音路径并入返回的 outputs
    return r_asr

score(sample, work_dir, stage, config):
    synth = stage.outputs["synth_wav"]; segs = stage.outputs["segments"]
    hyp_text = "".join(seg.text for seg in load(segs))
    cer = metrics.text.cer(sample.ground_truth.clone_text, hyp_text)
    sim = metrics.speaker.speaker_similarity(ref, synth)["sim"]   # ECAPA 余弦；不可用→None
    return {"sim": sim, "cer": cer, "wer": wer, "intelligibility": 1-min(cer,1), ...}
```

- **主指标**：`sim`（`higher_is_better = True`）。`cer` 次要同屏。
- **优雅降级**：若 ECAPA 不可用（理论上不会，它是 diarization 默认后端的同款依赖），`sim=None` 并记一条 note，场景仍成功返回 `cer`——不阻断。
- **corpus 聚合**（`corpus_metrics`）：`cer_micro`（池化）+ `sim_mean`。

---

## 5. lab 侧 TTS worker（`tts_synth.py`，`python -m translip_lab.tts_synth`）

为什么是 lab 侧 worker 而非直接复用 `server/atomic_tools` 的 `generate_speech`：后者所在的 `adapters/__init__.py` 会 **eager-import 全部重适配器**（separation/vision…，拖入 demucs/torch/vision），违背 lab「base 依赖 + 轻量」原则。

worker **只导入 `translip.dubbing` core**，镜像原子工具的 `_generate_voice_clone`（qwen3tts 路径）：

```python
from translip.dubbing.backend import SynthSegmentInput, resolve_tts_device
from translip.dubbing.qwen_tts_backend import (
    _load_qwen_model, _language_name, _max_new_tokens_for, _normalize_waveform)
# device → 加载 Qwen3-TTS-Base → generate_voice_clone(text, ref_audio=...) → 归一化 → 写 wav
# stdout 机器可读：synth_wav=<path>  sample_rate=<n>  tts_backend=qwen3tts
```

- **单向依赖**：lab → translip.dubbing，保持「translip 不反向依赖 lab」。
- **子进程隔离**：多 GB 的 TTS 模型用完即随子进程退出释放（与 orchestrator/lab 既有姿势一致）。
- **后端范围**：v1 落 **qwen3tts**（默认、最干净）。`moss-tts-nano-onnx` / `voxcpm2` 需走 `ReferencePackage` 参考音预处理，列为后续（需真实模型 smoke test，见 §9）。

---

## 6. 复用与解耦（守住 Lab 的「一条规则」）

| 复用点 | 来源 | 性质 |
|---|---|---|
| 说话人嵌入（SIM） | `translip.speaker_embedding`（ECAPA/speechbrain） | 纯函数导入，与既有「借用 `translip.transcription.benchmark`」同姿势 |
| 语音克隆 TTS | `translip.dubbing.qwen_tts_backend`（core） | 子进程 `python -m`，模型用完释放 |
| 可懂度转写 | `translip transcribe`（CLI） | 子进程，与其它场景一致 |
| CER/cosine | lab `metrics/text.py`、`metrics/speaker.py` | 纯 numpy/stdlib，可单测 |

依旧满足：**删掉 `src/translip_lab/` + 一个 sidebar link，主系统无感**。

---

## 7. 离线测试方案（用合成数据，不下载、不跑真模型）

三层，全部离线、确定性：

1. **指标层** `test_metrics_speaker.py`
   - `cosine_similarity`：相同向量→1，正交→0，反向→−1。
   - `speaker_similarity` 用**注入的纯 numpy embedder**：相同音→sim≈1，不同音→更低；embedder 抛错→`sim=None` 且不崩（优雅降级）。
2. **数据层** `test_datasets_synthetic_clone.py`
   - 生成器产出 `prompt.wav` + manifest 带 `clone_text` + `clone_ref_wav`；确定性（同 seed 同输出）；同 speaker_seed 的两段音 MFCC 距离 < 不同 seed。
3. **场景层** `test_scenario_tts_clone.py`（核心，端到端打分路径全覆盖）
   - 用**假 Invoker**（`StageResult` 注入 `synth_wav` + 转写 `segments`）+ **monkeypatch 掉默认 ECAPA embedder 为纯 numpy**：
     - 完美档：合成音=参考音、转写=目标文本 → `cer≈0`、`sim` 高。
     - 退化档：转写乱码 → `cer` 高；合成音=不同说话人 → `sim` 低。
   - 断言 `tts-clone` 已注册、`required_gt` 校验、缺 `clone_text` 时 `skipped`。

> 真实 TTS 的 `invoke` 路径（需 Qwen3-TTS 模型）**不在离线测试范围**，作为 §9 的 smoke-test 项；但 `score`（真正补的能力）100% 离线可测。

---

## 8. 与既有 `e2e-dub` 的关系

- **不改 `e2e_dub.py`**（保持 intrinsic 回归分作为端到端冒烟）。
- `tts-clone` 是**环节级、GT 锚定**的客观指标，补 intrinsic 分漏报的音色维度——即 PRD 里 `mcd` 想做却没做的那个客观指标的更好实现（SIM+CER ＞ 单一 intrinsic 分）。
- 两者并存：`e2e-dub` 看「整条链能不能跑、整体回归」，`tts-clone` 看「TTS 这一环音色保真 + 可懂度」。

---

## 9. 落地清单与后续

**本次落地（离线可测）**：metrics/speaker.py · datasets/synthetic_clone.py · scenarios/tts_clone.py · tts_synth.py · suite · GroundTruth 字段 · folder 边车 · CLI · 三个测试文件。

**后续（需数据/模型，硬盘就绪后）**：
1. **moss/voxcpm2** 后端的 worker 路径 + 真实模型 smoke test。
2. **MagicData-RAMC** 适配器 — **✅ 已落地**：`datasets/magicdata_ramc.py`（专用 `[start,end] speaker 性别,方言 text` 解析器，复用 RTTM/SRT 发射器）+ `suites/asr-diar-ramc.toml` + `tests/lab/test_datasets_ramc.py`（6 个 fixture 测试验证解析逻辑）。CER+DER 扩到自发对话域。⚠️ 解析格式据官方发布示例构建，**真数据首跑前抽一条 `.txt` 逐字节对照**（解析器已隔离便于微调）。
3. **ChaLearn Decaptioning** 适配器（subtitle-erase 跨集校验；调研 P1）。
4. **缓存键纳入 scorer 版本**（`cache.py` 现仅按 config+input 哈希，改打分逻辑不失效——既有 footgun；加 `Scenario.version` 进 key）。
5. 自建中文影视音色小集（走 §3.3 的 `folder` 边车）。
