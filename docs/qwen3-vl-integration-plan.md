# Qwen3-VL-4B 视频内容感知模块 — 技术方案

> 状态：草案 v1（2026-06-10）
> 目标：为 translip 引入本地视频理解能力（Qwen3-VL-4B），用于场景上下文、说话人视觉归属、擦除质检、OCR 语义过滤。
> 设计哲学：与 ocr/erase 先例完全一致 —— in-tree 模块 + 可选 extra + lazy import + 隔离子进程 + manifest 契约。

---

## 1. 背景与目标

translip 管线目前对视频内容的"感知"仅限于音频（ASR/声纹）和文字（PaddleOCR）。引入一个轻量视觉语言模型后，可在四个环节产生增益：

| 场景 | 消费方 | 增益 |
| --- | --- | --- |
| **V1 场景上下文** | task-c 翻译 | 每个 ContextUnit 附带一句画面描述，减少称谓性别/指代/语气误译 |
| **V2 说话人视觉归属** | task-b 角色库 | 判断画面人数/谁在说话，辅助声纹聚类；角色库获得"有脸的角色" |
| **V3 擦除质检** | subtitle-erase 之后 | 抽样检查 inpaint 残留，自动产出问题帧报告 |
| **V4 OCR 语义过滤** | ocr-detect 之后 | 区分硬字幕 vs 场景文字（路牌/店招/logo），减少误擦和误翻 |

**实施顺序：V1 → V3 → V4 → V2**（V1 收益/成本比最高且无依赖；V2 涉及声纹聚类联动，最复杂，放最后）。

### 非目标（本期不做）

- 全片逐帧精看 / 动作级理解（16 GB 内存 + 4B 模型不现实）
- TTS 情绪提示（moss-tts-nano 韵律控制有限，等后端能力跟上）
- 云端 VLM 后端（预留接口，见 §10，本期只做本地）

---

## 2. 能力全景：能感知什么、能做什么、收益是什么

> 本节回答"引入这个模型到底能获得什么"。§1 的 V1–V4 是首批落地的集成点；这里是完整的能力地图，作为后续迭代的需求池。

### 2.1 能从画面中提取的信息

**场景与环境**
- 地点类型（车内/办公室/街头/餐厅/室外夜景）、时间感（白天/夜晚/黄昏）、天气
- 场景切换判断（"这两帧是同一个场景吗"）→ 可做粗粒度镜头/场景分段

**人物**
- 画面人数、性别、大致年龄段、衣着特征（"穿红色外套的女性"）
- 动作（坐着交谈/奔跑/打电话/吃饭）
- 表情与情绪（愤怒/微笑/哭泣/惊讶）
- 谁的嘴在动（说话人判断）——多帧对比下可用，单帧不可靠
- 人物关系线索（面对面争吵/拥抱/一方在听）

**画面文字**（Qwen-VL 系强项，32 语种 OCR）
- 硬字幕、片头片尾字幕、标题卡
- 场景内文字：路牌、店招、屏幕内容、报纸、手机界面
- 关键差异：PaddleOCR 只回答"哪里有什么字"，VLM 能**理解语义后分类**——"这是字幕还是路牌""这块文字和剧情有什么关系"

**物体与构图**
- 关键物体识别（武器/食物/车辆/乐器）；Qwen3-VL 支持 grounding，可输出坐标框
- 镜头语言粗判断：特写/远景、画面主体

**时序信息**（多帧输入下）
- 一段时间内发生了什么（"先递东西、然后争执、最后离开"）
- 事件大致时间点（配合抽帧附带的时间戳）
- 前后画面变化（"字幕消失了没有""人物换装了"）

**内容属性**
- 视频类型（动画/真人剧/纪录片/演讲/游戏录屏）
- 内容分级线索（暴力/亲密场景的存在性）
- 画质问题（模糊/涂抹痕迹/水印/黑边）

### 2.2 对现有管线的直接收益（= V1–V4）

