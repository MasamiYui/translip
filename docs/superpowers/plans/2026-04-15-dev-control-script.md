# Dev Control Script Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a single repo-local script that can start, stop, restart, and inspect the frontend and backend development servers on fixed ports.

**Architecture:** Keep the process control logic in a small shell script at `scripts/dev.sh`, with PID and log files written under `.dev-runtime/`. Cover observable behavior with subprocess-based pytest tests so the shell stays simple while critical control flow remains regression-tested.

**Tech Stack:** POSIX shell, pytest, subprocess, uvicorn, Vite, README documentation

---

## File Map

- Create: `scripts/dev.sh`
- Create: `tests/test_dev_script.py`
- Modify: `.gitignore`
- Modify: `README.md`

### Task 1: Add a Failing Regression Test for the Dev Control Script

**Files:**
- Create: `tests/test_dev_script.py`
- Test: `tests/test_dev_script.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path


def _write_stub_command(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def test_dev_script_status_reports_stopped_when_no_pid_files(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "dev.sh"
    runtime_dir = tmp_path / ".dev-runtime"
    runtime_dir.mkdir()

    stub_bin = tmp_path / "bin"
    stub_bin.mkdir()
    _write_stub_command(
        stub_bin / "lsof",
        "#!/bin/sh\nexit 1\n",
    )

    env = os.environ.copy()
    env["PATH"] = f"{stub_bin}:{env['PATH']}"
    env["DEV_RUNTIME_DIR"] = str(runtime_dir)

    result = subprocess.run(
        ["sh", str(script_path), "status"],
        capture_output=True,
        text=True,
        env=env,
        cwd=script_path.parent.parent,
        check=False,
    )

    assert result.returncode == 0
    assert "api: stopped" in result.stdout
    assert "web: stopped" in result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_dev_script.py::test_dev_script_status_reports_stopped_when_no_pid_files -q`
Expected: FAIL because `scripts/dev.sh` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Create `scripts/dev.sh` with command dispatch, repo-root resolution, `.dev-runtime` support, and a `status` command that prints:

```sh
api: stopped
web: stopped
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_dev_script.py::test_dev_script_status_reports_stopped_when_no_pid_files -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_dev_script.py scripts/dev.sh
git commit -m "Add initial dev control script status command"
```

### Task 2: Add Start and Stop Behavior with Port Checks

**Files:**
- Modify: `scripts/dev.sh`
- Modify: `tests/test_dev_script.py`
- Test: `tests/test_dev_script.py`

- [ ] **Step 1: Write the failing test**

Append a test that stubs `uv`, `npm`, and `lsof`, then verifies `start` writes PID files and `stop` removes them:

```python
def test_dev_script_start_and_stop_manage_pid_files(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "dev.sh"
    runtime_dir = tmp_path / ".dev-runtime"

    stub_bin = tmp_path / "bin"
    stub_bin.mkdir()
    _write_stub_command(stub_bin / "lsof", "#!/bin/sh\nexit 1\n")
    _write_stub_command(stub_bin / "uv", "#!/bin/sh\nsleep 30 & wait\n")
    _write_stub_command(stub_bin / "npm", "#!/bin/sh\nsleep 30 & wait\n")

    env = os.environ.copy()
    env["PATH"] = f"{stub_bin}:{env['PATH']}"
    env["DEV_RUNTIME_DIR"] = str(runtime_dir)

    start = subprocess.run(
        ["sh", str(script_path), "start"],
        capture_output=True,
        text=True,
        env=env,
        cwd=script_path.parent.parent,
        check=False,
    )
    assert start.returncode == 0
    assert (runtime_dir / "api.pid").exists()
    assert (runtime_dir / "web.pid").exists()

    stop = subprocess.run(
        ["sh", str(script_path), "stop"],
        capture_output=True,
        text=True,
        env=env,
        cwd=script_path.parent.parent,
        check=False,
    )
    assert stop.returncode == 0
    assert not (runtime_dir / "api.pid").exists()
    assert not (runtime_dir / "web.pid").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_dev_script.py::test_dev_script_start_and_stop_manage_pid_files -q`
Expected: FAIL because `start` and `stop` are not implemented.

- [ ] **Step 3: Write minimal implementation**

Update `scripts/dev.sh` to:

