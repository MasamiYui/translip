# Hard Subtitle Aware Bilingual Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让“双语审片”在检测到原片硬中文字幕时，导出前显式提示并默认推荐“保留原字 + 补英文”，同时把实际导出策略记录到任务详情中。

**Architecture:** 复用现有 OCR 检测产物，在任务读模型中生成硬字幕状态摘要；导出接口新增双语策略字段，由后端根据策略决定是否烧录中文字幕；任务详情页在双语审片导出前按检测结果展示策略选择 UI，并在导出完成后显示实际策略。

**Tech Stack:** FastAPI, SQLModel, Python delivery runner, React 19, TypeScript, Vitest, Playwright

---

### Task 1: Add failing backend tests for hard subtitle status and strategy-driven export

**Files:**
- Modify: `tests/test_delivery.py`
- Modify: `tests/test_server_routes.py`

- [ ] Add a failing test that verifies task/system read models can surface hard subtitle status from OCR artifacts.
- [ ] Run the targeted pytest command and confirm the new assertion fails for missing hard subtitle metadata.
- [ ] Add a failing test that verifies bilingual export with `preserve_hard_subtitles_add_english` does not resolve a Chinese subtitle path and behaves like English-only burn on the original video.
- [ ] Run the targeted pytest command and confirm the export test fails for unsupported strategy handling.

Run:

```bash
uv run pytest -q tests/test_delivery.py tests/test_server_routes.py
```

### Task 2: Implement backend hard subtitle status and export strategy support

**Files:**
- Modify: `src/translip/types.py`
- Modify: `src/translip/delivery/runner.py`
- Modify: `src/translip/server/routes/delivery.py`
- Modify: `src/translip/server/task_read_model.py`
- Modify: `src/translip/server/schemas.py`

- [ ] Add typed fields for hard subtitle detection status and bilingual export strategy in request/response models.
- [ ] Implement OCR-artifact-based hard subtitle detection in the task read model.
- [ ] Extend delivery compose payload handling to accept the strategy field and persist it into delivery config.
- [ ] Update delivery export logic so `preserve_hard_subtitles_add_english` burns only English on the original video, while `clean_video_rebuild_bilingual` keeps the existing bilingual path.
- [ ] Re-run the backend pytest command and confirm the new tests pass.

Run:

```bash
uv run pytest -q tests/test_delivery.py tests/test_server_routes.py
```

### Task 3: Add failing frontend tests for export warning and strategy selection

**Files:**
- Modify: `frontend/src/pages/__tests__/TaskDetailPage.delivery.test.tsx`

- [ ] Add a failing test that opens the export drawer for a bilingual review task with confirmed hard subtitles and expects a strategy warning with the recommended option selected.
- [ ] Add a failing test that confirms the compose payload uses `preserve_hard_subtitles_add_english` by default and can switch to `clean_video_rebuild_bilingual`.
- [ ] Run the frontend test command and confirm the new tests fail before UI changes.

Run:

```bash
cd frontend && npm test -- --run src/pages/__tests__/TaskDetailPage.delivery.test.tsx
```

### Task 4: Implement frontend export warning, copy, and payload changes

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/tasks.ts`
- Modify: `frontend/src/lib/taskPresentation.ts`
- Modify: `frontend/src/pages/NewTaskPage.tsx`
- Modify: `frontend/src/pages/TaskDetailPage.tsx`

- [ ] Rename the user-facing intent copy from `中英双语审片版` to `双语审片版` where appropriate.
- [ ] Hydrate hard subtitle status and last-used strategy from task payloads.
- [ ] Show the export-time warning only for bilingual review tasks with confirmed hard subtitles.
- [ ] Default the recommended option to `保留原字 + 补英文`, but allow switching to `清理原字 + 重做双语`.
- [ ] Include the selected strategy in the compose API payload and surface the effective strategy in export summary text.
- [ ] Re-run the frontend test command and confirm the updated tests pass.

Run:

```bash
cd frontend && npm test -- --run src/pages/__tests__/TaskDetailPage.delivery.test.tsx
```

### Task 5: Run broader verification and real-video validation

**Files:**
- No code changes expected unless failures require follow-up

- [ ] Run backend and frontend focused suites covering delivery behavior.
- [ ] Start the app locally if needed and validate the end-to-end export interaction with Playwright using `/Users/masamiyui/Downloads/哪吒预告片.mp4`.
- [ ] Confirm the bilingual review export path shows the warning and that the recommended strategy avoids duplicate Chinese subtitles.
- [ ] Record any residual limitations discovered during real-video testing.

Run:

```bash
uv run pytest -q tests/test_delivery.py tests/test_server_routes.py
cd frontend && npm test -- --run src/pages/__tests__/TaskDetailPage.delivery.test.tsx
```

Playwright validation target:

```text
/Users/masamiyui/Downloads/哪吒预告片.mp4
```