| 提取的信息 | 用在哪 | 收益 |
| --- | --- | --- |
| 场景描述 + 人物关系 + 情绪 | task-c 翻译 prompt | 称谓性别、指代、语气误译减少（你→tu/vous、兄/弟这类） |
| 画面人数 + 谁在说话 | task-b 声纹聚类 | 同性别相近音色的说话人区分；角色库获得头像和画面出场记录 |
| 残留文字/涂抹检测 | erase 后 QC | 擦除质量自动报告，替代人工逐段检查 |
| 字幕 vs 场景文字分类 | ocr-detect 后 | 不误擦路牌店招、不把场景文字当台词送翻译 |

### 2.3 解锁的新能力（现有管线完全没有的）

1. **视频类型自动识别**：上传后自动判断动画/真人 → 驱动配置选择（动画适合 lama 擦除后端、TTS 风格选择）
2. **章节/场景自动分段**：粗粒度剧情分段 + 每段一句摘要 → dubbing-editor 导航（"跳到餐厅争吵那段"）
3. **画面感知的字幕排版**：判断画面下方是否有人脸/重要文字 → 烧录字幕位置自动上移
4. **任意问答原子工具**（`freeform` 模式）：对视频提任意问题（"出现过几次手机屏幕特写"），通用素材检视
5. **内容安全/合规预检**：交付前自动标记需注意的画面内容
6. **缩略图/封面智能选择**：从抽帧中挑"有代表性、人脸清晰、无字幕遮挡"的一帧

### 2.4 4B 档位的能力边界（避免期望错位）

| 做不好/做不了 | 说明 | 替代方案 |
| --- | --- | --- |
| 细粒度动作理解 | 分不清"递东西"和"抢东西"；体育动作、手语不行 | 不做 |
| 跨长时段剧情推理 | "第 80 分钟这人为什么哭"需要全片记忆，4B + 抽帧做不到 | 云端长上下文（Gemini / Twelve Labs Pegasus，见 §10） |
| 精确计数 / 密集小目标 | 人群数人头、远处小字 OCR 不可靠 | 输出带 confidence，下游只做参考 |
| 人脸身份识别 | 能判断"和上一帧是同一人"（短程），不能跨全片稳定追踪"这是角色 A" | V2 需配合人脸 embedding（如 insightface）做聚类，VLM 只负责"谁在说话" |
| 幻觉 | 对模糊画面会编造细节 | 所有输出带 confidence；QC 类任务设计为"报告"而非"自动动作" |

**一句话定位**：4B 模型给管线装上一双"常识级的眼睛"——可靠回答"画面里大致是什么、谁在场、什么气氛、有什么字"，恰好覆盖翻译上下文、说话人辅助、擦除质检这些管线最缺视觉信息的环节；但它不是"看懂整部电影"的脑子——需要剧情级理解的任务要么切小喂（按段问答），要么留给云端大模型。

---

## 3. 模型与运行时选型

### 3.1 模型：Qwen3-VL-4B-Instruct

| 候选 | 结论 |
| --- | --- |
| **Qwen3-VL-4B-Instruct**（选定） | Apache 2.0；4-bit 量化 ~3.3 GB，峰值内存 6–8 GB，16 GB M2 可与轻管线阶段共存；原生视频/多图输入 + 文本-时间戳对齐；32 语种 OCR 能力可兼职 V4 |
| Qwen3-VL-8B | 12–16 GB 峰值，在 16 GB 机器上必须独占内存，留作 `model_size` 配置项的升级档 |
| MiniCPM-V / SmolVLM2 | 更小但中文场景描述质量明显弱于 Qwen 系，且与云端 qwen-vl prompt 不互通 |
| Thinking 变体 | 响应慢 2–4 倍，感知类任务不需要长推理链，不用 |

### 3.2 运行时：双后端，MLX 优先

```
vision_backend = "auto" | "mlx" | "ollama"
```

