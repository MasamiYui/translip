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

## Why `translip`

- **Pipeline + atomic tools, both ways**: run the full "separate → transcribe → translate → dub → re-fit → deliver" chain in one click, or invoke separation, transcription, translation, synthesis, mixing, muxing, and subtitle detect/erase as independent tools.
- **Speaker-aware by default**: outputs are built around speaker profiles and a reusable registry, with a character library that records the "character → speaker" mapping across tasks.
- **Visual dubbing review**: the built-in Dubbing Editor drives segment-by-segment review from an issue queue, with live duration prediction, preview playback rate, and per-segment re-synthesis.
- **Cache-aware, re-runnable orchestration**: each stage is an isolated subprocess that writes artifacts + a manifest; changing one backend/model only recomputes what is needed, and you can re-run from any stage.
- **Local-first with one-click model management**: models run locally by default; the UI configures a HuggingFace token (for gated models) and detects/downloads missing models in one click.

## UI Preview

| Dashboard · pipeline & atomic tasks overview | New pipeline task · stepped wizard + grouped advanced config |
| --- | --- |
| ![Dashboard](docs/assets/readme/dashboard.png) | ![New task](docs/assets/readme/new-task.png) |

| Pipeline task detail · stage DAG and rerun controls | Atomic tools · grouped by audio/speech/video |
| --- | --- |
| ![Task detail](docs/assets/readme/task-detail.png) | ![Atomic tools](docs/assets/readme/atomic-tools.png) |

| A single atomic tool · dialogue/background separation | Dubbing editor · issue queue + inspector |
| --- | --- |
| ![Separation tool](docs/assets/readme/tool-separation.png) | ![Dubbing editor](docs/assets/readme/dubbing-editor.png) |

| Settings · HuggingFace token & one-click model download | Works library · works/episode assets |
| --- | --- |
| ![Settings](docs/assets/readme/settings.png) | ![Works library](docs/assets/readme/works-library.png) |

## System Architecture

```mermaid
flowchart LR
    Input["Input Media<br/>Video / Audio"] --> Stage1["Stage 1<br/>Audio Separation"]
    Stage1 --> TaskA["Task A<br/>Speaker-attributed Transcription"]
    TaskA --> TaskB["Task B<br/>Speaker Profiles / Registry"]
    TaskB --> TaskC["Task C<br/>Dubbing Script Translation"]
    TaskC --> TaskD["Task D<br/>Per-speaker TTS"]
    TaskD --> TaskE["Task E<br/>Timeline Fit And Mix"]
    TaskE --> TaskG["Task G<br/>Final Video Delivery"]

    TaskA -. "+OCR subs template" .-> OCR["OCR subtitle detect/translate<br/>+ subtitle erase"]
    OCR -.-> TaskG

    subgraph ControlPlane["Control Plane (FastAPI + React)"]
        UI["React Management UI"]
        API["FastAPI Service"]
        DB[("SQLite Task Store")]
        Orchestrator["Orchestration / Cache / Artifact Index"]
        Atomic["Atomic Tools Subsystem<br/>standalone job queue"]
    end

    UI <--> API
    API <--> DB
    API <--> Orchestrator
    API <--> Atomic
    Orchestrator --> Stage1 & TaskA & TaskB & TaskC & TaskD & TaskE & TaskG

    TaskE --> Preview["Preview Mix / Dub Audio"]
    TaskG --> Delivery["Final MP4 Delivery"]
```

The orchestrator holds no task logic: it resolves a node DAG, checks a cache, and shells out to each stage as an **isolated subprocess** (the same code path as the CLI subcommands). Heavy ML models are freed on exit and a single stage crash cannot poison the orchestrator. The atomic-tools subsystem is orthogonal to the pipeline: a standalone single-tool job queue that handles uploads, concurrency, cancellation, and artifact registration.

## Core Capabilities

**A. End-to-end dubbing pipeline**

- Separate dialogue and background audio from video or audio inputs.
- Generate speaker-attributed transcripts with `FunASR / Paraformer-zh` (default) or `faster-whisper`; diarization via `ECAPA` or `pyannote 3.1`.
- Build reusable speaker profiles and registries for later tasks.
- Produce dubbing scripts with local `M2M100` or the `SiliconFlow API`.
- Synthesize target-language speech locally with `MOSS-TTS-Nano ONNX` by default, with `Qwen3-TTS` and `VoxCPM2` also available.
- Fit speech back to the original timeline (atempo / rubberband), sidechain-mix, and export preview/final outputs.

