<div align="center">
  <img src="docs/assets/brand/translip-logo.svg" alt="translip logo" width="112" />
  <h1>translip</h1>
  <p><strong>Local-first, speaker-aware dubbing pipeline for video workflows</strong></p>
  <p>`translip` connects source separation, speaker-attributed transcription, translation, per-speaker TTS, timeline fitting, and final video delivery into a reusable end-to-end pipeline — and exposes each stage as a standalone "atomic tool" you can run on its own, with a FastAPI + React management UI included.</p>
  <p>
    <img src="https://img.shields.io/badge/Python-3.11--3.12-3776AB?logo=python&logoColor=white" alt="Python 3.11-3.12" />
    <img src="https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white" alt="FastAPI" />
    <img src="https://img.shields.io/badge/React-19-149ECA?logo=react&logoColor=white" alt="React 19" />
    <img src="https://img.shields.io/badge/License-Apache--2.0-111827" alt="Apache 2.0" />
    <img src="https://img.shields.io/badge/Status-Beta%20%2F%20Early%20Access-2563EB" alt="Beta / Early Access" />
  </p>
  <p>
    <a href="#quick-start"><strong>Quick Start</strong></a> ·
    <a href="#system-architecture"><strong>Architecture</strong></a> ·
    <a href="#web-management-ui"><strong>Management UI</strong></a> ·
    <a href="docs/README.md"><strong>Docs Index</strong></a> ·
    <a href="README.md"><strong>中文 README</strong></a>
  </p>
</div>

> **Status: Beta / Early Access**
>
> `translip` is currently best suited for research workflows, internal demos, self-hosted iteration, and pipeline exploration. It already provides an end-to-end path, a visual dubbing review surface, and a management UI, but it is intentionally positioned as fast-moving beta software rather than a production-ready product claim.

<details>
<summary><strong>Table of contents</strong></summary>