| 后端 | 依赖 | 优点 | 缺点 |
| --- | --- | --- | --- |
| **mlx**（macOS arm64 默认） | `mlx-vlm`（extra） | Metal 原生最快；权重经 HF hub 自动下载，可控缓存目录；进程内运行，随子进程退出释放内存 → 完美契合 translip 子进程隔离模型 | 仅 Apple Silicon |
| **ollama**（fallback） | 无 Python 依赖，HTTP 调 `localhost:11434` | 跨平台（Linux/NVIDIA 也能用）；用户可能已装 | 常驻 server 占内存，与"子进程退出即释放"哲学冲突；需用户自行 `ollama pull qwen3-vl:4b` |

`auto` 解析顺序：macOS arm64 且 `mlx_vlm` 可导入 → mlx；否则探测 `OLLAMA_HOST`（默认 `http://127.0.0.1:11434`）可达且有 qwen3-vl 模型 → ollama；都没有 → 清晰的依赖错误（仿照 task-d 对 moss-tts-nano 的处理）。

权重：

- mlx 路径用 HF 模型 `mlx-community/Qwen3-VL-4B-Instruct-4bit`（~3.3 GB）。下载交给 `huggingface_hub`，但通过设置 `HF_HOME=<CACHE_ROOT>/vision_models/hf` 收敛到 translip 缓存目录（与 `SUBTITLE_ERASE_MODELS_DIR` 同级语义）。
- `VISION_LOCAL_MODELS_ONLY=1` 时传 `local_files_only=True`，权重缺失直接报错（对齐 `SUBTITLE_ERASE_LOCAL_MODELS_ONLY`）。
- 不自己实现下载器（HF hub 已带断点续传 + etag 校验，无需复刻 erase 的 `ensure_weight`）。

### 3.3 喂入策略：抽帧，不喂原生视频流

4B 模型 + 16 GB 内存下，多图输入比原生视频 token 更稳。统一约定：

- 每个分析单元（segment / ContextUnit / 事件区间）取 **k 帧**（默认 4，可配 1–8）：单元时长 < 2s 取中点 1 帧；否则在 `[start, end]` 内均匀取 k 帧。
- 帧用 ffmpeg 抽取（`imageio-ffmpeg` 已是 base 依赖），长边缩到 **768px**（再大对 4B 无增益、徒增显存）。
- 整片任务（如 V3 抽样质检）按固定间隔抽帧，单批 ≤ 8 帧。

---

## 4. 模块布局：`src/translip/vision/`

仿照 `erase/` 的结构：

```
src/translip/vision/
  __init__.py            # 导出 VisionService、AnalyzeRequest/Result
  config.py              # pydantic-settings，VISION_* 环境变量
  extract.py             # python -m translip.vision.extract 子进程入口
  frames.py              # ffmpeg 抽帧（无重依赖，可单测）
  prompts.py             # 四类任务的 prompt 模板（zh/en），结构化 JSON 输出约定
  schema.py              # 输出 JSON 的 dataclass + 解析/校验（模型输出容错）
  backends/
    __init__.py          # resolve_backend("auto"|"mlx"|"ollama")，lazy import
    base.py              # VisionBackend 协议：load() / chat(images, prompt) -> str / close()
    mlx_backend.py       # mlx-vlm 实现（lazy import mlx_vlm，ImportError 带安装指引）
    ollama_backend.py    # HTTP 实现（urllib.request，无新依赖）
  services/
    vision_service.py    # 编排：读分段 JSON → 抽帧 → 逐单元推理 → 写产物 + manifest
```

### 4.1 config.py（对齐 erase/config.py 写法）

