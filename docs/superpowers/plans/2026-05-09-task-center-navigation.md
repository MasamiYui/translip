# Task Center Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize sidebar navigation so pipeline tasks and atomic jobs live under one task center, while atomic tools only lists capability entry points.

**Architecture:** Keep existing routes unchanged. Update only sidebar composition and localized labels so `/tasks`, `/tools/jobs`, and `/tasks/new` appear as task-center children, and `/tools` plus individual tools remain under atomic tools.

**Tech Stack:** React, React Router, TanStack Query, Vitest, Testing Library, Browser plugin validation.

---

### Task 1: Sidebar Tests

**Files:**
- Modify: `frontend/src/components/layout/__tests__/Sidebar.test.tsx`

- [x] **Step 1: Write failing tests**

Add assertions that `任务中心` is an expandable button, `流水线任务` points to `/tasks`, `原子任务` points to `/tools/jobs`, `新建流水线任务` points to `/tasks/new`, and `原子工具集` no longer contains `运行记录`.

- [x] **Step 2: Run focused test**

Run: `npm run test -- --run src/components/layout/__tests__/Sidebar.test.tsx`

Expected before implementation: FAIL because the current sidebar still renders top-level `任务列表` and keeps `运行记录` under atomic tools.

### Task 2: Sidebar Implementation

**Files:**
- Modify: `frontend/src/components/layout/Sidebar.tsx`
- Modify: `frontend/src/i18n/messages.ts`

- [ ] **Step 1: Add localized navigation labels**

Add labels for `任务中心`, `流水线任务`, `原子任务`, and `新建流水线任务`, with matching English labels.

- [ ] **Step 2: Update sidebar grouping**

Replace the top-level task links with a task-center accordion. Move `/tools/jobs` into that group. Keep `/tools` and individual atomic capability routes under `原子工具集`.

- [ ] **Step 3: Preserve active states**

Make `/tasks` and task details activate `流水线任务`; `/tools/jobs` and atomic job details activate `原子任务`; `/tasks/new` activates `新建流水线任务`; `/tools` and `/tools/:toolId` activate `原子工具集`.

### Task 3: Verification

**Files:**
- Test: `frontend/src/components/layout/__tests__/Sidebar.test.tsx`

- [ ] **Step 1: Run focused frontend test**

Run: `npm run test -- --run src/components/layout/__tests__/Sidebar.test.tsx`

- [ ] **Step 2: Run build**

Run: `npm run build`

- [ ] **Step 3: Browser validation**

Restart dev services, open `http://127.0.0.1:5173/tasks`, verify the task-center child links and active state, then open `/tools/jobs` and verify `原子任务` is active and `原子工具集` only contains capability links.
