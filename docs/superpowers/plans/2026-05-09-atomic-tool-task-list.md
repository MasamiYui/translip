# Atomic Tool Task List Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist atomic tool jobs and provide an independent atomic task list plus Dashboard aggregation.

**Architecture:** Keep pipeline `Task` tables untouched. Add dedicated atomic job/file/artifact tables and adapt `JobManager` to read/write SQLite. Add list/detail frontend routes that consume the new atomic job APIs.

**Tech Stack:** FastAPI, SQLModel, SQLite, React, React Router, TanStack Query, Vitest, pytest, Browser/Playwright validation.

---

### Task 1: Backend Persistence

**Files:**
- Modify: `src/translip/server/models.py`
- Modify: `src/translip/server/atomic_tools/schemas.py`
- Modify: `src/translip/server/atomic_tools/job_manager.py`
- Modify: `src/translip/server/routes/atomic_tools.py`
- Test: `tests/test_atomic_tools_job_persistence.py`
- Test: `tests/test_atomic_tools_api.py`

- [ ] Write failing tests for DB-backed upload/job/artifact persistence and list endpoints.
- [ ] Add SQLModel tables for atomic files, jobs, and artifacts.
- [ ] Persist upload metadata, job lifecycle updates, results, errors, and artifact metadata.
- [ ] Add list, recent, detail, delete, and rerun routes.
- [ ] Preserve existing tool-specific job routes.

### Task 2: Frontend API And Types

**Files:**
- Modify: `frontend/src/types/atomic-tools.ts`
- Modify: `frontend/src/api/atomic-tools.ts`
- Test: `frontend/src/api/__tests__/atomic-tools.test.ts`

- [ ] Write failing API tests for list/detail/delete/rerun endpoints.
- [ ] Add atomic job list/detail response types.
- [ ] Add API client methods.

### Task 3: Atomic Job UI

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/layout/Sidebar.tsx`
- Create: `frontend/src/pages/AtomicJobListPage.tsx`
- Create: `frontend/src/pages/AtomicJobDetailPage.tsx`
- Modify: `frontend/src/i18n/messages.ts`
- Test: `frontend/src/test/atomic-tools/AtomicJobListPage.test.tsx`
- Test: `frontend/src/test/atomic-tools/AtomicJobDetailPage.test.tsx`

- [ ] Write failing render tests for list and detail pages.
- [ ] Add routes and navigation entry.
- [ ] Implement list filters and table.
- [ ] Implement detail summary, JSON sections, artifacts, delete, rerun, and origin tool link.

### Task 4: Dashboard Aggregation

**Files:**
- Modify: `frontend/src/pages/DashboardPage.tsx`
- Modify: `frontend/src/i18n/messages.ts`
- Test: `frontend/src/pages/__tests__/DashboardPage.test.tsx`

- [ ] Write failing test for recent atomic runs on Dashboard.
- [ ] Fetch `/api/atomic-tools/jobs/recent` independently from pipeline tasks.
- [ ] Render compact recent atomic runs panel without affecting pipeline task totals.

### Task 5: Verification

- [ ] Run focused pytest tests.
- [ ] Run focused Vitest tests.
- [ ] Run frontend build.
- [ ] Restart dev service if needed.
- [ ] Validate `/tools/jobs`, `/tools/jobs/:jobId`, and Dashboard in Browser/Playwright.
