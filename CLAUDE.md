# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`translip` is a local-first, multi-speaker-aware video dubbing pipeline: audio separation → speaker-attributed transcription → translation → single-speaker TTS → timeline re-fit/mix → video delivery. It ships as a Python CLI/library (`src/translip`) plus a FastAPI control plane and a React management UI (`frontend/`). Status is Beta/early-access. The README (`README.md` / `README.en.md`) is the canonical user-facing doc and is more detailed than this file on CLI flags.

## Commands

Backend uses **uv** (not pip/poetry). FFmpeg must be on `PATH`.

```bash
uv sync                      # install runtime deps
uv sync --extra dev          # add pytest, pytest-asyncio, httpx (needed for tests)
uv sync --extra ocr          # add PaddleOCR (paddlepaddle/paddleocr/paddlex) for hard-subtitle detection
# NOTE: `uv sync --extra X` syncs the env to *exactly* X, dropping others — use
# `uv sync --extra dev --extra ocr` to keep tests + OCR together.

uv run pytest                # run all Python tests (testpaths=tests)
uv run pytest tests/test_orchestration.py            # one file
uv run pytest tests/test_cli.py::test_name -q        # one test
uv run pytest -k atomic_tools                         # by keyword

uv run translip <subcommand> ...   # CLI (see "Pipeline stages" below)
uv run translip --help
```

Frontend (Node + npm, in `frontend/`):

```bash
npm install
npm run dev      # Vite dev server on :5173, proxies /api -> 127.0.0.1:8765
npm run build    # tsc -b (full typecheck) then vite build -> frontend/dist
npm run lint     # ESLint over .ts/.tsx
npm run test     # Vitest unit/component tests (jsdom)
```

End-to-end Playwright tests live at the repo root in `tests/e2e/*.spec.ts` (config: `playwright.config.ts`, baseURL `http://127.0.0.1:5173`, `fullyParallel: false`). They drive the running dev stack, so start it first:

```bash
./scripts/dev.sh start    # boots API (uvicorn :8765) + web (:5173) detached; logs/pids in .dev-runtime/
./scripts/dev.sh status   # / stop / restart
npx playwright test       # then run e2e
```

Serve the built UI from the backend (production-style): `npm run build` then `uv run translip-server` — if `frontend/dist` exists the API mounts it and serves everything from `:8765`.

There is **no Python linter/formatter configured** (no ruff/black config); match surrounding style.

## Architecture

### The pipeline is a cache-aware DAG of subprocesses