```python
from pydantic_settings import BaseSettings, SettingsConfigDict
from translip.config import CACHE_ROOT

class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=True, extra="ignore")

    VISION_BACKEND: str = "auto"            # auto | mlx | ollama
    VISION_MODEL: str = "mlx-community/Qwen3-VL-4B-Instruct-4bit"
    VISION_OLLAMA_MODEL: str = "qwen3-vl:4b"
    VISION_OLLAMA_HOST: str = "http://127.0.0.1:11434"
    VISION_MODELS_DIR: str = str(CACHE_ROOT / "vision_models")
    VISION_LOCAL_MODELS_ONLY: bool = False
    VISION_FRAMES_PER_UNIT: int = 4         # 每单元抽帧数 1-8
    VISION_FRAME_MAX_EDGE: int = 768        # 帧长边像素
    VISION_MAX_NEW_TOKENS: int = 256
    VISION_TEMPERATURE: float = 0.2         # 感知任务要低温
    VISION_TIMEOUT_SEC: int = 120           # 单次推理超时

settings = Settings()
```

### 4.2 子进程入口 extract.py

```
python -m translip.vision.extract \
  --input <video> \
  --output-dir <dir> \
  --task scene-context|erase-qc|ocr-classify|speaker-visual \
  [--segments <segments.zh.json>]      # scene-context / speaker-visual 必填
  [--detection <detection.json>]       # ocr-classify 必填
  [--sample-interval <sec>]            # erase-qc 用，默认 10
  [--backend auto|mlx|ollama]
  [--frames-per-unit N] [--lang zh|en]
```

要点（全部照抄 erase 先例）：

- 重依赖 **函数体内 lazy import**，`--help` 保持轻量；mlx_vlm 缺失时 raise 带 `uv sync --extra vision` 指引的 ImportError。
- 进度行协议：`__VISION_PROGRESS__\t<pct>\t<message>`（对齐 `__ERASE_PROGRESS__`），编排器 bridge 解析后喂给 monitor。
- 产物 + `<task>-manifest.json` 写入 `--output-dir`，stdout 末尾打印 manifest JSON。
- 模型 **加载一次、循环推理、进程退出即释放**——这就是 translip 子进程隔离的设计红利，无需在常驻进程里管理模型生命周期。

### 4.3 产物契约（schema.py）

所有任务输出统一信封 + 任务特定 payload。模型被 prompt 约束输出 JSON，解析失败时该单元降级为 `{"error": "...", "raw": "<截断原文>"}` 而非整体失败：

**V1 scene-context → `visual_context.json`**

```json
{
  "task": "scene-context",
  "model": {"backend": "mlx", "model": "mlx-community/Qwen3-VL-4B-Instruct-4bit"},
  "units": [
    {
      "unit_id": "unit-0001",
      "start": 0.5, "end": 11.8,
      "frames_sampled": [1.2, 4.0, 7.5, 10.9],
      "scene": "车内，男女二人对话，男方驾驶，气氛紧张",
      "people_visible": 2,
      "setting": "car_interior",
      "mood": "tense"
    }
  ]
}
```

**V3 erase-qc → `erase_qc_report.json`**：`{"timestamp": 123.0, "residual_text": true, "artifact": "blur_patch", "confidence": 0.8, "note": "..."}` 列表 + 汇总通过率。

**V4 ocr-classify → `ocr_events.classified.json`**：在原 `ocr_events.json` 每个事件上附加 `{"kind": "subtitle" | "scene_text" | "watermark" | "title_card", "confidence": 0.9}`。

**V2 speaker-visual → `speaker_visual.json`**：每 segment 附 `{"people_visible": N, "speaking_face": true|false|null, "face_crop": "faces/seg_0001.jpg"}`。

---

## 5. 接入点一：原子工具（第一阶段交付）

新文件 `src/translip/server/atomic_tools/adapters/video_analyze.py`：

```python
class VideoAnalyzeAdapter(ToolAdapter):
    def validate_params(self, params: dict) -> dict:
        return VideoAnalyzeToolRequest(**params).model_dump()   # pydantic schema

    def run(self, params, input_dir, output_dir, on_progress):
        input_file = self.first_input(input_dir, "file")
        on_progress(5.0, "preparing")
        # 经 subprocess 调 python -m translip.vision.extract（与管线同一入口），
        # 解析 __VISION_PROGRESS__ 行转发给 on_progress
        ...
        return {"result_file": "visual_context.json", "unit_count": n, ...}

register_tool(
    ToolSpec(
        tool_id="video-analyze",
        name_zh="视频内容分析",
        name_en="Video Content Analysis",
        description_zh="基于 Qwen3-VL 本地模型分析视频画面：场景描述、画面文字分类、擦除质检",
        description_en="Analyze video frames with local Qwen3-VL: scene description, on-screen text triage, erase QC",
        category="video",
        icon="Visibility",
        accept_formats=[".mp4", ".mkv", ".avi", ".mov"],
        max_file_size_mb=2048,
    ),
    VideoAnalyzeAdapter,
)
```

