# Auto Dub Repair Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make failed dubbing segments repairable in the normal pipeline and prevent subtitle-window audio from being dropped by overlap resolution.

**Architecture:** Keep Task D reports as the source of generated candidates, add an optional repair loop before Task E, pass `selected_segments.<lang>.json` into `render-dub`, and update placement to layer short/subtitle-critical overlaps instead of skipping them. This produces immediate improvements while preserving existing reports and delivery artifacts.

**Tech Stack:** Python dataclasses, existing repair runner, existing render runner, pytest, Playwright CLI.

---

### Task 1: Overlap-Safe Placement

**Files:**
- Modify: `tests/test_rendering.py`
- Modify: `src/translip/rendering/runner.py`

- [ ] **Step 1: Write failing test**

Change the subtitle-window overlap test so the second subtitle-window segment is placed as `placed_overlap`, reports full subtitle coverage, and does not increment audible coverage failures.

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
uv run pytest tests/test_rendering.py::test_render_dub_counts_skipped_subtitle_window_as_uncovered -q
```

Expected before implementation: failure because old code returns `skipped_overlap`.

- [ ] **Step 3: Implement overlap placement**

Add:

- `TimelineItem.mix_gain_db`
- rendered status helper treating `placed` and `placed_overlap` as audible
- overlap layering rule for subtitle-window or short-dialogue overlaps
- gain attenuation when layering failed/review overlap candidates

- [ ] **Step 4: Verify**

Run:

```bash
uv run pytest tests/test_rendering.py -q
```

Expected: all rendering tests pass after updated expectations.

### Task 2: Pipeline Repair Loop

**Files:**
- Modify: `tests/test_orchestration.py`
- Modify: `src/translip/types.py`
- Modify: `src/translip/orchestration/request.py`
- Modify: `src/translip/orchestration/commands.py`
- Modify: `src/translip/orchestration/runner.py`
- Modify: `src/translip/server/schemas.py`
- Modify: `src/translip/server/task_manager.py`
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Write failing tests**

Add tests that assert:

- pipeline request maps `dub_repair_enabled`, `dub_repair_max_items`, `dub_repair_attempts_per_item`
- `build_task_e_command(..., selected_segments_path=...)` includes `--selected-segments`

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_orchestration.py::test_build_pipeline_request_maps_dub_repair_config tests/test_orchestration.py::test_task_e_command_passes_selected_repair_segments -q
```

Expected before implementation: failure because fields/signature do not exist.

- [ ] **Step 3: Implement config and command plumbing**

Add `PipelineRequest` fields:

```python
dub_repair_enabled: bool = False
dub_repair_backends: list[str] | None = None
dub_repair_max_items: int = 12
dub_repair_attempts_per_item: int = 3
dub_repair_include_risk: bool = False
```

Map the same fields from CLI config/server task config/frontend type.

- [ ] **Step 4: Implement repair execution before Task E**

When enabled:

1. Read Task D reports from `task-d-stage-manifest.json`.
2. Run `plan_dub_repair` into `task-d/voice/repair-plan`.
3. Run `run_dub_repair` into `task-d/voice/repair-run`.
4. If `selected_segments.<lang>.json` exists, pass it to `render-dub`.
5. Record repair artifacts in Task E manifest/report through existing `selected_segments_path`.

- [ ] **Step 5: Verify**

Run:

```bash
uv run pytest tests/test_orchestration.py tests/test_rendering.py tests/test_repair.py -q
```

Expected: pass.

### Task 3: Documentation And Playwright Full Pipeline

**Files:**
- Create: `docs/superpowers/reports/2026-04-30-dubai-auto-repair-playwright-execution-report.zh-CN.md`

- [ ] **Step 1: Run targeted unit tests**

Run:

```bash
uv run pytest tests/test_rendering.py tests/test_orchestration.py tests/test_repair.py tests/test_delivery.py tests/test_dubbing.py -q
```

- [ ] **Step 2: Run frontend verification**

Run:

```bash
npm run build
```

- [ ] **Step 3: Run full Playwright pipeline**

Use Playwright CLI against the local frontend/API to create a task for:

```text
/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/test_video/我在迪拜等你.mp4
```

Config requirements:

- `template=asr-dub+ocr-subs`
- `run_to_stage=task-g`
- `subtitle_mode=bilingual`
- `subtitle_render_source=asr`
- `dub_repair_enabled=true`
- `dub_repair_max_items=12`
- `dub_repair_attempts_per_item=3`

- [ ] **Step 4: Inspect outputs**

Compare the new task against `task-20260430-015606`:

- `audible_coverage.failed_count`
- `skipped_count`
- `skip_reason_counts.skipped_overlap`
- repair `selected_count`
- final preview path

- [ ] **Step 5: Write execution report**

The report must state:

- what improved
- what did not improve
- final artifact paths
- whether the output is good enough for user inspection
- next iteration if still below target