**B. Standalone atomic tools** (upload → process → download independently; results can flow into the next tool in one click)

- Dialogue/background separation, audio mixing, speech-to-text, transcript correction, text translation, text-to-speech, audio/video muxing, subtitle detection, subtitle erase, and media probe.

**C. Collaboration & assets**

- **Dubbing Editor**: an issue queue (silence, voice mismatch, duration stretch, low translation confidence, etc.) + inspector + live duration prediction + per-segment re-synthesis.
- **Works / Character libraries**: attach tasks to a "work → episode" and maintain a "character → speaker" ledger, with reusable global personas.
- **Model & token management**: configure the HuggingFace token (to unlock gated models such as pyannote), inspect model status, and download missing models in one click.

## Workflow Templates

`run-pipeline` selects which nodes run via a template:

| Template | Description |
| --- | --- |
| `asr-dub-basic` | Basic dubbing chain: Stage 1 → Task A/B/C/D/E → Task G. The default template. |
| `asr-dub+ocr-subs` | Adds OCR subtitle detection/translation on top of the basic chain and corrects the ASR transcript with the OCR result. |
| `asr-dub+ocr-subs+erase` | Adds hard-subtitle erasure of the source video on top of the above. |

## Web Management UI

The UI is the primary day-to-day entry point. The left navigation is grouped into:

- **Dashboard**: unified counts and recent activity across pipeline tasks and atomic jobs (total / running / completed / failed).
- **Task Center**: pipeline task list, new pipeline task (stepped wizard + grouped advanced config), task detail (stage DAG / progress / artifacts / rerun from any stage), the **Dubbing Editor**, and the speaker-review harness.
- **Atomic Tools**: 10 standalone single-tool jobs (separation, mixing, transcription, correction, translation, synthesis, muxing, subtitle detect/erase, probe), each with its own upload + parameter panel; outputs can flow straight into the next tool.
- **Works / Character libraries**: cross-task works-and-episodes assets and the character→speaker ledger.
- **Settings**: system info & cache cleanup, TMDB API, HuggingFace token, model status & one-click download, and task default parameters.

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
| Stage 1 | `translip run` | Audio separation (demucs / cdx23 / clearervoice) | `voice.*`, `background.*` |
| Task A | `translip transcribe` | Speaker-attributed transcription (FunASR/faster-whisper + diarization) | `segments.zh.json`, `segments.zh.srt` |
| Task B | `translip build-speaker-registry` | Speaker profile / registry | `speaker_profiles.json`, `speaker_registry.json` |
| Task C | `translip translate-script` | Script translation | `translation.<lang>.json`, `translation.<lang>.srt` |
| Task D | `translip synthesize-speaker` | Single-speaker dubbing synthesis | `speaker_segments.<lang>.json`, `speaker_demo.<lang>.wav` |
| Task E | `translip render-dub` | Timeline fitting and mixdown | `dub_voice.<lang>.wav`, `preview_mix.<lang>.wav` |
| Task F | `translip run-pipeline` | Orchestrate Stage 1 to Task E | `pipeline-manifest.json`, `pipeline-status.json` |
| Task G | `translip export-video` | Final video export | `final_preview.<lang>.mp4`, `final_dub.<lang>.mp4` |

> Default backends: ASR `funasr` (model `paraformer-zh`), separation `cdx23`, translation `local-m2m100`, TTS `moss-tts-nano-onnx`.

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
```

Recommended: preload the separation model (or use the UI: Settings → Model status → one-click download):

```bash
uv run translip download-models --backend cdx23 --quality balanced
```

For gated models (e.g. `pyannote` diarization), accept the model license on HuggingFace, then provide a read-scoped access token — either in the Settings page or via `HF_TOKEN` / `HUGGINGFACE_HUB_TOKEN` / `PYANNOTE_AUTH_TOKEN`. The SiliconFlow translation backend needs `SILICONFLOW_API_KEY`.

## Quick Start

`run-pipeline` stops at `task-e` by default (dub audio + preview mix); final video delivery is a separate `export-video` step.

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
├── stage1/example/
├── task-a/voice/
├── task-b/voice/
├── task-c/voice/
├── task-d/voice/<speaker-id>/
├── task-e/voice/
└── task-g/delivery/
```

Final videos are typically written to:

- `output-pipeline/task-g/delivery/final-preview/final_preview.en.mp4`
- `output-pipeline/task-g/delivery/final-dub/final_dub.en.mp4`

