# translip

**Speaker-aware multilingual video dubbing pipeline.**

Separates voice and background audio from a source video, transcribes with speaker attribution, translates, clones each speaker's voice in the target language, and exports a final dubbed MP4 — with a web-based management UI included.

[English](#english) · [中文](#中文)

---

## English

### Overview

`translip` is a local, end-to-end video dubbing pipeline. Given a source video file and a target language, it produces a fully dubbed MP4 with per-speaker voice cloning.

**Pipeline stages:**

| Stage | Name | Description |
|-------|------|-------------|
| Stage 1 | Audio Separation | Splits voice track and background using Demucs / CDX23 |
| Task A | Transcription | ASR via faster-whisper + speaker diarization (SpeechBrain ECAPA) |
| Task B | Speaker Registry | Builds speaker profiles and matches against a persistent registry |
| Task C | Translation | Translates segments with M2M100 (local) or SiliconFlow API |
| Task D | Voice Cloning | Synthesizes target-language speech per speaker via Qwen3-TTS |
| Task E | Timeline Fitting | Assembles dub audio onto the original timeline with background ducking |
| Task G | Video Delivery | Muxes dubbed audio back into the source video and exports final MP4 |
| Task F | Orchestration | Cache-aware multi-stage pipeline runner with status tracking |

**Management UI** — A full-stack web interface (FastAPI + React) lets you create and monitor pipeline tasks in real time with per-stage progress graphs, manifest viewers, and artifact downloads.

---

### Requirements

- Python 3.11–3.12
- [uv](https://docs.astral.sh/uv/) package manager
- FFmpeg (available in PATH)
- macOS / Linux (MPS or CUDA recommended for Task D; CPU is supported)

---

### Installation

```bash
git clone https://github.com/MasamiYui/translip.git
cd translip
uv sync
```

Pre-download CDX23 dialogue separation checkpoints (recommended):

```bash
uv run translip download-models --backend cdx23 --quality balanced
```

---

### Quick Start — Full Pipeline

Run the full pipeline on a source video (Stage 1 → Task G):

```bash
uv run translip run-pipeline \
  --input ./test_video/example.mp4 \
  --output-root ./output-pipeline \
  --target-lang en \
  --write-status
```

Then export the final video:

```bash
uv run translip export-video \
  --pipeline-root ./output-pipeline
```

**Outputs:**
- `final-preview/final_preview.en.mp4` — preview mix (original voice ducked)
- `final-dub/final_dub.en.mp4` — dubbed version (voice track replaced)

---

### Web Management UI

Start the backend API server:

```bash
uv run translip-server --host 127.0.0.1 --port 8765
# or directly:
uv run uvicorn translip.server.app:app --host 127.0.0.1 --port 8765
```

Start the frontend dev server:

```bash
cd frontend
npm install
npm run dev
# Opens at http://localhost:5173
```

Features:
- **Dashboard** — task stats and active pipeline graphs
- **Task List** — filter and browse all tasks
- **New Task** — 4-step form to configure and launch a pipeline run
- **Task Detail** — real-time stage progress, manifest viewer, artifact downloads
- **Settings** — system info, device, Python version, cache usage

---

### CLI Reference

#### Stage 1 — Audio Separation

```bash
uv run translip run \
  --input ./test_video/example.mp4 \
  --mode auto \
  --quality balanced \
  --output-dir ./output
```

`--mode auto` selects `dialogue` (CDX23) for voice-dominant content and `music` (Demucs) otherwise.

#### Task A — Transcription

```bash
uv run translip transcribe \
  --input ./output/example/voice.mp3 \
  --output-dir ./output-task-a
```

Outputs: `segments.zh.json`, `segments.zh.srt`, `task-a-manifest.json`

#### Task B — Speaker Registry

```bash
uv run translip build-speaker-registry \
  --segments ./output-task-a/voice/segments.zh.json \
  --audio ./output/example/voice.mp3 \
  --output-dir ./output-task-b \
  --registry ./output-task-b/registry/speaker_registry.json \
  --update-registry
```

Outputs: `speaker_profiles.json`, `speaker_matches.json`, `speaker_registry.json`

#### Task C — Translation

```bash
# Local M2M100
uv run translip translate-script \
  --segments ./output-task-a/voice/segments.zh.json \
  --profiles ./output-task-b/voice/speaker_profiles.json \
  --target-lang en \
  --backend local-m2m100 \
  --glossary ./config/glossary.example.json \
  --output-dir ./output-task-c

# SiliconFlow API
export SILICONFLOW_API_KEY=<your-key>
uv run translip translate-script \
  ... \
  --backend siliconflow \
  --api-model deepseek-ai/DeepSeek-V3
```

Outputs: `translation.en.json`, `translation.en.srt`

#### Task D — Voice Cloning

```bash
uv run translip synthesize-speaker \
  --translation ./output-task-c/voice/translation.en.json \
  --profiles ./output-task-b/voice/speaker_profiles.json \
  --speaker-id spk_0001 \
  --output-dir ./output-task-d \
  --backend qwen3tts \
  --device auto
```

Outputs: `speaker_segments.en.json`, `speaker_demo.en.wav`

#### Task E — Timeline Fitting & Mixing

```bash
uv run translip render-dub \
  --background ./output/example/background.mp3 \
  --segments ./output-task-a/voice/segments.zh.json \
  --translation ./output-task-c/voice/translation.en.json \
  --task-d-report ./output-task-d/voice/spk_0001/speaker_segments.en.json \
  --output-dir ./output-task-e \
  --fit-policy conservative \
  --mix-profile preview
```

Outputs: `dub_voice.en.wav`, `preview_mix.en.wav`, `timeline.en.json`

#### Task G — Export Video

```bash
uv run translip export-video \
  --pipeline-root ./output-pipeline
```

#### Other Commands

| Command | Description |
|---------|-------------|
| `probe` | Inspect media metadata (duration, codecs, sample rate) |
| `download-models` | Pre-download backend checkpoints |

---

### Configuration

Default values are in `src/translip/config.py`:

| Key | Default | Description |
|-----|---------|-------------|
| `DEFAULT_SAMPLE_RATE` | 44,100 Hz | Output sample rate |
| Transcription sample rate | 16,000 Hz | Internal ASR rate |
| Device | auto (CPU/CUDA/MPS) | Compute device |
| Cache root | `~/.cache/translip` | Override with `TRANSLIP_CACHE_DIR` |

---

### Development

```bash
uv sync
uv run pytest tests/
```

---

### Architecture

```
src/translip/
├── pipeline/        # Stage 1 — audio separation (Demucs, CDX23)
├── transcription/   # Task A — ASR + diarization
├── speakers/        # Task B — speaker embeddings, registry
├── translation/     # Task C — M2M100 / SiliconFlow
├── dubbing/         # Task D — Qwen3-TTS voice cloning
├── rendering/       # Task E — timeline fitting, mixing, ducking
├── delivery/        # Task G — FFmpeg video muxing
├── orchestration/   # Task F — cache-aware pipeline runner
├── server/          # FastAPI backend + SQLite task management
└── models/          # Model backends (DemucsMusicSeparator, Cdx23DialogueSeparator)
```

---

### Docs

- [docs/README.md](docs/README.md) — document index
- [docs/technical-design.md](docs/technical-design.md) — source separation design
- [docs/speaker-aware-dubbing-plan.md](docs/speaker-aware-dubbing-plan.md) — overall dubbing plan
- [docs/task-f-pipeline-and-engineering-orchestration.md](docs/task-f-pipeline-and-engineering-orchestration.md) — pipeline orchestration
- [docs/task-g-final-video-delivery.md](docs/task-g-final-video-delivery.md) — video delivery design
- [docs/frontend-management-system-design.md](docs/frontend-management-system-design.md) — web UI design

---

## 中文

### 概述

`translip` 是一个本地端到端视频配音流水线。输入一个源视频和目标语言，即可输出带有逐说话人声音克隆的完整配音 MP4。

**流水线阶段：**

| 阶段 | 名称 | 说明 |
|------|------|------|
| Stage 1 | 音频分离 | 使用 Demucs / CDX23 分离人声与背景音 |
| Task A | 语音转写 | faster-whisper ASR + SpeechBrain ECAPA 说话人分割 |
| Task B | 说话人注册表 | 构建说话人档案并与持久化注册表匹配 |
| Task C | 翻译 | 使用 M2M100（本地）或 SiliconFlow API 翻译 |
| Task D | 声音克隆 | 通过 Qwen3-TTS 为每位说话人合成目标语言语音 |
| Task E | 时间轴拟合 | 将配音音频按原始时间轴拼装，含背景音自动压低 |
| Task G | 视频交付 | 将配音音频混入源视频并导出最终 MP4 |
| Task F | 流水线编排 | 支持缓存复用的多阶段流水线执行器，含状态跟踪 |

**管理界面** — 内置全栈 Web 界面（FastAPI + React），可实时创建和监控流水线任务，支持逐阶段进度图、Manifest 查看、产物文件下载。

---

### 环境要求

- Python 3.11–3.12
- [uv](https://docs.astral.sh/uv/) 包管理器
- FFmpeg（需在 PATH 中）
- macOS / Linux（Task D 推荐使用 MPS 或 CUDA；支持 CPU）

---

### 安装

```bash
git clone https://github.com/MasamiYui/translip.git
cd translip
uv sync
```

预下载 CDX23 对话分离模型（推荐）：

```bash
uv run translip download-models --backend cdx23 --quality balanced
```

---

### 快速开始 — 完整流水线

对源视频运行完整流水线（Stage 1 → Task G）：

```bash
uv run translip run-pipeline \
  --input ./test_video/example.mp4 \
  --output-root ./output-pipeline \
  --target-lang en \
  --write-status
```

导出最终视频：

```bash
uv run translip export-video \
  --pipeline-root ./output-pipeline
```

**输出文件：**
- `final-preview/final_preview.en.mp4` — 预览混音版（原声压低）
- `final-dub/final_dub.en.mp4` — 配音版（人声替换）

---

### Web 管理界面

启动后端 API 服务：

```bash
uv run translip-server --host 127.0.0.1 --port 8765
# 或直接启动：
uv run uvicorn translip.server.app:app --host 127.0.0.1 --port 8765
```

启动前端开发服务：

```bash
cd frontend
npm install
npm run dev
# 访问 http://localhost:5173
```

功能说明：
- **仪表盘** — 任务统计与活跃流水线进度图
- **任务列表** — 筛选与浏览所有任务
- **新建任务** — 四步配置表单，快速启动流水线任务
- **任务详情** — 实时阶段进度、Manifest 查看、产物文件下载
- **全局设置** — 系统信息、设备、Python 版本、缓存用量

---

### CLI 命令说明

#### Stage 1 — 音频分离

```bash
uv run translip run \
  --input ./test_video/example.mp4 \
  --mode auto \
  --quality balanced \
  --output-dir ./output
```

`--mode auto` 会对人声主导内容自动选择 `dialogue`（CDX23），否则使用 `music`（Demucs）。

#### Task A — 语音转写

```bash
uv run translip transcribe \
  --input ./output/example/voice.mp3 \
  --output-dir ./output-task-a
```

输出：`segments.zh.json`、`segments.zh.srt`、`task-a-manifest.json`

#### Task B — 说话人注册表

```bash
uv run translip build-speaker-registry \
  --segments ./output-task-a/voice/segments.zh.json \
  --audio ./output/example/voice.mp3 \
  --output-dir ./output-task-b \
  --registry ./output-task-b/registry/speaker_registry.json \
  --update-registry
```

输出：`speaker_profiles.json`、`speaker_matches.json`、`speaker_registry.json`

#### Task C — 翻译

```bash
# 本地 M2M100
uv run translip translate-script \
  --segments ./output-task-a/voice/segments.zh.json \
  --profiles ./output-task-b/voice/speaker_profiles.json \
  --target-lang en \
  --backend local-m2m100 \
  --glossary ./config/glossary.example.json \
  --output-dir ./output-task-c

# SiliconFlow API
export SILICONFLOW_API_KEY=<your-key>
uv run translip translate-script \
  ... \
  --backend siliconflow \
  --api-model deepseek-ai/DeepSeek-V3
```

输出：`translation.en.json`、`translation.en.srt`

#### Task D — 声音克隆

```bash
uv run translip synthesize-speaker \
  --translation ./output-task-c/voice/translation.en.json \
  --profiles ./output-task-b/voice/speaker_profiles.json \
  --speaker-id spk_0001 \
  --output-dir ./output-task-d \
  --backend qwen3tts \
  --device auto
```

输出：`speaker_segments.en.json`、`speaker_demo.en.wav`

#### Task E — 时间轴拟合与混音

```bash
uv run translip render-dub \
  --background ./output/example/background.mp3 \
  --segments ./output-task-a/voice/segments.zh.json \
  --translation ./output-task-c/voice/translation.en.json \
  --task-d-report ./output-task-d/voice/spk_0001/speaker_segments.en.json \
  --output-dir ./output-task-e \
  --fit-policy conservative \
  --mix-profile preview
```

输出：`dub_voice.en.wav`、`preview_mix.en.wav`、`timeline.en.json`

#### Task G — 视频导出

```bash
uv run translip export-video \
  --pipeline-root ./output-pipeline
```

#### 其他命令

| 命令 | 说明 |
|------|------|
| `probe` | 查看媒体文件元信息（时长、编解码器、采样率等） |
| `download-models` | 预下载后端模型检查点 |

---

### 配置

默认值在 `src/translip/config.py` 中：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `DEFAULT_SAMPLE_RATE` | 44,100 Hz | 输出采样率 |
| 转写采样率 | 16,000 Hz | ASR 内部采样率 |
| 设备 | auto（CPU/CUDA/MPS） | 运算设备 |
| 缓存目录 | `~/.cache/translip` | 可通过 `TRANSLIP_CACHE_DIR` 覆盖 |

---

### 开发

```bash
uv sync
uv run pytest tests/
```

---

### 架构说明

```
src/translip/
├── pipeline/        # Stage 1 — 音频分离（Demucs、CDX23）
├── transcription/   # Task A — ASR + 说话人分割
├── speakers/        # Task B — 说话人嵌入、注册表
├── translation/     # Task C — M2M100 / SiliconFlow
├── dubbing/         # Task D — Qwen3-TTS 声音克隆
├── rendering/       # Task E — 时间轴拟合、混音、压低
├── delivery/        # Task G — FFmpeg 视频混流
├── orchestration/   # Task F — 缓存感知流水线执行器
├── server/          # FastAPI 后端 + SQLite 任务管理
└── models/          # 模型后端（DemucsMusicSeparator、Cdx23DialogueSeparator）
```

---

### 文档

- [docs/README.md](docs/README.md) — 文档索引
- [docs/technical-design.md](docs/technical-design.md) — 音频分离系统设计
- [docs/speaker-aware-dubbing-plan.md](docs/speaker-aware-dubbing-plan.md) — 多阶段配音整体方案
- [docs/task-f-pipeline-and-engineering-orchestration.md](docs/task-f-pipeline-and-engineering-orchestration.md) — 流水线编排设计
- [docs/task-g-final-video-delivery.md](docs/task-g-final-video-delivery.md) — 视频交付设计
- [docs/frontend-management-system-design.md](docs/frontend-management-system-design.md) — Web 管理界面设计
