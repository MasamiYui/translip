# Dubbing Benchmark Character Tournament Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Benchmark v0, Character Ledger v1, and TTS/VC Tournament v1 for movie/TV dubbing quality iteration.

**Architecture:** Add focused Python modules for audio voice signatures, character ledger generation, benchmark reporting, and repair tournament scoring. Wire them into Task E around the existing repair/render path, then expose the artifacts through the existing dubbing review API and drawer.

**Tech Stack:** Python dataclasses, NumPy/SoundFile audio analysis, existing repair/render orchestration, FastAPI route aggregation, React/TypeScript dubbing review drawer, pytest, Playwright CLI.

---

### Task 1: Character Ledger v1

**Files:**
- Create: `src/translip/quality/audio_signature.py`
- Create: `src/translip/characters/__init__.py`
- Create: `src/translip/characters/ledger.py`
- Test: `tests/test_character_ledger.py`

- [x] Write failing tests for pitch class and ledger risk output.
- [x] Implement lightweight pitch/RMS/duration signature extraction.
- [x] Implement character ledger writer with JSON, Markdown, and manifest artifacts.
- [x] Verify `uv run pytest tests/test_character_ledger.py -q`.

### Task 2: Tournament Scoring

**Files:**
- Modify: `src/translip/repair/executor.py`
- Modify: `src/translip/cli.py`
- Test: `tests/test_repair.py`

- [x] Write failing test showing a pitch-mismatched candidate is rejected when a ledger is provided.
- [x] Add `character_ledger_path` to `RepairRunRequest`.
- [x] Add voice consistency metrics to each repair attempt.
- [x] Fold voice consistency into strict acceptance and attempt score.
- [x] Verify `uv run pytest tests/test_repair.py -q`.

### Task 3: Benchmark v0

**Files:**
- Create: `src/translip/quality/__init__.py`
- Create: `src/translip/quality/dub_benchmark.py`
- Modify: `src/translip/cli.py`
- Test: `tests/test_dub_benchmark.py`

- [x] Write failing test for benchmark JSON summary and status.
- [x] Implement benchmark builder from mix report, ledger, and repair artifacts.
- [x] Add CLI command `benchmark-dub`.
- [x] Verify `uv run pytest tests/test_dub_benchmark.py -q`.

### Task 4: Pipeline Integration

**Files:**
- Modify: `src/translip/orchestration/commands.py`
- Modify: `src/translip/orchestration/runner.py`
- Test: `tests/test_orchestration.py`

- [x] Write failing test proving Task E invokes ledger and benchmark builders.
- [x] Generate character ledger before repair.
- [x] Pass ledger path into repair run.
- [x] Generate benchmark report after Task E render.
- [x] Add artifacts to Task E stage result.
- [x] Verify `uv run pytest tests/test_orchestration.py -q`.

### Task 5: Dubbing Review QA Dashboard

**Files:**
- Modify: `src/translip/server/routes/dubbing_review.py`
- Modify: `tests/test_dubbing_review_routes.py`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/components/dubbing-review/DubbingReviewDrawer.tsx`

- [x] Write failing API route test for `quality_benchmark` and `characters`.
- [x] Aggregate benchmark and ledger artifacts in `/dubbing-review`.
- [x] Add TypeScript types for benchmark and characters.
- [x] Add a quality overview tab to the drawer.
- [x] Verify backend route test and frontend build.

### Task 6: Full Verification

**Files:**
- Create: `docs/superpowers/reports/2026-04-30-dubbing-benchmark-character-tournament-execution-report.zh-CN.md`

- [ ] Run focused pytest suites.
- [ ] Run frontend build.
- [ ] Restart local API service if needed.
- [ ] Use Playwright to run a full ASR + dubbing pipeline on the Dubai sample.
- [ ] Inspect benchmark, ledger, mix report, and final MP4 paths.
- [ ] If `audible_coverage.failed_count > 0` or benchmark artifacts are missing, fix and rerun.
- [ ] Save execution report with metrics and conclusions.
