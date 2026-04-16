# Task/Delivery Config Separation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separate pipeline execution config from delivery/export config without changing the database schema, and move delivery-only editing to the task detail page.

**Architecture:** Normalize stored task JSON into canonical `pipeline` and `delivery` sections in the backend, expose pipeline config plus explicit `delivery_config` in API responses, and simplify the new-task frontend so delivery styling only lives in the task detail composer. Keep legacy flat tasks working through normalization helpers.

**Tech Stack:** FastAPI, SQLModel, Python pytest, React, TypeScript, Vitest, Playwright

---

### Task 1: Add backend normalization coverage first

**Files:**
- Modify: `tests/test_task_config_normalization.py`

- [ ] **Step 1: Write failing tests for split config normalization and request building**

```python
def test_normalize_task_storage_splits_legacy_flat_config() -> None:
    ...

def test_build_pipeline_request_reads_delivery_config_from_nested_storage(tmp_path: Path) -> None:
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_task_config_normalization.py -q`
Expected: FAIL because normalization helpers and nested-delivery handling do not exist yet.

- [ ] **Step 3: Implement minimal normalization helpers**

```python
def normalize_task_storage(config: Mapping[str, Any] | None) -> dict[str, Any]:
    return {"pipeline": ..., "delivery": ...}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_task_config_normalization.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_task_config_normalization.py src/translip/server/task_config.py src/translip/server/task_manager.py
git commit -m "test: cover split task config normalization"
```

### Task 2: Persist delivery config independently

**Files:**
- Modify: `src/translip/server/schemas.py`
- Modify: `src/translip/server/routes/tasks.py`
- Modify: `src/translip/server/routes/delivery.py`
- Test: `tests/test_delivery_routes.py`

- [ ] **Step 1: Write failing route tests**

```python
def test_task_read_exposes_delivery_config(client):
    ...

def test_delivery_compose_updates_delivery_config_only(client):
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_delivery_routes.py -q`
Expected: FAIL because task reads do not expose `delivery_config` and compose mutates shared config.

- [ ] **Step 3: Implement API and persistence updates**

```python
class TaskRead(BaseModel):
    config: Dict[str, Any]
    delivery_config: Dict[str, Any]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_delivery_routes.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/translip/server/schemas.py src/translip/server/routes/tasks.py src/translip/server/routes/delivery.py tests/test_delivery_routes.py
git commit -m "feat: separate task delivery config persistence"
```

### Task 3: Remove delivery-only controls from new task creation

**Files:**
- Modify: `frontend/src/pages/NewTaskPage.tsx`
- Test: `frontend/src/pages/__tests__/NewTaskPage.test.tsx`

- [ ] **Step 1: Write failing UI tests**

```tsx
it('hides delivery-only subtitle styling controls on step two', () => {
  expect(screen.queryByText('字幕字体')).not.toBeInTheDocument()
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --run src/pages/__tests__/NewTaskPage.test.tsx`
Expected: FAIL because the controls still render.

- [ ] **Step 3: Implement minimal UI changes**

```tsx
<Field label={t.newTask.fields.template}>...</Field>
<Field label={t.newTask.fields.videoSource}>...</Field>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- --run src/pages/__tests__/NewTaskPage.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/NewTaskPage.tsx frontend/src/pages/__tests__/NewTaskPage.test.tsx
git commit -m "refactor: move delivery styling out of new task flow"
```

### Task 4: Hydrate task detail composer from delivery config

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/pages/TaskDetailPage.tsx`
- Test: `frontend/src/pages/__tests__/TaskDetailPage.delivery.test.tsx`

- [ ] **Step 1: Write failing hydration tests**

```tsx
it('hydrates composer controls from delivery_config', async () => {
  expect(await screen.findByDisplayValue('Source Han Sans')).toBeInTheDocument()
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --run src/pages/__tests__/TaskDetailPage.delivery.test.tsx`
Expected: FAIL because the page still uses hard-coded defaults.

- [ ] **Step 3: Implement minimal composer hydration**

```tsx
useEffect(() => {
  setFontFamily(task.delivery_config.subtitle_font ?? 'Noto Sans')
}, [task])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- --run src/pages/__tests__/TaskDetailPage.delivery.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/pages/TaskDetailPage.tsx frontend/src/pages/__tests__/TaskDetailPage.delivery.test.tsx
git commit -m "feat: hydrate delivery composer from task delivery config"
```

### Task 5: Full verification

**Files:**
- No code changes required

- [ ] **Step 1: Run backend tests**

Run: `pytest tests/test_task_config_normalization.py tests/test_delivery_routes.py -q`
Expected: PASS

- [ ] **Step 2: Run frontend tests**

Run: `cd frontend && npm test -- --run src/pages/__tests__/NewTaskPage.test.tsx src/pages/__tests__/TaskDetailPage.delivery.test.tsx`
Expected: PASS

- [ ] **Step 3: Run app against `test_video` and verify behavior**

Run: `./scripts/dev.sh`
Expected: frontend and backend start successfully with the updated config model.

- [ ] **Step 4: Run Playwright validation**

Run: `npx playwright test`
Expected: PASS for the new task creation flow and task detail composer coverage.

- [ ] **Step 5: Commit**

```bash
git add .
git commit -m "test: verify split pipeline and delivery config flow"
```