参数：`task`（默认 `scene-context`）、`question`（自由问答模式，task=`freeform` 时必填）、`sample_interval`、`frames_per_unit`、`lang`。

> 为什么先做原子工具：adapter 壳子极薄（subtitle-detect 同款），不动管线和缓存；能在管理 UI 里独立验证模型输出质量，验证不过关随时止损。

**配套（按项目惯例必做）**：新端点/字段加中文 docstring + Field description（接口文档页从 OpenAPI 渲染）；前端 `i18n/messages.ts` 加 zh-CN/en-US 词条；atomic tool 列表页会自动出现新工具。

---

## 6. 接入点二：管线节点 `visual-context`（第二阶段）

### 6.1 节点注册（nodes.py）

```python
"visual-context": WorkflowNodeDef("visual-context", "visual-perception", ("task-a",), 45),
```

- 依赖 task-a（需要 segments 的时间轴和文本），排在 task-b/c 之前（`sequence_hint=45`，介于 task-a 与 task-c 之间，具体值按现有注册表插空）。
- 模板：现有三个模板**不默认包含**该节点。新增 `asr-dub+visual` 模板（或作为现有模板的 `optional_nodes`，按 templates.py 现状选侵入更小的方式），保证默认行为零变化。

### 6.2 命令构建（commands.py + vision_bridge.py）

新增 `orchestration/vision_bridge.py`（照抄 erase_bridge.py 三件套）：

```python
def build_visual_context_command(request, *, segments_path) -> list[str]:
    return [sys.executable, "-m", "translip.vision.extract",
            "--input", str(request.input_path),
            "--task", "scene-context",
            "--segments", str(segments_path),
            "--output-dir", str(request.output_root / "visual-context"),
            "--backend", request.vision_backend,
            "--frames-per-unit", str(request.vision_frames_per_unit)]

def parse_vision_progress_line(line) -> tuple[float, str] | None: ...
def run_visual_context(request, *, log_path, monitor, should_cancel) -> dict: ...
```

### 6.3 PipelineRequest 新字段（types.py）

```python
# === Vision（视觉感知）字段 ===
vision_backend: str = "auto"          # auto | mlx | ollama
vision_frames_per_unit: int = 4
vision_lang: str = "zh"
```

### 6.4 缓存 spec（runner.py）

```python
StageCacheSpec(
    stage_name="visual-context",
    manifest_path=visual_context_manifest_path(request),
    artifact_paths=[visual_context_path(request)],
    cache_key=compute_cache_key({
        "input_path": str(request.input_path),
        "vision_backend": request.vision_backend,   # 换后端/模型强制重算
        "vision_model": resolved_model_id,
        "vision_frames_per_unit": request.vision_frames_per_unit,
        "vision_lang": request.vision_lang,
        "segments_fingerprint": file_fingerprint(segments_path),  # 上游指纹
    }),
)
```

### 6.5 task-c 消费（最小侵入）

`TranslationRequest` 加可选字段 `visual_context_path: Path | None = None`。翻译器构建 ContextUnit 后，按 `unit_id`（或时间区间重叠）查 `visual_context.json`，命中则在 prompt 前注入一行：

```
[画面] 车内，男女二人对话，男方驾驶，气氛紧张
```

- 仅 `deepseek` 后端注入（m2m100 是 seq2seq 模型，不吃自然语言上下文）。
- 文件缺失/单元未命中 → 静默跳过，**翻译阶段不因视觉模块失败而失败**。
- task-c 的 cache key 需把 `visual_context` 文件指纹纳入（有上下文与无上下文的译文不同）。

