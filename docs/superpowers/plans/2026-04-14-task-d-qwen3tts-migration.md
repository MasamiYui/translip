# Task D Qwen3-TTS Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Task D's current F5/OpenVoice-based dubbing path with a single Qwen3-TTS implementation and remove the obsolete TTS backend code and dependencies.

**Architecture:** Keep Task B, Task C, and Task E interfaces unchanged, but swap the Task D synthesis backend to a new `qwen_tts_backend.py` implementation. The runner, CLI, and typing layers will be narrowed to one supported backend so the codebase stays simple and the old TTS integrations can be deleted cleanly.

**Tech Stack:** Python 3.11, `qwen-tts`, `faster-whisper`, `speechbrain`, `pytest`

---

### Task 1: Lock The New Public Contract

**Files:**
- Modify: `tests/test_dubbing.py`
- Modify: `tests/test_cli.py`
- Test: `tests/test_dubbing.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test for the new default backend**

Add assertions that `DubbingRequest` defaults to `qwen3tts` and that the CLI parser only accepts `qwen3tts` for `synthesize-speaker`.

- [ ] **Step 2: Run the targeted tests and verify failure**

Run: `uv run pytest tests/test_dubbing.py tests/test_cli.py -q`
Expected: FAIL because the code still defaults to `f5tts` and still exposes `openvoice`.

- [ ] **Step 3: Make the minimal typing and CLI changes**

Update `src/video_voice_separate/types.py`, `src/video_voice_separate/config.py`, and `src/video_voice_separate/cli.py` so Task D only exposes `qwen3tts`.

- [ ] **Step 4: Re-run the targeted tests**

Run: `uv run pytest tests/test_dubbing.py tests/test_cli.py -q`
Expected: PASS for the contract changes, with later failures reserved for the missing backend implementation.

- [ ] **Step 5: Commit**

```bash
git add tests/test_dubbing.py tests/test_cli.py src/video_voice_separate/types.py src/video_voice_separate/config.py src/video_voice_separate/cli.py
git commit -m "test: lock Task D to qwen3tts"
```

### Task 2: Add The Qwen3-TTS Backend

**Files:**
- Create: `src/video_voice_separate/dubbing/qwen_tts_backend.py`
- Modify: `tests/test_dubbing.py`
- Test: `tests/test_dubbing.py`

- [ ] **Step 1: Write the failing backend unit test**

Add a test that monkeypatches the Qwen model loader and verifies the backend calls the clone API with `ref_audio`, `ref_text`, and `target_text`, then writes a wav to the requested output path.

- [ ] **Step 2: Run the test and verify failure**

Run: `uv run pytest tests/test_dubbing.py -q`
Expected: FAIL because `qwen_tts_backend.py` does not exist.

- [ ] **Step 3: Implement the minimal backend**

Create `src/video_voice_separate/dubbing/qwen_tts_backend.py` with:
- lazy model loading
- device resolution
- a single `QwenTTSBackend.synthesize(...)`
- generated duration metadata

- [ ] **Step 4: Re-run the backend tests**

Run: `uv run pytest tests/test_dubbing.py -q`
Expected: PASS for backend-specific tests.

- [ ] **Step 5: Commit**

```bash
git add tests/test_dubbing.py src/video_voice_separate/dubbing/qwen_tts_backend.py
git commit -m "feat: add qwen3tts dubbing backend"
```

### Task 3: Migrate The Task D Runner

**Files:**
- Modify: `src/video_voice_separate/dubbing/runner.py`
- Modify: `src/video_voice_separate/dubbing/__init__.py`
- Delete: `src/video_voice_separate/dubbing/f5tts_backend.py`
- Delete: `src/video_voice_separate/dubbing/openvoice_backend.py`
- Test: `tests/test_dubbing.py`

- [ ] **Step 1: Write the failing runner test**

Extend `tests/test_dubbing.py` so `synthesize_speaker(...)` without `backend_override` constructs `QwenTTSBackend`, and so unsupported backend names fail fast.

- [ ] **Step 2: Run the test and verify failure**

Run: `uv run pytest tests/test_dubbing.py -q`
Expected: FAIL because the runner still imports and selects `F5TTSBackend` / `OpenVoiceBackend`.

- [ ] **Step 3: Implement the runner migration**

Update `src/video_voice_separate/dubbing/runner.py` to:
- import `QwenTTSBackend`
- route `_build_backend(...)` only to Qwen
- remove legacy imports

Delete the old backend modules after the runner no longer references them.

- [ ] **Step 4: Re-run the tests**

Run: `uv run pytest tests/test_dubbing.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/video_voice_separate/dubbing/runner.py src/video_voice_separate/dubbing/__init__.py src/video_voice_separate/dubbing/qwen_tts_backend.py tests/test_dubbing.py
git rm src/video_voice_separate/dubbing/f5tts_backend.py src/video_voice_separate/dubbing/openvoice_backend.py
git commit -m "refactor: migrate task d runner to qwen3tts"
```

### Task 4: Remove Old Dependencies And Surface Area

**Files:**
- Modify: `pyproject.toml`
- Modify: `README.md`
- Modify: `docs/task-d-test-report.md`
- Modify: `docs/task-e-test-report.md`
- Modify: `docs/speaker-aware-dubbing-plan.md`

- [ ] **Step 1: Write the failing dependency/documentation assertions**

Add or adjust tests if needed so CLI/help text and public defaults no longer mention `f5tts` or `openvoice`.

- [ ] **Step 2: Run the focused tests**

Run: `uv run pytest tests/test_cli.py -q`
Expected: FAIL if legacy backend names still appear.

- [ ] **Step 3: Remove obsolete dependency and doc references**

Update:
- `pyproject.toml` to remove `f5-tts`
- `README.md` and docs to use `qwen3tts`
- any sample commands and examples still referencing the old backends

- [ ] **Step 4: Re-run the focused tests**

Run: `uv run pytest tests/test_cli.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml README.md docs/task-d-test-report.md docs/task-e-test-report.md docs/speaker-aware-dubbing-plan.md tests/test_cli.py
git commit -m "chore: remove legacy task d backend references"
```

### Task 5: End-To-End Verification

**Files:**
- Modify if needed: `scripts/run_task_a_to_d.py`
- Modify if needed: `scripts/run_task_a_to_e.py`
- Test: `tests/test_dubbing.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Run the full unit test suite**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 2: Run a Task D smoke test**

Run a single-speaker, small-segment Task D invocation against existing Task B/C artifacts to confirm the Qwen backend works locally.

- [ ] **Step 3: Run the full `test_video` pipeline**

Run: `uv run python scripts/run_task_a_to_e.py --input ./test_video/我在迪拜等你.mp4 --output-root ./tmp/e2e-task-a-to-e-qwen --target-lang en --translation-backend local-m2m100 --tts-backend qwen3tts --device auto --speaker-limit 0 --segments-per-speaker 0 --fit-policy high_quality --max-compress-ratio 1.7`

Expected:
- Task A-E all complete
- Task E writes `dub_voice.en.wav`, `preview_mix.en.wav`, `timeline.en.json`, `mix_report.en.json`, `task-e-manifest.json`

- [ ] **Step 4: Fix any regressions and re-run until green**

If smoke or full pipeline fails, patch only the identified root cause, then re-run the specific failing command followed by the full pipeline again.

- [ ] **Step 5: Commit**

```bash
git add scripts/run_task_a_to_d.py scripts/run_task_a_to_e.py
git commit -m "test: verify qwen3tts task d pipeline"
```
