# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`translip` is a local-first, multi-speaker-aware video dubbing pipeline: audio separation → speaker-attributed transcription → translation → single-speaker TTS → timeline re-fit/mix → video delivery. It ships as a Python CLI/library (`src/translip`) plus a FastAPI control plane and a React management UI (`frontend/`). Status is Beta/early-access. The README (`README.md` / `README.en.md`) is the canonical user-facing doc and is more detailed than this file on CLI flags.

## Commands

Backend uses **uv** (not pip/poetry). FFmpeg must be on `PATH`.

```bash
uv sync                      # install runtime deps
uv sync --extra dev          # add pytest, pytest-asyncio, httpx (needed for tests)

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

`run-pipeline` defaults to running `stage1`→`task-e`; `export-video` (task-g) is a separate final step. Individual CLI subcommands and `run-pipeline` are two entry points to the **same** stage code.

### Pipeline stages (CLI ↔ module)

| Node | CLI subcommand | Module (`src/translip/`) | Backends / notes |
| --- | --- | --- | --- |
| stage1 | `run` | `models/` + `pipeline/` | demucs (music) / cdx23 (dialogue) / clearervoice |
| task-a | `transcribe` | `transcription/` | ASR: faster-whisper, funasr · diarization: ECAPA, pyannote |
| task-b | `build-speaker-registry` | `speakers/` | speaker profiles/embeddings + cross-task registry |
| task-c | `translate-script` | `translation/` | `local-m2m100`, `siliconflow` (needs `SILICONFLOW_API_KEY`) |
| task-d | `synthesize-speaker` | `dubbing/` | TTS: `moss-tts-nano-onnx` (default), `qwen3tts`, `voxcpm2` |
| task-e | `render-dub` | `rendering/` | timeline fit (atempo/rubberband) + sidechain mix |
| task-g | `export-video` | `delivery/` | ffmpeg mux + optional burned subtitles |

Adjacent (not always in the basic template): `repair/` (`plan-dub-repair` / `run-dub-repair` — re-synthesize failed dub segments), `subtitles/` (preview/burn ASS), `quality/` (dub benchmark, audio signature), `characters/` (character→speaker ledger), `speaker_review/` (diagnostics + manual decision application), and OCR/subtitle-erase bridge nodes used by the `+ocr-subs`/`+erase` templates.

### Per-stage contract & types

Every stage module follows the same shape: a `Request` dataclass → `runner.py` entry function → `Result` exposing typed `Artifacts` (file paths) and a manifest. **All inter-stage data flows through JSON files on disk**, not in-memory objects. The central type system lives in `src/translip/types.py` (~29KB: enums for mode/quality/device/backends/`PipelineStageName`, all Request/Result/Artifacts dataclasses, and the monolithic `PipelineRequest`). Defaults live in `config.py` (env-overridable). When adding/altering a stage, keep the Request→Result→Artifacts+manifest pattern and update the cache spec in `orchestration/`.

### Server (`src/translip/server/`)

FastAPI app (`app.py`, run via `translip-server` or `uvicorn translip.server.app:app`) with routers under `routes/`: tasks, progress (SSE), config/presets, delivery, dubbing-editor, speaker-review (+ global personas), works/work-types, system, artifacts, atomic-tools. State is **SQLite via SQLModel** (`database.py`, WAL mode, runtime column migrations in `_ensure_columns`). `task_manager.create_task()` writes a DB row then spawns two daemon threads: one runs `orchestration.run_pipeline()`, the other polls `pipeline-status.json` every ~3s and syncs progress into the DB. The app serves `frontend/dist` as an SPA fallback when present.

**Atomic tools** (`server/atomic_tools/`) are a separate, orthogonal system from the pipeline: standalone single-purpose jobs (separation, transcription, translation, tts, mixing, muxing, subtitle-detect/erase, probe…). `registry.py` maps `tool_id → ToolSpec + adapter`; adapters in `adapters/` implement `validate_params` + `run(params, input_dir, output_dir, on_progress)`; `job_manager.py` handles uploads, a bounded concurrent job queue, cancellation via `threading.Event`, artifact registration, and cleanup. Jobs/uploads persist under `CACHE_ROOT/atomic-tools/`.

### Frontend (`frontend/src/`)

React 19 + TypeScript + Vite 8 + Tailwind 4. **Server state via TanStack React Query**, client/UI state via **Zustand** (`stores/`), routing via React Router 7. Axios client (`api/client.ts`) uses an empty baseURL + relative `/api/...` paths (works in dev via the Vite proxy and in prod when served by the backend). Layered structure: `api/` (typed clients, mirror backend Pydantic models) · `pages/` (route components) · `components/` (feature-grouped) · `hooks/` · `lib/` · `i18n/`. **i18n is first-class** — locales `zh-CN` (default) and `en-US` in `i18n/messages.ts`; use the `useI18n()` hook rather than hardcoding strings (recent work aligned UI terminology with backend stage/status labels). Tests are Vitest colocated in `__tests__/`; `tsc -b` chains `tsconfig.app.json` (app) + `tsconfig.node.json` (vite config).

### `video_voice_separate` package

`src/video_voice_separate/` is a thin **legacy alias** that re-exports from `translip` (`SeparationRequest/Result`, `separate_file`, `cli.main`). Real implementation lives in `translip`; don't add new logic there.

## Key paths & env

- `TRANSLIP_CACHE_DIR` (default `~/.cache/translip`) — model cache, pipeline output (`output-pipeline/<task_id>/`), atomic-tools storage.
- `TRANSLIP_DB_PATH` (default `<cache>/data.db`) — server SQLite DB.
- `SILICONFLOW_API_KEY` / `SILICONFLOW_BASE_URL` / `SILICONFLOW_MODEL` — `siliconflow` translation backend.
- `MOSS_TTS_NANO_CLI` / `MOSS_TTS_NANO_MODEL_DIR` / `MOSS_TTS_NANO_CPU_THREADS` — the default TTS backend shells out to the external `moss-tts-nano` CLI; it must be installed separately or task-d fails with a clear dependency error.
- `VOXCPM_*` — `voxcpm2` backend (CPU by default on Apple Silicon; `VOXCPM_ALLOW_MPS=1` to try MPS).

Pipeline outputs are conventionally laid out as `<root>/{stage1,task-a,...,task-g}/<input-stem>/...` with top-level `pipeline-{manifest,report,status}.json`. See `config.py` for the full default set.