```sh
start)
  # require uv npm lsof
  # refuse to start if 8765 or 5173 are in use
  # start backend in repo root, frontend in frontend/
  # write .dev-runtime/api.pid and .dev-runtime/web.pid
  ;;
stop)
  # terminate pids from pid files if they are still running
  # remove pid files afterward
  ;;
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_dev_script.py::test_dev_script_start_and_stop_manage_pid_files -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_dev_script.py scripts/dev.sh
git commit -m "Add dev control script start and stop commands"
```

### Task 3: Cover Restart, Port Conflicts, and Stale PID Cleanup

**Files:**
- Modify: `scripts/dev.sh`
- Modify: `tests/test_dev_script.py`
- Test: `tests/test_dev_script.py`

- [ ] **Step 1: Write the failing tests**

Add tests that cover:

```python
def test_dev_script_start_fails_when_api_port_is_in_use(tmp_path: Path) -> None:
    ...
    _write_stub_command(
        stub_bin / "lsof",
        "#!/bin/sh\nif [ \"$3\" = \"8765\" ]; then exit 0; fi\nexit 1\n",
    )
    ...
    assert result.returncode != 0
    assert "port 8765 is already in use" in result.stderr


def test_dev_script_status_cleans_stale_pid_files(tmp_path: Path) -> None:
    ...
    (runtime_dir / "api.pid").write_text("999999\n", encoding="utf-8")
    ...
    assert not (runtime_dir / "api.pid").exists()


def test_dev_script_restart_recreates_pid_files(tmp_path: Path) -> None:
    ...
    assert restart.returncode == 0
    assert (runtime_dir / "api.pid").exists()
    assert (runtime_dir / "web.pid").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_dev_script.py -q`
Expected: FAIL because restart flow, stale PID cleanup, or port-conflict messaging is incomplete.

- [ ] **Step 3: Write minimal implementation**

Update `scripts/dev.sh` to:

```sh
restart)
  run_stop
  run_start
  ;;

status)
  # remove stale pid files when process no longer exists
  # report per-service state plus URLs
  ;;
```

Also make `start` emit a clear error for occupied ports:

```sh
echo "port 8765 is already in use" >&2
exit 1
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_dev_script.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_dev_script.py scripts/dev.sh
git commit -m "Harden dev control script lifecycle behavior"
```

### Task 4: Ignore Runtime Artifacts and Document Usage

**Files:**
- Modify: `.gitignore`
- Modify: `README.md`
- Test: `tests/test_dev_script.py`

- [ ] **Step 1: Write the failing expectation**

Add a simple documentation-oriented assertion in `tests/test_dev_script.py` that checks the script usage text includes all supported commands:

```python
def test_dev_script_usage_lists_supported_commands(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "dev.sh"
    result = subprocess.run(
        ["sh", str(script_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "start|stop|restart|status" in result.stderr
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_dev_script.py::test_dev_script_usage_lists_supported_commands -q`
Expected: FAIL until usage text is added.

- [ ] **Step 3: Write minimal implementation**

Update `scripts/dev.sh` usage output, add `.dev-runtime/` to `.gitignore`, and document the commands in `README.md` with:

```md
./scripts/dev.sh start
./scripts/dev.sh stop
./scripts/dev.sh restart
./scripts/dev.sh status
```

- [ ] **Step 4: Run focused verification**

Run: `uv run pytest tests/test_dev_script.py -q`
Expected: PASS

Run: `bash scripts/dev.sh status`
Expected: exit 0 and service state output

- [ ] **Step 5: Commit**

```bash
git add scripts/dev.sh tests/test_dev_script.py .gitignore README.md
git commit -m "Document dev control script workflow"
```

### Task 5: Final Verification

**Files:**
- Modify: none
- Test: `tests/test_dev_script.py`

- [ ] **Step 1: Run the automated verification suite**

Run: `uv run pytest tests/test_dev_script.py tests/test_server_app.py -q`
Expected: PASS

- [ ] **Step 2: Run manual lifecycle verification**

Run: `bash scripts/dev.sh start`
Expected: exit 0, `.dev-runtime/api.pid` and `.dev-runtime/web.pid` created

Run: `bash scripts/dev.sh status`
Expected: both services reported as running

Run: `bash scripts/dev.sh restart`
Expected: exit 0 and both services still reported as running afterward

Run: `bash scripts/dev.sh stop`
Expected: exit 0 and PID files removed

- [ ] **Step 3: Inspect git diff**

Run: `git status --short`
Expected: only intended files changed

- [ ] **Step 4: Commit final polish if needed**

```bash
git add scripts/dev.sh tests/test_dev_script.py .gitignore README.md
git commit -m "Finalize dev control script"
```