### 6.6 监控权重（stages.py）

`visual-context` 进度权重给较小值（如 0.05 量级，参照 ocr-detect 的设定），单元数已知所以进度 = 已处理单元 / 总单元，线性可信。

---

## 7. 接入点三/四：erase-qc 与 ocr-classify（第三阶段）

- **erase-qc**：节点 `erase-qc`，依赖 `("subtitle-erase",)`，对 `clean_video.mp4` 在原 OCR 事件时间区间内抽帧提问"画面中是否仍有可读文字或涂抹痕迹"。产物 `erase_qc_report.json` 进入 delivery 的 task_read_model，前端在擦除结果页展示问题帧列表（截图 + 时间戳，点击跳转播放器）。不阻断管线，纯报告。
- **ocr-classify**：不新增节点，作为 `ocr-detect` 的可选后处理步骤（`ocr_classify_text: bool = False` 字段）。对每个 OCR 事件取 1 帧 + 事件框裁剪图，问"这段文字是硬字幕还是场景文字"。下游：erase 的 mask planning 跳过 `scene_text`；task-c 不翻译 `watermark/title_card`。**默认关闭**，因为它改变 erase/翻译行为，需要在真实片源上验证误分类率后再考虑默认开启。

---

## 8. CLI 与依赖

### 8.1 CLI 子命令（cli.py）

```
uv run translip analyze-video \
  --input video.mp4 --task scene-context \
  --segments output/task-a/xxx/segments.zh.json \
  --output-dir output-vision [--backend auto] [--frames-per-unit 4]
```

样板照 `translate-script`：subparser 注册 → `args.command == "analyze-video"` 分支 → 函数体内 import `vision.services` → 打印 manifest JSON。

### 8.2 pyproject.toml

```toml
vision = [
  "mlx-vlm>=0.1,<1; sys_platform == 'darwin' and platform_machine == 'arm64'",
  "huggingface_hub>=0.26,<1",
  "pillow>=10,<12",
]
```

- ollama 后端零依赖（标准库 urllib + 复用 imageio-ffmpeg 抽帧），所以 **Linux 用户不装 extra 也能用 ollama 后端**。
- 提醒（CLAUDE.md 已记录的坑）：`uv sync --extra X` 会精确同步，文档里写明 `uv sync --extra dev --extra vision` 组合用法。

---

## 9. 内存与性能预算（16 GB M2 基准）

| 项 | 预算 |
| --- | --- |
| Qwen3-VL-4B 4bit 峰值内存 | ~6–8 GB（含 KV cache + 视觉编码器） |
| 单单元推理（4 帧 + 256 token 输出） | 估 5–15 s（M2，待 Phase 0 实测校准） |
| 90 min 影片，~300 ContextUnit 的 V1 全量 | 估 30–75 min —— **必须有缓存** 且建议提供 `--max-units` 抽样模式 |
| 与其它阶段并发 | **不并发**。编排器本身串行执行节点，天然满足；原子工具侧 job_manager 的并发上限需确认 vision 任务与其它重任务不同时跑（必要时给 vision 工具单独并发=1 的约束） |

降本手段（按优先级实现）：

1. 单元抽帧数自适应（短单元 1 帧）；
2. `scene-context` 支持"按 ContextUnit 而非 segment"粒度（300 vs 800+ 次推理）；
3. 相邻单元画面相似时跳过（ffmpeg scene-change 分数 < 阈值则复用上一单元描述）——Phase 2 再做，先跑通。

超时与失败语义：单单元推理超 `VISION_TIMEOUT_SEC` → 记 error 继续下一单元；连续 5 个单元失败 → 整阶段 fail fast（大概率是后端挂了而非内容问题）。

---

## 10. 云端后端预留（本期不实现）

`backends/` 的协议天然可扩展 `dashscope_backend.py`（阿里百炼 `qwen-vl-plus/max`，同家族 prompt 直接复用）。届时：

