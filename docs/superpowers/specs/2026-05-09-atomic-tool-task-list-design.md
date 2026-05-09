# Atomic Tool Task List Design

## Goal

Persist atomic tool runs in SQLite and expose an independent atomic task list, while allowing the Dashboard to show recent atomic runs without mixing them into pipeline task totals.

## Product Shape

Atomic tools stay separate from pipeline tasks. `/tools` remains the atomic capability catalog and `/tools/:toolId` remains the single-tool run surface. A new `/tools/jobs` page lists atomic runs, and `/tools/jobs/:jobId` shows a run's parameters, inputs, status, result, and artifacts. The Dashboard shows a compact "recent atomic runs" panel sourced from the atomic jobs API.

## Backend Design

Add SQLModel tables for atomic uploads, jobs, and artifacts:

- `atomic_tool_files`: persisted upload and artifact file metadata.
- `atomic_tool_jobs`: one row per tool run, including tool id/name, status, params, progress, result, error, and timing.
- `atomic_tool_artifacts`: downloadable files produced by a job.

The existing code registry remains the source of truth for tool definitions. The database stores executions, not the capability catalog.

`JobManager` changes from in-memory state to database-backed state. It still writes files under `.cache/translip/atomic-tools`, but upload metadata, job status, and artifact metadata are stored in SQLite. On service startup, any stale `pending` or `running` jobs from a previous process are marked `interrupted`.

## API Design

Keep existing compatibility endpoints:

- `GET /api/atomic-tools/tools`
- `POST /api/atomic-tools/upload`
- `POST /api/atomic-tools/{tool_id}/run`
- `GET /api/atomic-tools/{tool_id}/jobs/{job_id}`
- `GET /api/atomic-tools/{tool_id}/jobs/{job_id}/result`
- `GET /api/atomic-tools/{tool_id}/jobs/{job_id}/artifacts`
- `GET /api/atomic-tools/{tool_id}/jobs/{job_id}/artifacts/{artifact_path}`

Add list and lifecycle endpoints:

- `GET /api/atomic-tools/jobs`
- `GET /api/atomic-tools/jobs/recent`
- `GET /api/atomic-tools/jobs/{job_id}`
- `DELETE /api/atomic-tools/jobs/{job_id}?delete_artifacts=true`
- `POST /api/atomic-tools/jobs/{job_id}/rerun`

The list endpoint supports `status`, `tool_id`, `search`, `page`, and `size`.

## Frontend Design

Add API methods to `frontend/src/api/atomic-tools.ts` and types to `frontend/src/types/atomic-tools.ts`.

Add pages:

- `AtomicJobListPage`: filters by status/tool/search, displays progress, created time, duration, and artifact count.
- `AtomicJobDetailPage`: shows status, progress, inputs, params, result JSON, artifacts, delete, rerun, and a link back to the originating tool.

Add routes:

- `/tools/jobs`
- `/tools/jobs/:jobId`

Update the sidebar's atomic tools accordion to include `能力库` and `运行记录` before individual tools. Update Dashboard with a recent atomic runs table, fetched independently from pipeline tasks.

## Status Semantics

Atomic job statuses are:

- `pending`
- `running`
- `completed`
- `failed`
- `cancelled`
- `interrupted`

`completed` maps to the existing status badge label visually as success, without changing the pipeline task status model.

## Validation

Backend tests cover persistence across `JobManager` instances, job list filters, recent jobs, artifact download, rerun, and deletion. Frontend tests cover API calls, job list rendering, detail rendering, sidebar navigation, and Dashboard aggregation. Rendered UI must be validated in the browser or Playwright after implementation.