The core insight: each pipeline stage is an **independent CLI command** that reads input files (mostly JSON + audio) and writes output files + a `*-manifest.json`. The orchestrator (`src/translip/orchestration/`) is a thin conductor that does **not** contain task logic — it resolves a node DAG, checks a cache, and shells out to those same CLI commands in **isolated subprocesses** (so heavy ML models are freed on exit and crashes don't poison the orchestrator).

- `nodes.py` — static node registry (name, group, `dependencies`, `sequence_hint`).
- `templates.py` — workflow templates select which nodes run: `asr-dub-basic`, `asr-dub+ocr-subs`, `asr-dub+ocr-subs+erase`.
- `graph.py` — `resolve_template_plan()` collects transitive deps + topologically sorts.
- `commands.py` — builds the `uv run translip ...` argv for each node.
- `subprocess_runner.py` — `run_stage_command()` streams logs to `<output_root>/logs/<node>.log`, supports SIGTERM/SIGKILL cancellation.
- `cache.py` — per-stage `StageCacheSpec`; cache key = SHA256 of stage-specific params + upstream file fingerprints. A node is a cache **hit** only if its manifest exists, status is `succeeded`, all artifacts exist, and the cache key is unchanged. This is why changing a backend/model flag forces selective recompute.
- `runner.py` — `run_pipeline()` ties it together and writes `pipeline-manifest.json` / `pipeline-report.json` / `pipeline-status.json`.
- `monitor.py` — overall progress = weighted sum of per-stage progress (weights in `stages.py`), written to the status JSON.

`run-pipeline` defaults to running `separation`→`render`; `export-video` (delivery) is a separate final step. Individual CLI subcommands and `run-pipeline` are two entry points to the **same** stage code.

### Pipeline stages (CLI ↔ module)

| Node | CLI subcommand | Module (`src/translip/`) | Backends / notes |
| --- | --- | --- | --- |
| separation | `run` | `models/` + `pipeline/` | demucs (music) / cdx23 (dialogue). `--enhance-voice` is a **no-op passthrough placeholder** (`NoOpVoiceEnhancer`) — no real denoise/dereverb backend yet |
| transcription | `transcribe` | `transcription/` | ASR: faster-whisper, funasr · diarization: ECAPA, pyannote |
| speaker-registry | `build-speaker-registry` | `speakers/` | speaker profiles/embeddings + cross-task registry |
| translation | `translate-script` | `translation/` | `local-m2m100`, `deepseek` (needs `DEEPSEEK_API_KEY`) |
| synthesis | `synthesize-speaker` | `dubbing/` | TTS: `moss-tts-nano-onnx` (default), `qwen3tts`, `voxcpm2` |
| render | `render-dub` | `rendering/` | timeline fit (atempo/rubberband) + sidechain mix |
| delivery | `export-video` | `delivery/` | ffmpeg mux + optional burned subtitles |

Adjacent (not always in the basic template): `repair/` (`plan-dub-repair` / `run-dub-repair` — re-synthesize failed dub segments), `subtitles/` (preview/burn ASS), `ocr/` (in-tree PaddleOCR hard-subtitle detection — see below), `erase/` (in-tree subtitle inpainting — see below), `quality/` (dub benchmark, audio signature), `characters/` (character→speaker ledger), `speaker_review/` (diagnostics + manual decision application), and OCR/subtitle-erase bridge nodes used by the `+ocr-subs`/`+erase` templates.

#### OCR hard-subtitle detection (`src/translip/ocr/`)

The `ocr-detect` node is **fully in-tree** — a vendored PaddleOCR pipeline (`translip.ocr.SubtitleService`, ported from media-sense's `modules/paddle_ocr`), not an external sibling project. `orchestration/ocr_bridge.py` runs it as an isolated subprocess via `python -m translip.ocr.extract`, which writes the same artifact contract downstream consumers expect (`ocr-detect/{ocr_events.json, detection.json, ocr_subtitles.source.srt, ocr-detect-manifest.json}`). PaddleOCR is the optional `ocr` extra and is imported lazily, so the base install and the rest of the pipeline are unaffected when it's absent (you get a clear ImportError only when detection actually runs). The atomic `subtitle-detect` tool uses the same module.

#### Subtitle erase (`src/translip/erase/`)

**Subtitle *erase* is also fully in-tree** — `orchestration/erase_bridge.py` runs `python -m translip.erase.extract` (vendored `translip.erase`), no external sibling project. It ports the inpainting core of [`video-subtitle-remover`](https://github.com/YaoFANGUK/video-subtitle-remover) (Apache-2.0) with two backends selected by `erase_backend`: **`sttn`** (default — STTN spatial-temporal transformer video inpainting, temporal coherence) and **`lama`** (big-LaMa single-frame, sharpest for stills/animation). It reuses the OCR `detection.json` to build per-frame masks (no second detector), inpaints only subtitle frames, and re-muxes the original audio, writing `subtitle-erase/{clean_video.mp4, erase-report.json, subtitle-erase-manifest.json}` (the contract `delivery/`, `task_read_model`, and the runner cache spec depend on). The mask coordinate/order quirks and color handling are documented in the module. torch is base-transitive; the cv2/pydantic-settings stack is the optional **`erase`** extra, imported lazily (clear ImportError only when erase runs). Model weights (`sttn.pth` ~63 MB, `big-lama.pt` ~196 MB) auto-download from the upstream GitHub tree to `<cache>/erase_models` on first use, sha256-verified (`SUBTITLE_ERASE_MODELS_DIR` / `SUBTITLE_ERASE_LOCAL_MODELS_ONLY` override). The atomic `subtitle-erase` tool uses the same module via `balanced`=sttn / `quality`=lama presets. Erasure coverage is bounded by OCR box accuracy — the inpainter removes exactly what the detection masks.

#### Video content perception (`src/translip/vision/`)

**In-tree Qwen3-VL video analysis** (Phases 1–2 of `docs/qwen3-vl-integration-plan.md`: atomic tool + CLI + the optional `visual-context` pipeline node; erase-qc/ocr-classify integration is Phase 3, not yet built). The `asr-dub+visual` template inserts `visual-context` (optional, group `visual-perception`, after speaker-registry) which runs scene-context over the *effective* transcription segments; translation picks it up by **time-overlap matching** (`translation/visual_context.py` — never by unit numbering, which is process-local on both sides) and prepends `[画面] <scene>` to each unit's `context` channel (LLM-only by construction: m2m100 reads source_text only). Its cache key stores the **resolved** backend/model (cheap `resolve_backend_name()` probe, "auto" never goes in the key), and translation's key fingerprints `visual_context.json` so content changes cascade. visual-context path helpers live in `orchestration/commands.py` (vision_bridge imports commands; the reverse would be circular). `python -m translip.vision.extract` samples frames per analysis unit (ffmpeg, long edge 768px) and runs a local VLM, writing `{visual_context.json | erase_qc_report.json | ocr_events.classified.json | freeform_answer.json}` + `<task>-manifest.json`, with `__VISION_PROGRESS__` stdout lines. Two backends resolved by `vision_backend=auto|mlx|ollama`: **mlx** (Apple Silicon, `mlx-community/Qwen3-VL-4B-Instruct-4bit` via the optional **`vision`** extra) and **ollama** (HTTP, zero extra deps, default tag `qwen3-vl:4b-instruct` — never the bare `:4b` tag, which may resolve to the thinking variant). `backends.resolve_backend_name()` is intentionally cheap (find_spec + HTTP probe) so the orchestrator can put the *resolved* backend/model into cache keys later. `vision/config.py` is stdlib-only (NOT pydantic-settings — that ships only with extras, and the ollama path must work without any extra); `VISION_*` env vars are re-read per `load_settings()` call. Unit construction: segments-driven grouping or fixed-interval slicing — consumers match by **time overlap, never unit numbering** (sub-second interval tails are merged; frame extraction needs `-strict unofficial` for non-full-range YUV sources). Dependency landmines, documented in pyproject: mlx-vlm 0.3.x needs **torchvision** (Qwen3-VL AutoProcessor), and mlx-vlm's `opencv-python` requirement is globally excluded via `[tool.uv] override-dependencies` so it can't corrupt the ocr/erase stack's `opencv-contrib-python` (one cv2 distribution only). The `video-analyze` atomic tool and `translip analyze-video` CLI use the same module; `ToolSpec.heavy=True` tools (vision, erase, separation) additionally serialize on a single job-manager slot so two multi-GB models never run concurrently on a 16 GB host.

### Per-stage contract & types

Every stage module follows the same shape: a `Request` dataclass → `runner.py` entry function → `Result` exposing typed `Artifacts` (file paths) and a manifest. **All inter-stage data flows through JSON files on disk**, not in-memory objects. The central type system lives in `src/translip/types.py` (~29KB: enums for mode/quality/device/backends/`PipelineStageName`, all Request/Result/Artifacts dataclasses, and the monolithic `PipelineRequest`). Defaults live in `config.py` (env-overridable). When adding/altering a stage, keep the Request→Result→Artifacts+manifest pattern and update the cache spec in `orchestration/`.

### Server (`src/translip/server/`)

FastAPI app (`app.py`, run via `translip-server` or `uvicorn translip.server.app:app`) with routers under `routes/`: tasks, progress (SSE), config/presets, delivery, dubbing-editor, speaker-review (+ global personas), works/work-types, system, artifacts, atomic-tools. State is **SQLite via SQLModel** (`database.py`, WAL mode, runtime column migrations in `_ensure_columns`). `task_manager.create_task()` writes a DB row then spawns two daemon threads: one runs `orchestration.run_pipeline()`, the other polls `pipeline-status.json` every ~3s and syncs progress into the DB. The app serves `frontend/dist` as an SPA fallback when present.

**Atomic tools** (`server/atomic_tools/`) are a separate, orthogonal system from the pipeline: standalone single-purpose jobs (separation, transcription, translation, tts, mixing, muxing, subtitle-detect/erase, probe…). `registry.py` maps `tool_id → ToolSpec + adapter`; adapters in `adapters/` implement `validate_params` + `run(params, input_dir, output_dir, on_progress)`; `job_manager.py` handles uploads, a bounded concurrent job queue, cancellation via `threading.Event`, artifact registration, and cleanup. Jobs/uploads persist under `CACHE_ROOT/atomic-tools/`.

### Frontend (`frontend/src/`)

React 19 + TypeScript + Vite 8 + Tailwind 4. **Server state via TanStack React Query**, client/UI state via **Zustand** (`stores/`), routing via React Router 7. Axios client (`api/client.ts`) uses an empty baseURL + relative `/api/...` paths (works in dev via the Vite proxy and in prod when served by the backend). Layered structure: `api/` (typed clients, mirror backend Pydantic models) · `pages/` (route components) · `components/` (feature-grouped) · `hooks/` · `lib/` · `i18n/`. **i18n is first-class** — locales `zh-CN` (default) and `en-US` in `i18n/messages.ts`; use the `useI18n()` hook rather than hardcoding strings (recent work aligned UI terminology with backend stage/status labels). Tests are Vitest colocated in `__tests__/`; `tsc -b` chains `tsconfig.app.json` (app) + `tsconfig.node.json` (vite config).

### `video_voice_separate` package

`src/video_voice_separate/` is a thin **legacy alias** that re-exports from `translip` (`SeparationRequest/Result`, `separate_file`, `cli.main`). Real implementation lives in `translip`; don't add new logic there.

### `translip_lab` evaluation lab (`src/translip_lab/`, optional extra `lab`)

A **loosely-coupled** harness that benchmarks existing translip capabilities against ground-truth datasets (CER/DER/SI-SDR/PSNR-SSIM/OCR-text-F1). **One-way dependency rule: `translip_lab` imports `translip`; translip never imports the lab.** Integration is via the stable CLI/JSON contract (subprocess, like the orchestrator) plus a couple of pure helper imports — deleting `src/translip_lab/` + the one "Testing Lab" sidebar link leaves translip untouched. Entry points `translip-lab` (CLI: `doctor`/`run`/`report`/`compare`) and `translip-lab-server` (standalone dashboard on `:8799`, its own origin; the main UI only links to it). Suites in `translip_lab/suites/*.toml` declare dataset+scenarios+config (+ `[[arms]]` for config sweeps). Data/runs default to `/Volumes/EXT/translip-lab` (`TRANSLIP_LAB_HOME`). The engine runs on base deps (numpy/scipy/soundfile) + ffmpeg + stdlib; only Pillow is added by the `lab` extra. See `src/translip_lab/README.md`. Caveat: the lab cache is keyed by config+input fingerprints, **not code** — re-run with `--no-cache` after changing scoring logic.

## Key paths & env

- `TRANSLIP_CACHE_DIR` (default `~/.cache/translip`) — model cache, pipeline output (`output-pipeline/<task_id>/`), atomic-tools storage.
- `TRANSLIP_DB_PATH` (default `<cache>/data.db`) — server SQLite DB.
- `DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL` — `deepseek` translation backend, transcript-correction LLM arbitration, and translation quality judge (default model `deepseek-v4-pro`).
- `MOSS_TTS_NANO_CLI` / `MOSS_TTS_NANO_MODEL_DIR` / `MOSS_TTS_NANO_CPU_THREADS` — the default TTS backend shells out to the external `moss-tts-nano` CLI; it must be installed separately or synthesis fails with a clear dependency error.
- `VOXCPM_*` — `voxcpm2` backend (CPU by default on Apple Silicon; `VOXCPM_ALLOW_MPS=1` to try MPS).
- `PADDLEOCR_MODELS_BASE_DIR` (default `<cache>/paddleocr_models`) — local PP-OCRv5 mobile det/rec + textline-orientation weights for in-tree OCR, laid out per-platform (`macos-arm64/`, `linux-x86_64/`). Other `PADDLEOCR_*` / `SUBTITLE_*` knobs in `src/translip/ocr/config.py` are env-overridable. Models load locally — no remote download at runtime.
- `SUBTITLE_ERASE_MODELS_DIR` (default `<cache>/erase_models`) — cache for the subtitle-erase inpainting weights (`sttn.pth`, `big-lama.pt`), auto-downloaded + sha256-verified on first use. `SUBTITLE_ERASE_LOCAL_MODELS_ONLY=1` forbids downloads (weights must be pre-placed). Other `ERASE_*` defaults (backend/device/mask/STTN sampling) live in `src/translip/erase/config.py`.
- `VISION_*` (see `src/translip/vision/config.py`) — video perception: `VISION_BACKEND` (auto/mlx/ollama), `VISION_MODEL`, `VISION_OLLAMA_MODEL`/`VISION_OLLAMA_HOST`, `VISION_HF_CACHE` (default `<cache>/vision_models/hf`, injected as `HF_HUB_CACHE` — deliberately not `HF_HOME`), `VISION_LOCAL_MODELS_ONLY`, frames/token/temperature knobs, `VISION_TIMEOUT_SEC` (ollama HTTP only; mlx runs in-process and is killed via subprocess cancellation instead).

Pipeline outputs are conventionally laid out as `<root>/{separation,transcription,...,delivery}/<input-stem>/...` with top-level `pipeline-{manifest,report,status}.json`. See `config.py` for the full default set.
