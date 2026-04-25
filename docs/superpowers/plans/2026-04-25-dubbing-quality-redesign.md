# Dubbing Quality Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the observed dubbing-missing cases by carrying OCR-derived timing into rendering, measuring audible subtitle-window coverage, and blocking misleading final delivery when quality is not acceptable.

**Architecture:** Keep the existing A-G pipeline, but add a timing side-channel from ASR/OCR correction into Task E. Task E will prefer `dubbing_window` over raw ASR start/end, report coverage metrics, and use those metrics in content quality gating. Task G will avoid stale/misleading final artifacts when content quality is not publishable.

**Tech Stack:** Python dataclasses and JSON artifacts, existing pytest suite, ffmpeg utilities, Playwright CLI for browser workflow verification.

---

### Task 1: Persist OCR Timing In Correction Artifacts

**Files:**
- Modify: `src/translip/transcription/ocr_correction.py`
- Test: `tests/test_asr_ocr_correction.py`

- [ ] **Step 1: Write failing test**

Add a test where an ASR segment starts much earlier than the matched OCR event. Assert the corrected segment contains `timing.ocr_window`, `timing.dubbing_window`, and `timing.warnings`.

- [ ] **Step 2: Verify red**

Run: `pytest tests/test_asr_ocr_correction.py::test_correction_persists_ocr_dubbing_window_for_late_subtitle -q`

Expected: FAIL because `timing` is not present.

- [ ] **Step 3: Implement timing metadata**

When OCR candidates are attached to a segment, compute `ocr_window` from min OCR start and max OCR end. If OCR starts more than 1 second after ASR start, set `dubbing_window.start` near OCR start with a small lead. Preserve ASR end as a safe maximum when it is later than OCR end.

- [ ] **Step 4: Verify green**

Run the same pytest command. Expected: PASS.

### Task 2: Render From Dubbing Windows

**Files:**
- Modify: `src/translip/rendering/runner.py`
- Test: `tests/test_rendering.py`

- [ ] **Step 1: Write failing test**

Add a Task E test with corrected segments containing `timing.dubbing_window.start = 16.0` while ASR start is `13.0`. Assert `placement_start` uses `16.0`, not `13.0`, and that subtitle-window coverage is high.

- [ ] **Step 2: Verify red**

Run: `pytest tests/test_rendering.py::test_render_dub_uses_dubbing_window_from_corrected_segments -q`

Expected: FAIL because Task E currently anchors on raw `start`.

- [ ] **Step 3: Implement dubbing window loading**

Extend `TimelineItem` with `dubbing_start`, `dubbing_end`, `subtitle_start`, `subtitle_end`. Load these from `anchor["timing"]` when available. Use `dubbing_start` and `dubbing_end` for fit source duration and placement.

- [ ] **Step 4: Verify green**

Run the same pytest command. Expected: PASS.

### Task 3: Add Audible Coverage QA

**Files:**
- Modify: `src/translip/rendering/runner.py`
- Modify: `src/translip/rendering/export.py`
- Test: `tests/test_rendering.py`

- [ ] **Step 1: Write failing tests**

Add tests for a segment whose fitted audio ends before `subtitle_window.start`. Assert the report includes `subtitle_overlap_coverage = 0.0`, a `subtitle_window_not_covered` note, and content quality reason `audible_coverage_failed`.

- [ ] **Step 2: Verify red**

Run: `pytest tests/test_rendering.py::test_mix_report_flags_uncovered_subtitle_window -q`

Expected: FAIL because coverage metrics are missing.

- [ ] **Step 3: Implement coverage metrics**

Compute overlap between `[placement_start, placement_end]` and `[subtitle_start, subtitle_end]`. Store per-segment `subtitle_overlap_coverage`, aggregate average/minimum coverage, and mark content quality failed when any subtitle-bearing segment has zero coverage.

- [ ] **Step 4: Verify green**

Run the same pytest command. Expected: PASS.

### Task 4: Prevent Misleading Delivery

**Files:**
- Modify: `src/translip/delivery/runner.py`
- Test: `tests/test_delivery.py`

- [ ] **Step 1: Write failing test**

Add a delivery test with `content_quality.status = review_required` and a stale `final-dub/final_dub.en.mp4` already present. Assert the new delivery manifest does not advertise that stale file and removes or ignores it.

- [ ] **Step 2: Verify red**

Run: `pytest tests/test_delivery.py::test_delivery_does_not_advertise_stale_final_dub_when_dub_export_disabled -q`

Expected: FAIL if stale files remain advertised or present as current output.

- [ ] **Step 3: Implement stale artifact cleanup**

At Task G start, remove outputs that are not requested for the current run. Ensure manifest artifacts only list files generated in this invocation.

- [ ] **Step 4: Verify green**

Run the same pytest command. Expected: PASS.

### Task 5: Full Verification

**Files:**
- No direct code changes.

- [ ] **Step 1: Run targeted unit suite**

Run: `pytest tests/test_asr_ocr_correction.py tests/test_rendering.py tests/test_delivery.py tests/test_dubbing.py tests/test_orchestration.py tests/test_cli.py -q`

- [ ] **Step 2: Run full workflow on sample video**

Run the pipeline with `/Users/masamiyui/Downloads/哪吒预告片.mp4` into a fresh output root and inspect `mix_report.en.json`.

- [ ] **Step 3: Run browser workflow with Playwright**

Start the local app, open it with Playwright CLI, create or inspect the workflow for the sample video, and capture a screenshot/artifact under `output/playwright/`.

- [ ] **Step 4: Iterate on failures**

For any failed unit test, pipeline QA metric, or browser workflow error, debug root cause, add/adjust tests, fix, and rerun from the failing verification point.