### Running stages individually

Each stage can be invoked on its own for debugging or swapping out a single step. The most common ones are below; see the per-stage docs for the full flag set.

```bash
# Stage 1: audio separation
uv run translip run --input ./test_video/example.mp4 --mode auto --quality balanced --output-dir ./output-stage1

# Task A: transcription
uv run translip transcribe --input ./output-stage1/example/voice.wav --output-dir ./output-task-a

# Task C: translation (local M2M100 / SiliconFlow)
uv run translip translate-script --segments ./output-task-a/voice/segments.zh.json \
  --profiles ./output-task-b/voice/speaker_profiles.json --target-lang en \
  --backend local-m2m100 --output-dir ./output-task-c

# Task D: single-speaker synthesis (default moss-tts-nano-onnx; switch to qwen3tts / voxcpm2)
uv run translip synthesize-speaker --translation ./output-task-c/voice/translation.en.json \
  --profiles ./output-task-b/voice/speaker_profiles.json --speaker-id spk_0000 \
  --backend moss-tts-nano-onnx --output-dir ./output-task-d --device auto

# Misc: probe (media info), download-models (preload models)
uv run translip probe --input ./test_video/example.mp4
uv run translip --help    # list all subcommands
```

> `moss-tts-nano-onnx` is the default TTS backend and requires the `moss-tts-nano` CLI from OpenMOSS/MOSS-TTS-Nano installed first; Task D reports a clear dependency error when it is missing. `voxcpm2` uses `openbmb/VoxCPM2` and falls back to CPU on Apple Silicon — set `VOXCPM_ALLOW_MPS=1` to attempt MPS.

## Configuration And Environment Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `TRANSLIP_CACHE_DIR` | `~/.cache/translip` | Root for model cache, pipeline output, and atomic-tools storage |
| `TRANSLIP_DB_PATH` | `<cache>/data.db` | SQLite database path for the web UI |
| `HF_TOKEN` / `HUGGINGFACE_HUB_TOKEN` / `PYANNOTE_AUTH_TOKEN` | none | HuggingFace token to download/use gated models (e.g. pyannote); can also be set in Settings |
| `TMDB_API_KEY` / `TMDB_BEARER_TOKEN` | none | Fetch works/episode metadata and posters for the Works library |
| `SILICONFLOW_API_KEY` | none | Required when using the `siliconflow` translation backend |
| `SILICONFLOW_BASE_URL` | `https://api.siliconflow.cn/v1` | Override the SiliconFlow API endpoint |
| `SILICONFLOW_MODEL` | `deepseek-ai/DeepSeek-V3` | Override the default SiliconFlow model |
| `MOSS_TTS_NANO_CLI` | `moss-tts-nano` | CLI executable used by the `moss-tts-nano-onnx` backend |
| `MOSS_TTS_NANO_MODEL_DIR` | `<cache>/models` | MOSS ONNX model directory passed to `--onnx-model-dir` |
| `MOSS_TTS_NANO_CPU_THREADS` | `4` | CPU thread count for MOSS ONNX inference |
| `QWEN_TTS_MODEL` | — | Override the model loaded by the `qwen3tts` backend |
| `VOXCPM_MODEL` | `openbmb/VoxCPM2` | Override the model loaded by the `voxcpm2` backend |
| `VOXCPM_ALLOW_MPS` | `0` | Allow `voxcpm2` to run on Apple Silicon MPS; defaults to CPU fallback |
| `VOXCPM_INFERENCE_TIMESTEPS` | `10` | Inference steps for `voxcpm2` |
| `VOXCPM_RETRY_BADCASE` | `1` | Enable VoxCPM internal bad-case retry |

For more defaults, see [src/translip/config.py](src/translip/config.py).

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

## Related Documentation

- [docs/README.md](docs/README.md): documentation index
- [docs/speaker-aware-dubbing-plan.md](docs/speaker-aware-dubbing-plan.md): high-level plan and technical route
- [docs/task-f-pipeline-and-engineering-orchestration.md](docs/task-f-pipeline-and-engineering-orchestration.md): orchestration and cache design
- [docs/task-g-final-video-delivery.md](docs/task-g-final-video-delivery.md): final video delivery design
- [docs/frontend-management-system-design.md](docs/frontend-management-system-design.md): management UI design
- [frontend/README.md](frontend/README.md): frontend directory guide

## Chinese README

- [README.md](README.md): full Chinese version
