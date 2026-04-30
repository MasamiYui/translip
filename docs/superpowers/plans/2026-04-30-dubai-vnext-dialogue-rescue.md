# Dubai vNext Dialogue Rescue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a parallel vNext dubbing experiment that improves the Dubai sample without destabilizing the existing baseline.

**Architecture:** Keep the existing baseline dub as the stable bed, then add only high-confidence SRT-only rescue clips in subtitle windows where the baseline voice is silent or weak. Generate a fresh Task E-like artifact set and export final preview/final dub videos for A/B/C comparison against baseline and SRT v2.

**Tech Stack:** Python, `soundfile`, `numpy`, project rendering helpers, existing Qwen3TTS segment candidates, ffmpeg via the existing `translip` CLI.

---

### Task 1: vNext Rescue Renderer

**Files:**
- Create: `.tmp/dubai_vnext_overlay_rescue.py`

- [ ] **Step 1: Implement the script**

Create a script that:
- parses `test_video/我的迪拜等你.srt`;
- loads `tmp/dubai-rerun-v3/task-e/voice/dub_voice.en.wav` as the stable base;
- loads `tmp/dubai-srt-v2/task-e/voice/mix_report.en.json` as the rescue candidate source;
- computes baseline RMS inside every SRT window;
- selects SRT-only candidates only when the baseline SRT window is weak and the candidate passes text/speaker quality thresholds;
- overlays accepted clips into a vNext dub voice waveform;
- writes `tmp/dubai-vnext-<profile>/task-e/voice/{dub_voice.en.wav,preview_mix.en.wav,preview_mix.en.mp3,mix_report.en.json,task-e-manifest.json}`.

- [ ] **Step 2: Run three quality profiles**

Run:

```bash
uv run python .tmp/dubai_vnext_overlay_rescue.py --profile conservative
uv run python .tmp/dubai_vnext_overlay_rescue.py --profile balanced
uv run python .tmp/dubai_vnext_overlay_rescue.py --profile aggressive
```

Expected: each command exits 0 and prints selected/rejected rescue counts plus audible coverage.

### Task 2: Export Best vNext Video

**Files:**
- Output only under `tmp/dubai-vnext-*`

- [ ] **Step 1: Pick best profile**

Pick the profile with the best tradeoff:
- `SRT window audible > -45 dBFS` improves over baseline;
- rejected low-quality short lines do not enter final audio;
- no overlap skips are introduced.

- [ ] **Step 2: Export preview/final dub**

Run:

```bash
uv run translip export-video \
  --input-video test_video/我在迪拜等你.mp4 \
  --task-e-dir tmp/dubai-vnext-balanced/task-e/voice \
  --output-dir tmp/dubai-vnext-balanced/task-g \
  --target-lang en \
  --export-preview \
  --export-dub \
  --subtitle-mode none
```

Expected: `tmp/dubai-vnext-balanced/task-g/final-preview/final_preview.en.mp4` and `tmp/dubai-vnext-balanced/task-g/final-dub/final_dub.en.mp4` exist.

### Task 3: Three-Way Comparison Report

**Files:**
- Create: `.tmp/compare_dubai_vnext.py`
- Create: `docs/superpowers/reports/2026-04-30-dubai-vnext-dialogue-rescue.zh-CN.md`

- [ ] **Step 1: Implement the comparison script**

Create a script that compares baseline, SRT v2, and vNext on:
- SRT-window audible coverage at `-45 dBFS`;
- placed/skipped counts;
- vNext rescue accept/reject counts;
- selected candidate quality distribution;
- final exported artifact paths.

- [ ] **Step 2: Run the comparison**

Run:

```bash
uv run python .tmp/compare_dubai_vnext.py --vnext-root tmp/dubai-vnext-balanced
```

Expected: the report is written and contains a clear conclusion about whether vNext is better than baseline and SRT v2.

### Task 4: Stop/Retry Decision

- [ ] **Step 1: Verify thresholds**

Pass criteria for the first vNext attempt:
- audible coverage must beat baseline;
- vNext must not introduce overlap skips;
- obviously bad SRT-only translations such as `乐乐 -> pleasure` must be rejected;
- final preview/final dub videos must export.

- [ ] **Step 2: Retry if needed**

If the first attempt fails, tighten or relax candidate thresholds and rerun Task 1-3. If overlay rescue cannot produce a meaningful gain, escalate to actual DialogueUnit-level TTS regeneration.