- `VISION_BACKEND=dashscope` + `DASHSCOPE_API_KEY`（对齐 DEEPSEEK_API_KEY 的 opt-in 模式）；
- 抽帧→base64 多图输入的代码路径与本地完全一致，只换 chat 实现；
- 默认永远是本地，云端显式开启——与项目 local-first 哲学一致。

跨长时段剧情推理（§2.4 列出的 4B 边界外任务）也属于这条路线：届时可按"本地 4B 粗筛 + 云端大模型精看"的混合模式分层。

---

## 11. 测试计划

| 层 | 内容 |
| --- | --- |
| 单测（无模型，CI 可跑） | `frames.py` 抽帧时间点计算；`schema.py` 对畸形模型输出的容错解析；`prompts.py` 模板渲染；config env 覆盖；`parse_vision_progress_line` |
| 单测（mock backend） | `vision_service` 编排逻辑：单元遍历、错误降级、manifest 写出（注入 FakeBackend 返回固定 JSON） |
| 适配器测试 | `video_analyze` adapter 的 validate_params 边界（仿现有 atomic_tools 测试） |
| 集成（标 slow，本地手跑） | 真模型跑 30s 样例视频的 scene-context，断言产物结构 + manifest status=succeeded |
| 缓存回归 | 改 `vision_frames_per_unit` → visual-context 重算且 task-c 级联重算；不改 → 全 hit |

---

## 12. 实施阶段与验收

### Phase 0 — 质量验证（不写正式代码，0.5 天）
脚本跑通 mlx-vlm + Qwen3-VL-4B-4bit：在 2–3 个真实测试片源上人工评估 V1 场景描述、V4 字幕/场景文字分类的输出质量与速度。建议同时对 §2.1 的各信息类型各问一轮，产出一份"能力实测表"，校准 §2.4 的边界判断。
**Gate：场景描述对翻译"有用率"主观 ≥ 70%，单次推理 ≤ 15s，否则换模型档位或终止。**

### Phase 1 — vision 模块 + 原子工具 + CLI（2–3 天）
`translip/vision/` 全量 + `video-analyze` 原子工具 + `analyze-video` 子命令 + 单测 + extra 声明 + i18n/接口文档。
**验收：UI 上传视频跑 scene-context 出结构化 JSON；`uv run pytest -k vision` 全绿；不装 extra 时其余测试不受影响。**

### Phase 2 — 管线节点 + task-c 注入（2 天）
`visual-context` 节点 + bridge + 缓存 spec + 新模板 + TranslationRequest 注入 + 监控权重。
**验收：带 visual 模板端到端跑通；缓存语义正确；对照同一片源有/无视觉上下文的译文 diff，人工确认改善案例。**

### Phase 3 — erase-qc + ocr-classify（2 天）
两个集成点 + 前端报告展示。
**验收：erase-qc 在已知擦除不净的样例（参考 box-vs-polygon 那次的片源）上能标出残留帧。**

### Phase 4（择期）— speaker-visual + dashscope 云后端，以及 §2.3 需求池中验证有价值的项（视频类型识别、章节分段、字幕排版感知等）。

---

## 附：关键先例文件索引（写代码时对照）

| 要抄什么 | 去哪抄 |
| --- | --- |
| 子进程入口 + lazy import + manifest | `src/translip/erase/extract.py` |
| env 配置 | `src/translip/erase/config.py` |
| bridge（命令构建/进度解析/运行包装） | `src/translip/orchestration/erase_bridge.py` |
| 原子工具 adapter + register_tool | `src/translip/server/atomic_tools/adapters/subtitle_detect.py` |
| 缓存 spec | `src/translip/orchestration/cache.py` + runner 中 ocr-detect 的 spec |
| CLI 子命令 | `src/translip/cli.py` 的 `translate-script` |
| ContextUnit / segments JSON 结构 | `src/translip/translation/units.py`、`src/translip/transcription/export.py` |
