from __future__ import annotations

import os
import socket
import stat
import subprocess
import shutil
from pathlib import Path


def _script_path() -> Path:
    return Path(__file__).resolve().parents[1] / "scripts" / "dev.sh"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def _system_lsof_script() -> str:
    lsof_path = shutil.which("lsof")
    if lsof_path is None:
        raise AssertionError("lsof is required for these tests")
    return f"""#!/bin/sh
exec "{lsof_path}" "$@"
"""


def _make_env(tmp_path: Path, *, lsof_script: str | None = None, uv_script: str | None = None, npm_script: str | None = None) -> tuple[dict[str, str], Path]:
    bin_dir = tmp_path / "bin"
    runtime_dir = tmp_path / ".dev-runtime"
    frontend_dir = tmp_path / "frontend"
    bin_dir.mkdir()
    runtime_dir.mkdir()
    frontend_dir.mkdir()

    _write_executable(bin_dir / "lsof", lsof_script or _system_lsof_script())
    if uv_script is not None:
        _write_executable(bin_dir / "uv", uv_script)
    if npm_script is not None:
        _write_executable(bin_dir / "npm", npm_script)

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["DEV_RUNTIME_DIR"] = str(runtime_dir)
    env["DEV_FRONTEND_DIR"] = str(frontend_dir)
    env["DEV_API_PORT"] = str(_get_free_port())
    env["DEV_WEB_PORT"] = str(_get_free_port())
    return env, runtime_dir


PORT_SERVER_STUB = """#!/bin/sh
port=""
while [ "$#" -gt 0 ]; do
  if [ "$1" = "--port" ]; then
    port=$2
    shift 2
    continue
  fi
  shift
done
exec python3 -m http.server "$port" --bind 127.0.0.1
"""


def _get_free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _run_dev(tmp_path: Path, *args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", str(_script_path()), *args],
        capture_output=True,
        text=True,
        cwd=_script_path().parents[1],
        env=env,
        check=False,
    )


def test_dev_script_status_reports_stopped_when_no_pid_files(tmp_path: Path) -> None:
    env, _runtime_dir = _make_env(
        tmp_path,
    )

    result = _run_dev(tmp_path, "status", env=env)

    assert result.returncode == 0
    assert "api: stopped" in result.stdout
    assert "web: stopped" in result.stdout


def test_dev_script_usage_lists_supported_commands(tmp_path: Path) -> None:
    env, _runtime_dir = _make_env(
        tmp_path,
    )

    result = _run_dev(tmp_path, env=env)

    assert result.returncode != 0
    assert "start|stop|restart|status" in result.stderr


def test_dev_script_start_and_stop_manage_pid_files(tmp_path: Path) -> None:
    env, runtime_dir = _make_env(
        tmp_path,
        uv_script=PORT_SERVER_STUB,
        npm_script=PORT_SERVER_STUB,
    )

    start = _run_dev(tmp_path, "start", env=env)

    assert start.returncode == 0
    api_pid_path = runtime_dir / "api.pid"
    web_pid_path = runtime_dir / "web.pid"
    assert api_pid_path.exists()
    assert web_pid_path.exists()

    api_pid = int(api_pid_path.read_text(encoding="utf-8").strip())
    web_pid = int(web_pid_path.read_text(encoding="utf-8").strip())
    assert api_pid > 0
    assert web_pid > 0
    assert os.path.exists(runtime_dir / "api.log")
    assert os.path.exists(runtime_dir / "web.log")

    stop = _run_dev(tmp_path, "stop", env=env)

    assert stop.returncode == 0
    assert not api_pid_path.exists()
    assert not web_pid_path.exists()
    with subprocess.Popen(["sh", "-c", f"kill -0 {api_pid}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) as proc:
        proc.wait()
        assert proc.returncode != 0
    with subprocess.Popen(["sh", "-c", f"kill -0 {web_pid}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) as proc:
        proc.wait()
        assert proc.returncode != 0


def test_dev_script_start_fails_when_api_port_is_in_use(tmp_path: Path) -> None:
    env, runtime_dir = _make_env(
        tmp_path,
        lsof_script="""#!/bin/sh
for arg in "$@"; do
  if [ "$arg" = "-iTCP:$DEV_API_PORT" ]; then
    exit 0
  fi
done
exit 1
""",
        uv_script=PORT_SERVER_STUB,
        npm_script=PORT_SERVER_STUB,
    )

    result = _run_dev(tmp_path, "start", env=env)

    assert result.returncode != 0
    assert f"port {env['DEV_API_PORT']} is already in use" in result.stderr
    assert not (runtime_dir / "api.pid").exists()
    assert not (runtime_dir / "web.pid").exists()


def test_dev_script_status_cleans_stale_pid_files(tmp_path: Path) -> None:
    env, runtime_dir = _make_env(
        tmp_path,
    )
    stale_pid_path = runtime_dir / "api.pid"
    stale_pid_path.write_text("999999\n", encoding="utf-8")

    result = _run_dev(tmp_path, "status", env=env)

    assert result.returncode == 0
    assert "api: stopped" in result.stdout
    assert not stale_pid_path.exists()


def test_dev_script_restart_recreates_pid_files(tmp_path: Path) -> None:
    env, runtime_dir = _make_env(
        tmp_path,
        uv_script=PORT_SERVER_STUB,
        npm_script=PORT_SERVER_STUB,
    )

    start = _run_dev(tmp_path, "start", env=env)
    assert start.returncode == 0
    old_api_pid = int((runtime_dir / "api.pid").read_text(encoding="utf-8").strip())
    old_web_pid = int((runtime_dir / "web.pid").read_text(encoding="utf-8").strip())

    restart = _run_dev(tmp_path, "restart", env=env)

    assert restart.returncode == 0
    new_api_pid = int((runtime_dir / "api.pid").read_text(encoding="utf-8").strip())
    new_web_pid = int((runtime_dir / "web.pid").read_text(encoding="utf-8").strip())
    assert new_api_pid != old_api_pid
    assert new_web_pid != old_web_pid

    _run_dev(tmp_path, "stop", env=env)