- [Why translip](#why-translip)
- [UI Preview](#ui-preview)
- [System Architecture](#system-architecture)
- [Core Capabilities](#core-capabilities)
- [Workflow Templates](#workflow-templates)
- [Web Management UI](#web-management-ui)
- [Pipeline Stages](#pipeline-stages)
- [Requirements](#requirements) · [Installation](#installation) · [Quick Start](#quick-start)
- [Configuration & Environment Variables](#configuration-and-environment-variables)
- [Tech Stack](#tech-stack)
- [Roadmap & Status](#roadmap--status)
- [Development](#development) · [Related Documentation](#related-documentation) · [Contact](#contact)

</details>

## Why `translip`

- **Pipeline + atomic tools, both ways**: run the full "separate → transcribe → translate → dub → re-fit → deliver" chain in one click, or invoke separation, transcription, translation, synthesis, mixing, muxing, and subtitle detect/erase as independent tools.
- **AI assistant that orchestrates atomic tools**: describe a goal in one sentence and the assistant (DeepSeek-planned) chains multiple atomic tools into a call graph — it shows the plan first, then runs it and lets you download the outputs.
- **Speaker-aware by default**: outputs are built around speaker profiles and a reusable registry, with a character library that records the "character → speaker" mapping across tasks.
- **Visual dubbing review**: the built-in Dubbing Editor drives segment-by-segment review from an issue queue, with live duration prediction, preview playback rate, and per-segment re-synthesis.
- **Cache-aware, re-runnable orchestration**: each stage is an isolated subprocess that writes artifacts + a manifest; changing one backend/model only recomputes what is needed, and you can re-run from any stage.
- **Local-first with built-in model management**: models run locally by default; the UI configures a HuggingFace token (for gated models) and detects/downloads missing models — all at once, or one at a time (subtitle-erase and vision weights included).

## UI Preview

| Dashboard · pipeline & atomic tasks overview | New pipeline task · stepped wizard + grouped advanced config |
| --- | --- |
| ![Dashboard](docs/assets/readme/dashboard.png) | ![New task](docs/assets/readme/new-task.png) |

| Pipeline task detail · stage DAG and rerun controls | Dubbing editor · issue queue + inspector |
| --- | --- |
| ![Task detail](docs/assets/readme/task-detail.png) | ![Dubbing editor](docs/assets/readme/dubbing-editor.png) |

| AI assistant · orchestrate atomic tools in one sentence | Dub evaluation · per-segment QC + one-click auto-fix |
| --- | --- |
| ![AI assistant](docs/assets/readme/assistant.png) | ![Dub evaluation](docs/assets/readme/evaluation.png) |

| Atomic tools · grouped by audio/speech/video | A single atomic tool · dialogue/background separation |
| --- | --- |
| ![Atomic tools](docs/assets/readme/atomic-tools.png) | ![Separation tool](docs/assets/readme/tool-separation.png) |

| Behind-the-scenes blog · architecture / algorithms / decisions | API docs · live OpenAPI, auto-generated |
| --- | --- |
| ![Blog](docs/assets/readme/blog.png) | ![API docs](docs/assets/readme/api-docs.png) |

| Works library · works/episode assets | Settings · HuggingFace token & one-click model download |
| --- | --- |
| ![Works library](docs/assets/readme/works-library.png) | ![Settings](docs/assets/readme/settings.png) |

## System Architecture

<div align="center">
  <img src="docs/assets/readme/architecture.en.svg" alt="translip system architecture: a control plane (FastAPI + React) drives a cache-aware dubbing pipeline, with optional OCR / visual-perception templates and output deliverables" width="100%" />
</div>

The orchestrator holds no task logic: it resolves a node DAG, checks a cache, and shells out to each stage as an **isolated subprocess** (the same code path as the CLI subcommands). Heavy ML models are freed on exit and a single stage crash cannot poison the orchestrator. The atomic-tools subsystem is orthogonal to the pipeline: a standalone single-tool job queue that handles uploads, concurrency, cancellation, and artifact registration.

## Core Capabilities

**A. End-to-end dubbing pipeline**

- Separate dialogue and background audio from video or audio inputs.
- Generate transcripts with `FunASR / Paraformer-zh` (default) or `faster-whisper`; speaker diarization is optional (off by default, enable explicitly) via `ECAPA` or `pyannote 3.1`.
- Build reusable speaker profiles and registries for later tasks.
- Produce dubbing scripts with local `M2M100` or the `DeepSeek API`; the optional `asr-dub+visual` template attaches a per-segment scene description from a local `Qwen3-VL` model, cutting pronoun/honorific/tone mistranslations.
- Synthesize target-language speech locally with `MOSS-TTS-Nano ONNX` by default, with `Qwen3-TTS` and `VoxCPM2` also available.
- Fit speech back to the original timeline (atempo / rubberband), sidechain-mix, and export preview/final outputs.

**B. Standalone atomic tools** (upload → process → download independently; results can flow into the next tool in one click)

- Audio: dialogue/background separation, audio mixing.
- Speech: speech-to-text, language detection, transcript correction, text translation, text-to-speech, dub render (timeline alignment).
- Video: subtitle detection, subtitle burn/embed, subtitle erase, watermark, video content analysis (scene description / on-screen text triage / erase QC / free-form Q&A), audio/video muxing, M3U8→MP4, and media probe.

**C. Collaboration & assets**

- **AI assistant**: describe a goal in natural language and the assistant plans and executes a chain of atomic capabilities; runs are recorded as "AI tasks" (needs `DEEPSEEK_API_KEY`).
- **Dubbing Editor**: an issue queue (silence, voice mismatch, duration stretch, low translation confidence, etc.) + inspector + live duration prediction + per-segment re-synthesis.
- **Dub evaluation + one-click auto-fix**: per-segment QC of a finished dub — automatically flags missing dub / voice mismatch / dropped words / off-rhythm / unintelligible / poor translation, with an overall score and a quality gate; the "Dub Evaluation" page compares source vs dub segment by segment, highlights dropped words, optionally scores translations with a DeepSeek LLM, and can **auto-fix** the flagged segments in one click (re-translate / re-synthesize / re-fit).
- **Speaker-review harness**: visually review diarization — diagnose, manually merge / assign speakers, and write decisions back into the downstream stages.
- **Works / Character libraries**: attach tasks to a "work → episode" and maintain a "character → speaker" ledger, with reusable global personas.
- **Model & token management**: configure the HuggingFace token (to unlock gated models such as pyannote), inspect model status, and download all missing models at once or one at a time (subtitle-erase `sttn`/`big-lama` and vision `Qwen3-VL` weights are included in the panel).

## Workflow Templates

`run-pipeline` selects which nodes run via a template:

| Template | Description |
| --- | --- |
| `asr-dub-basic` | Basic dubbing chain: separation → transcription → speaker-registry → translation → synthesis → render → delivery. The default template. |
| `asr-dub+visual` | Inserts a visual-perception node (local Qwen3-VL) into the basic chain: per-span scene descriptions are injected as translation context, reducing pronoun/honorific/tone mistranslations. Needs `--extra vision` or a local Ollama (see "Video content perception" below). |
| `asr-dub+ocr-subs` | Adds OCR subtitle detection/translation on top of the basic chain and corrects the ASR transcript with the OCR result. |
| `asr-dub+ocr-subs+erase` | Adds hard-subtitle erasure of the source video on top of the above. |

## Web Management UI

The UI is the primary day-to-day entry point. The left navigation is grouped into:

- **Dashboard**: unified counts and recent activity across pipeline tasks and atomic jobs (total / running / completed / failed).
- **Task Center**: three task lists + the create entry — **Pipeline Tasks**, **Atomic Tasks**, **AI Tasks** (AI-assistant runs), and Create Pipeline Task (stepped wizard + grouped advanced config). Opening a pipeline task exposes the stage DAG / progress / artifacts, rerun-from-any-stage, the **Dubbing Editor**, and the speaker-review harness.
- **Atomic Tools**: 16 standalone single-tool jobs grouped by audio / speech / video (separation, mixing | transcription, language detection, correction, translation, synthesis, dub render | subtitle detect, subtitle burn/embed, subtitle erase, watermark, video content analysis, muxing, M3U8→MP4, probe), each with its own upload + parameter panel; outputs can flow straight into the next tool.
- **Works Library**: cross-task "work → episode" assets, with TMDB metadata and posters.
- **Character Library**: the "character → speaker" ledger, with reusable global personas.
- **Dub Evaluation**: pick a finished task to compare source vs dub segment by segment, locating missing-dub / voice / dropped-word / translation issues with an overall score; optionally score translations with a DeepSeek LLM.
- **Blog**: the "behind-the-scenes" series (architecture / algorithms / decisions), with search and PDF export.
- **API Docs**: a full backend REST API reference generated from the live OpenAPI spec, always in sync with the code.
- **Testing Lab**: links out to the standalone evaluation lab (`translip-lab`, default `:8799`) that benchmarks each capability against ground-truth datasets.
- **Settings**: system info & cache cleanup, TMDB API, HuggingFace token, model status & download (all missing / one at a time), and task default parameters.

> **AI assistant**: a chat assistant you can summon from the bottom-right of any page (it opens as a right-docked drawer). Describe a goal in one sentence (e.g. "dub this video into English", "erase the hard subtitles"), and the assistant uses DeepSeek to plan your request into a chain of atomic capabilities and shows it first; confirm (editing each step's params if needed) and run it in one click, then download the outputs. Runs are recorded as "AI tasks" and need `DEEPSEEK_API_KEY` configured in Settings.

<div align="center">
  <img src="docs/assets/readme/assistant-flow.en.svg" alt="AI assistant flow: natural-language goal → DeepSeek plans an atomic-tool chain → review the editable plan → run the tools in order → download outputs, with multi-turn re-planning" width="100%" />
</div>

### Development Mode

Start the backend API first:

```bash
uv run uvicorn translip.server.app:app --host 127.0.0.1 --port 8765
```

Then start the frontend:

```bash
cd frontend
npm install
npm run dev
```

- Frontend: `http://127.0.0.1:5173`
- Backend API: `http://127.0.0.1:8765`
- `frontend/vite.config.ts` already proxies `/api` to `127.0.0.1:8765`; the frontend uses relative API paths and needs no extra env vars.

Or use the built-in dev control script (logs and PIDs land in `.dev-runtime/`):

```bash
./scripts/dev.sh start     # boots backend :8765 + frontend :5173 (detached)
./scripts/dev.sh status    # check status
./scripts/dev.sh stop       # stop
./scripts/dev.sh restart    # restart
```

### Serve The Built Frontend Through The Backend (production-style)

```bash
cd frontend && npm install && npm run build && cd ..
uv run translip-server
```

If `frontend/dist` exists, the backend mounts and serves the static frontend from `http://127.0.0.1:8765`. `translip-server` listens on `127.0.0.1:8765` by default; for a custom host/port use `uvicorn translip.server.app:app ...` directly.

## Pipeline Stages

Every stage is both a node in `run-pipeline` orchestration and a CLI subcommand you can run on its own.

| Stage | Command | Purpose | Main Outputs |
| --- | --- | --- | --- |
| separation | `translip run` | Audio separation (demucs / cdx23; `--enhance-voice` is a no-op placeholder, no real denoise yet) | `voice.*`, `background.*` |
| transcription | `translip transcribe` | Speaker-attributed transcription (FunASR/faster-whisper + diarization) | `segments.zh.json`, `segments.zh.srt` |
| speaker-registry | `translip build-speaker-registry` | Speaker profile / registry | `speaker_profiles.json`, `speaker_registry.json` |
| translation | `translip translate-script` | Script translation | `translation.<lang>.json`, `translation.<lang>.srt` |
| synthesis | `translip synthesize-speaker` | Single-speaker dubbing synthesis | `speaker_segments.<lang>.json`, `speaker_demo.<lang>.wav` |
| render | `translip render-dub` | Timeline fitting and mixdown | `dub_voice.<lang>.wav`, `preview_mix.<lang>.wav` |
| (orchestration) | `translip run-pipeline` | Orchestrate separation to render | `pipeline-manifest.json`, `pipeline-status.json` |
| delivery | `translip export-video` | Final video export | `final_preview.<lang>.mp4`, `final_dub.<lang>.mp4` |

> Default backends: ASR `funasr` (model `paraformer-zh`), separation `cdx23`, translation `local-m2m100`, TTS `moss-tts-nano-onnx`.

### Video content perception (Qwen3-VL, optional)

`translip analyze-video` analyzes video frames with a local vision-language model. It powers both the `visual-context` node of the `asr-dub+visual` template and the "Video Content Analysis" atomic tool:

```bash
# Scene descriptions (fixed-interval spans without --segments; the pipeline feeds the ASR timeline)
uv run translip analyze-video --input video.mp4 --task scene-context --output-dir out-vision

# Free-form Q&A
uv run translip analyze-video --input video.mp4 --task freeform --question "What car appears in the video?"

# On-screen text triage (subtitle vs scene text vs watermark vs title card; needs subtitle detection first)
uv run translip analyze-video --input video.mp4 --task ocr-classify --detection ocr-detect/ocr_events.json
```

- **Tasks**: `scene-context` | `erase-qc` | `ocr-classify` | `speaker-visual` | `freeform`.
- **Backends**: Apple Silicon defaults to MLX (`mlx-community/Qwen3-VL-4B-Instruct-4bit`, ~3.3 GB, auto-downloaded to `<cache>/vision_models/hf`; install with `uv sync --extra vision`); other platforms can point at a local Ollama (`ollama pull qwen3-vl:4b-instruct`) with zero extra dependencies. Controlled via `--backend auto|mlx|ollama`.
- **Fully local**: like OCR/erase, no cloud calls; translation degrades gracefully when the visual artifact is missing.

### Hard-subtitle erasure (optional)

The `asr-dub+ocr-subs+erase` template and the "Subtitle Erase" atomic tool reuse the OCR detection boxes to inpaint the source video's hard subtitles frame by frame, then re-mux the original audio — no second detector, and erasure is bounded by the detection boxes:

- **Backends**: `sttn` (default — spatial-temporal transformer video inpainting, better temporal coherence) | `lama` (big-LaMa single-frame, sharper for stills/animation).
- **Install**: `uv sync --extra erase` (cv2 / pydantic-settings; torch is a base dependency, no separate install).
- **Weights**: `sttn.pth` (~63 MB) and `big-lama.pt` (~196 MB) auto-download from the upstream GitHub tree and are sha256-verified on first use, cached under `<cache>/erase_models` (override with `SUBTITLE_ERASE_MODELS_DIR`; `SUBTITLE_ERASE_LOCAL_MODELS_ONLY=1` forbids downloads — weights must be pre-placed). They can also be downloaded per-model from Settings → Model status.
- **Fully local**: only subtitle frames are inpainted before re-muxing the original audio; no cloud calls.

## Requirements

- Python `3.11` to `3.12`
- [uv](https://docs.astral.sh/uv/)
- FFmpeg available on `PATH`
- Node.js + npm (only for frontend development or building the UI)
- macOS or Linux; CPU works, Apple Silicon uses MPS automatically, and TTS is more practical with `CUDA` or `MPS`

## Installation

```bash
git clone https://github.com/MasamiYui/translip.git
cd translip
uv sync                 # runtime deps
uv sync --extra dev     # add pytest etc. for tests / development
uv sync --extra ocr     # in-tree PaddleOCR hard-subtitle detection
uv sync --extra erase   # hard-subtitle erasure (STTN / big-LaMa inpainting; ~63MB / ~196MB weights auto-download on first use)
uv sync --extra vision  # video content perception (Qwen3-VL; only needed on Apple Silicon — other platforms can use Ollama with no extra)
uv sync --extra lab     # evaluation lab (translip-lab; adds only Pillow)
```

> `uv sync --extra X` syncs the environment to *exactly* X, dropping other extras — combine flags to keep several, e.g. `uv sync --extra dev --extra ocr --extra erase --extra vision`.

Recommended: preload the separation model (or use the UI: Settings → Model status → one-click download):

```bash
uv run translip download-models --backend cdx23 --quality balanced
```

> `--backend` also accepts other downloadable keys, e.g. `erase_sttn` / `erase_lama` / `vision_qwen3vl_mlx` / `faster_whisper_small` / `funasr_*`; `translip doctor` lists what is currently missing along with the matching download command.

For gated models (e.g. `pyannote` diarization), accept the model license on HuggingFace, then provide a read-scoped access token — either in the Settings page or via `HF_TOKEN` / `HUGGINGFACE_HUB_TOKEN` / `PYANNOTE_AUTH_TOKEN`. The DeepSeek translation backend, transcript-correction LLM arbitration, translation quality scoring, and AI-assistant planning need `DEEPSEEK_API_KEY`.

After installing, run the environment self-check to confirm FFmpeg, the inference device (CUDA/MPS/CPU), optional extras, external CLIs, API keys, and model weights are all ready:

```bash
uv run translip doctor          # human-readable report (missing items include a download command); add --json for CI / scripts
```

## Quick Start

`run-pipeline` stops at `render` by default (dub audio + preview mix); final video delivery is a separate `export-video` step.

```bash
uv run translip run-pipeline \
  --input ./test_video/example.mp4 \
  --output-root ./output-pipeline \
  --target-lang en \
  --write-status

uv run translip export-video \
  --pipeline-root ./output-pipeline
```

Typical output layout:

```text
output-pipeline/
├── pipeline-manifest.json
├── pipeline-report.json
├── pipeline-status.json
├── logs/
├── separation/example/
├── transcription/voice/
├── speaker-registry/voice/
├── translation/voice/
├── synthesis/voice/<speaker-id>/
├── render/voice/
└── delivery/delivery/
```

Final videos are typically written to:

- `output-pipeline/delivery/delivery/final-preview/final_preview.en.mp4`
- `output-pipeline/delivery/delivery/final-dub/final_dub.en.mp4`

### Running stages individually

Each stage can be invoked on its own for debugging or swapping out a single step. The most common ones are below; see the per-stage docs for the full flag set.

```bash
# separation: audio separation
uv run translip run --input ./test_video/example.mp4 --mode auto --quality balanced --output-dir ./output-separation

# transcription: transcription
uv run translip transcribe --input ./output-separation/example/voice.wav --output-dir ./output-transcription

# translation: translation (local M2M100 / DeepSeek)
uv run translip translate-script --segments ./output-transcription/voice/segments.zh.json \
  --profiles ./output-speaker-registry/voice/speaker_profiles.json --target-lang en \
  --backend local-m2m100 --output-dir ./output-translation

# synthesis: single-speaker synthesis (default moss-tts-nano-onnx; switch to qwen3tts / voxcpm2)
uv run translip synthesize-speaker --translation ./output-translation/voice/translation.en.json \
  --profiles ./output-speaker-registry/voice/speaker_profiles.json --speaker-id spk_0000 \
  --backend moss-tts-nano-onnx --output-dir ./output-synthesis --device auto

# Dub evaluation: per-segment QC of finished pipeline output (missing dub / voice / dropped words / rhythm / translation)
uv run translip evaluate-dub --pipeline-root ./output-pipeline/<task_id> --target-lang en \
  --output-dir ./output-pipeline/<task_id>/analysis/dub-qa
#   add --translation-judge to score translations with a DeepSeek LLM (needs DEEPSEEK_API_KEY)

# Misc: doctor (environment self-check), probe (media info), download-models (preload models)
uv run translip doctor
uv run translip probe --input ./test_video/example.mp4
uv run translip --help    # list all subcommands
```

> `moss-tts-nano-onnx` is the default TTS backend and requires the `moss-tts-nano` CLI from OpenMOSS/MOSS-TTS-Nano installed first; synthesis reports a clear dependency error when it is missing. `voxcpm2` uses `openbmb/VoxCPM2` and falls back to CPU on Apple Silicon — set `VOXCPM_ALLOW_MPS=1` to attempt MPS.

## Configuration And Environment Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `TRANSLIP_CACHE_DIR` | `~/.cache/translip` | Root for model cache, pipeline output, and atomic-tools storage |
| `TRANSLIP_DB_PATH` | `<cache>/data.db` | SQLite database path for the web UI |
| `HF_TOKEN` / `HUGGINGFACE_HUB_TOKEN` / `PYANNOTE_AUTH_TOKEN` | none | HuggingFace token to download/use gated models (e.g. pyannote); can also be set in Settings |
| `TMDB_API_KEY` / `TMDB_BEARER_TOKEN` | none | Fetch works/episode metadata and posters for the Works library |
| `DEEPSEEK_API_KEY` | none | Required for the `deepseek` translation backend, transcript-correction LLM arbitration, translation quality scoring, and AI-assistant planning |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | Override the DeepSeek API endpoint |
| `DEEPSEEK_MODEL` | `deepseek-v4-pro` | Override the default DeepSeek model |
| `MOSS_TTS_NANO_CLI` | `moss-tts-nano` | CLI executable used by the `moss-tts-nano-onnx` backend |
| `MOSS_TTS_NANO_MODEL_DIR` | `<cache>/models` | MOSS ONNX model directory passed to `--onnx-model-dir` |
| `MOSS_TTS_NANO_CPU_THREADS` | `4` | CPU thread count for MOSS ONNX inference |
| `QWEN_TTS_MODEL` | — | Override the model loaded by the `qwen3tts` backend |
| `VOXCPM_MODEL` | `openbmb/VoxCPM2` | Override the model loaded by the `voxcpm2` backend |
| `VOXCPM_ALLOW_MPS` | `0` | Allow `voxcpm2` to run on Apple Silicon MPS; defaults to CPU fallback |
| `VOXCPM_INFERENCE_TIMESTEPS` | `10` | Inference steps for `voxcpm2` |
| `VOXCPM_RETRY_BADCASE` | `1` | Enable VoxCPM internal bad-case retry |
| `VISION_BACKEND` | `auto` | Video perception backend: `auto` / `mlx` / `ollama` |
| `VISION_MODEL` | `mlx-community/Qwen3-VL-4B-Instruct-4bit` | HF model loaded by the MLX backend |
| `VISION_OLLAMA_MODEL` | `qwen3-vl:4b-instruct` | Ollama model tag (avoid the bare `:4b` tag — it may resolve to the thinking variant) |
| `VISION_OLLAMA_HOST` | `http://127.0.0.1:11434` | Ollama server address |
| `VISION_HF_CACHE` | `<cache>/vision_models/hf` | Vision model weight cache (injected as `HF_HUB_CACHE`) |
| `VISION_LOCAL_MODELS_ONLY` | `0` | Set `1` to forbid downloads; weights must be pre-placed |
| `SUBTITLE_ERASE_MODELS_DIR` | `<cache>/erase_models` | Cache for subtitle-erase weights (`sttn.pth` / `big-lama.pt`) |
| `SUBTITLE_ERASE_LOCAL_MODELS_ONLY` | `0` | Set `1` to forbid downloading erase weights; must be pre-placed |
| `PADDLEOCR_MODELS_BASE_DIR` | `<cache>/paddleocr_models` | Local PP-OCRv5 subtitle-OCR model directory |
| `TRANSLIP_NO_BANNER` | none | Set to any value to suppress the startup banner + env summary (same as `--no-banner`) |

For more defaults, see [src/translip/config.py](src/translip/config.py); the remaining `VISION_*` knobs (frames/resolution/temperature) live in [src/translip/vision/config.py](src/translip/vision/config.py), and `ERASE_*` / `PADDLEOCR_*` in [src/translip/erase/config.py](src/translip/erase/config.py) and [src/translip/ocr/config.py](src/translip/ocr/config.py).

## Tech Stack

| Layer | Stack |
| --- | --- |
| Orchestration / CLI | Python 3.11–3.12 · cache-aware DAG orchestrator · isolated subprocess execution (crash-isolated, models freed on exit) |
| Control plane | FastAPI · SQLModel (SQLite + WAL) · SSE live progress · concurrent atomic-tools job queue |
| Management UI | React 19 · TypeScript · Vite · Tailwind 4 · TanStack Query · Zustand · React Router · bilingual (zh/en) i18n |
| Speech / vision models | demucs · CDX23 · faster-whisper · FunASR/Paraformer · ECAPA / pyannote · M2M100 / DeepSeek · MOSS-TTS-Nano / Qwen3-TTS / VoxCPM2 · PaddleOCR · STTN / big-LaMa · Qwen3-VL (MLX / Ollama) |
| Media | FFmpeg (atempo / rubberband time-stretch · sidechain mix · mux / subtitle burn) |

## Development

```bash
# Backend
uv sync --extra dev
uv run pytest

# Frontend
cd frontend
npm install
npm run lint
npm run build
npm run test       # Vitest unit/component tests
```

End-to-end Playwright tests live at the repo root (`tests/e2e/*.spec.ts`); start the dev stack first with `./scripts/dev.sh start`, then run `npx playwright test`.

## Roadmap & Status

translip is fast-moving beta software. Here is the **honest scope** — what has landed, what is a placeholder, and what is next:

**Available now**

- End-to-end dubbing pipeline (separate → transcribe → translate → synthesize → re-fit → deliver), cache-aware and re-runnable from any stage.
- 16 atomic tools + AI-assistant orchestration; Dubbing Editor, dub evaluation, one-click auto-fix, speaker review.
- OCR hard-subtitle detection / translation / erasure; Qwen3-VL visual perception injected into translation context.
- Speaker profiles / registry, Works / Character libraries, model & token management, bilingual UI.

**Placeholder / limited**

- `--enhance-voice` is currently a **no-op placeholder** (`NoOpVoiceEnhancer`) — no real denoise / dereverb backend yet.
- The default TTS (MOSS-TTS-Nano) has limited timbre; higher-quality voice cloning is better served by `voxcpm2` on a GPU.
- Erasure coverage is bounded by the OCR detection boxes — anything the detector misses is not inpainted.

**Next**

- A real voice-enhancement backend; stronger local TTS timbre; deeper vision integration for erase-qc / ocr-classify (see [docs/qwen3-vl-integration-plan.md](docs/qwen3-vl-integration-plan.md) Phase 3).

## Related Documentation

- [docs/README.md](docs/README.md): documentation index
- [docs/speaker-aware-dubbing-plan.md](docs/speaker-aware-dubbing-plan.md): high-level plan and technical route
- [docs/pipeline-and-engineering-orchestration.md](docs/pipeline-and-engineering-orchestration.md): orchestration and cache design
- [docs/final-video-delivery.md](docs/final-video-delivery.md): final video delivery design
- [docs/qwen3-vl-integration-plan.md](docs/qwen3-vl-integration-plan.md): video content perception (Qwen3-VL) integration plan
- [docs/frontend-management-system-design.md](docs/frontend-management-system-design.md): management UI design
- [frontend/README.md](frontend/README.md): frontend directory guide

## Contact

Questions, suggestions, or collaboration — feel free to reach out:

- 📧 Email: [sherlock.yin1994@gmail.com](mailto:sherlock.yin1994@gmail.com)
- 🐧 QQ: 546253846

## Chinese README

- [README.md](README.md): full Chinese version
