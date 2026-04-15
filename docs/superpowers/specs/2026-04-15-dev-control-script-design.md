# Dev Control Script Design

Date: 2026-04-15

## Goal

Add a single developer-facing script for local web development process control so contributors can start, stop, restart, and inspect the React frontend and FastAPI backend without manually managing multiple terminals.

The script is intended for local development only. It does not replace production serving or process supervision.

## Scope

In scope:

- Add `scripts/dev.sh` as the single entrypoint.
- Support `start`, `stop`, `restart`, and `status` subcommands.
- Start the backend on `127.0.0.1:8765`.
- Start the frontend on `127.0.0.1:5173`.
- Run both services in the background for `start`.
- Persist runtime state under a repo-local `.dev-runtime/` directory.
- Refuse to start if the expected ports are already in use.
- Stop only processes started by this script via recorded PID files.

Out of scope:

- Automatic port selection.
- Production deployment behavior.
- Cross-machine process orchestration.
- Replacing existing README startup instructions beyond a focused usage note.

## User Interface

The script interface will be:

```bash
./scripts/dev.sh start
./scripts/dev.sh stop
./scripts/dev.sh restart
./scripts/dev.sh status
```

Expected behavior:

- `start`
  - Validate required commands (`uv`, `npm`, and a port inspection tool such as `lsof`).
  - Ensure `8765` and `5173` are not already listening.
  - Create `.dev-runtime/` if needed.
  - Start the backend from the repo root with:
    - `uv run uvicorn translip.server.app:app --host 127.0.0.1 --port 8765`
  - Start the frontend from `frontend/` with:
    - `npm run dev -- --host 127.0.0.1 --port 5173`
  - Store backend and frontend PIDs in `.dev-runtime/api.pid` and `.dev-runtime/web.pid`.
  - Write logs to `.dev-runtime/api.log` and `.dev-runtime/web.log`.
  - Print the two local URLs after startup.
- `stop`
  - Read the PID files if present.
  - Stop only those recorded processes.
  - Remove stale PID files after successful stop.
  - Leave unrelated processes alone, even if they use the same ports.
- `restart`
  - Execute `stop`, then `start`.
- `status`
  - Report whether each recorded PID exists.
  - Report whether `127.0.0.1:8765` and `127.0.0.1:5173` are listening.
  - Print the expected access URLs.

## Runtime Layout

Runtime files will live under `.dev-runtime/`:

- `api.pid`
- `web.pid`
- `api.log`
- `web.log`

This directory should be added to `.gitignore` so local process metadata and logs are never committed.

## Architecture

`scripts/dev.sh` will be a POSIX-compatible shell script with small helper functions, organized around command dispatch:

- `require_command`
  - Validate prerequisites like `uv`, `npm`, and `lsof`.
- `is_pid_running`
  - Check whether a stored PID still points to a live process.
- `is_port_in_use`
  - Check whether the fixed API or frontend port is already bound.
- `start_api`
  - Launch the backend and write PID/log files.
- `start_web`
  - Launch the frontend and write PID/log files.
- `stop_pid_file`
  - Stop a process referenced by a PID file and clean up stale state.
- `status_service`
  - Print a concise state summary for each service.

The script should derive the repository root from its own location so it works when invoked from any current working directory.

## Data Flow

For `start`:

1. Resolve repo root.
2. Verify prerequisites.
3. Create `.dev-runtime/`.
4. Check that both expected ports are free.
5. Start backend, capture PID, write `api.pid`.
6. Start frontend, capture PID, write `web.pid`.
7. Print success output with log file paths and URLs.

For `stop`:

1. Read `api.pid` and `web.pid` if present.
2. Terminate matching live processes.
3. Remove PID files.
4. Keep logs for inspection.

For `status`:

1. Read PID files if present.
2. Check process liveness.
3. Check port listeners.
4. Print a combined human-readable summary.

## Error Handling

The script should fail fast and print actionable messages for:

- Missing `uv`.
- Missing `npm`.
- Missing `lsof`.
- Missing `frontend/node_modules` if frontend startup fails.
- Port `8765` already in use.
- Port `5173` already in use.
- Stale PID files that reference dead processes.

Behavior details:

- If `start` sees a stale PID file but the process is dead, it may remove the stale file and continue.
- If backend startup succeeds but frontend startup fails, the script should stop the backend it just started before exiting. This avoids a half-started state.
- `stop` should not fail just because a PID file is stale; it should report the stale state, remove the file, and continue.

## Testing Strategy

Implementation should follow TDD.

Tests should cover:

- Repo runtime path generation.
- Command dispatch for `start`, `stop`, `restart`, and `status`.
- Refusing to start when a fixed port is already in use.
- Removing stale PID files.
- Cleaning up the backend if frontend startup fails.

Because shell scripts are awkward to unit test directly, the preferred approach is:

1. Keep the shell script small and procedural.
2. Add lightweight integration-style tests that invoke the script in a temporary directory with stubbed helper commands on `PATH`.

If that proves too heavy for this repo, the fallback is:

1. Add focused tests for observable script behavior via subprocess execution.
2. Verify the script manually in the repo as part of completion checks.

## Documentation Changes

Add a short section to the main README under the web management or development workflow area documenting:

- `./scripts/dev.sh start`
- `./scripts/dev.sh stop`
- `./scripts/dev.sh restart`
- `./scripts/dev.sh status`

Also note the fixed dev URLs:

- `http://127.0.0.1:8765`
- `http://127.0.0.1:5173`

## Open Decisions Already Resolved

The user has explicitly chosen:

- Unified single-script interface instead of separate scripts.
- Fixed ports instead of configurable or auto-detected ports.
- Support for `start`, `stop`, and `restart`, with `status` included as an inspection command.

## Implementation Boundaries

Keep the script intentionally small. Do not add:

- Additional subcommands like `logs`, `tail`, or `doctor`.
- Background/foreground mode switching.
- Parameterized ports.
- External process managers.

Those can be added later if real usage shows a need.
