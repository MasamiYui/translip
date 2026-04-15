#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
FRONTEND_DIR=${DEV_FRONTEND_DIR:-"$REPO_ROOT/frontend"}
RUNTIME_DIR=${DEV_RUNTIME_DIR:-"$REPO_ROOT/.dev-runtime"}

API_HOST=127.0.0.1
API_PORT=${DEV_API_PORT:-8765}
WEB_HOST=127.0.0.1
WEB_PORT=${DEV_WEB_PORT:-5173}

API_PID_FILE="$RUNTIME_DIR/api.pid"
WEB_PID_FILE="$RUNTIME_DIR/web.pid"
API_LOG_FILE="$RUNTIME_DIR/api.log"
WEB_LOG_FILE="$RUNTIME_DIR/web.log"

usage() {
  echo "Usage: $0 start|stop|restart|status" >&2
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing required command: $1" >&2
    exit 1
  fi
}

read_pid() {
  tr -d '[:space:]' < "$1"
}

is_pid_running() {
  pid=$1
  [ -n "$pid" ] || return 1
  kill -0 "$pid" 2>/dev/null
}

cleanup_stale_pid_file() {
  pid_file=$1
  if [ ! -f "$pid_file" ]; then
    return 0
  fi

  pid=$(read_pid "$pid_file" || true)
  if [ -z "$pid" ] || ! is_pid_running "$pid"; then
    rm -f "$pid_file"
  fi
}

is_port_in_use() {
  port=$1
  lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
}

ensure_runtime_dir() {
  mkdir -p "$RUNTIME_DIR"
}

start_detached() {
  pid_file=$1
  log_file=$2
  work_dir=$3
  shift 3

  python3 - "$pid_file" "$log_file" "$work_dir" "$@" <<'PY'
import os
import subprocess
import sys

pid_file, log_file, work_dir, *cmd = sys.argv[1:]

with open(log_file, "ab", buffering=0) as log_handle, open(os.devnull, "rb") as devnull:
    process = subprocess.Popen(
        cmd,
        cwd=work_dir,
        stdin=devnull,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )

with open(pid_file, "w", encoding="utf-8") as pid_handle:
    pid_handle.write(f"{process.pid}\n")
PY
}

start_api() {
  start_detached \
    "$API_PID_FILE" \
    "$API_LOG_FILE" \
    "$REPO_ROOT" \
    uv run uvicorn translip.server.app:app --host "$API_HOST" --port "$API_PORT"
}

start_web() {
  start_detached \
    "$WEB_PID_FILE" \
    "$WEB_LOG_FILE" \
    "$FRONTEND_DIR" \
    npm run dev -- --host "$WEB_HOST" --port "$WEB_PORT"
}

wait_for_pid() {
  pid_file=$1
  attempts=5

  while [ "$attempts" -gt 0 ]; do
    if [ -f "$pid_file" ]; then
      pid=$(read_pid "$pid_file" || true)
      if [ -n "$pid" ] && is_pid_running "$pid"; then
        return 0
      fi
    fi
    attempts=$((attempts - 1))
    sleep 1
  done

  return 1
}

wait_for_port() {
  port=$1
  attempts=15

  while [ "$attempts" -gt 0 ]; do
    if is_port_in_use "$port"; then
      return 0
    fi
    attempts=$((attempts - 1))
    sleep 1
  done

  return 1
}

stop_pid_file() {
  pid_file=$1
  service_name=$2

  cleanup_stale_pid_file "$pid_file"
  if [ ! -f "$pid_file" ]; then
    echo "$service_name: stopped"
    return 0
  fi

  pid=$(read_pid "$pid_file" || true)
  if [ -n "$pid" ] && is_pid_running "$pid"; then
    kill -TERM "-$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
    attempts=10
    while [ "$attempts" -gt 0 ] && is_pid_running "$pid"; do
      attempts=$((attempts - 1))
      sleep 1
    done
    if is_pid_running "$pid"; then
      kill -KILL "-$pid" 2>/dev/null || kill -9 "$pid" 2>/dev/null || true
    fi
  fi

  rm -f "$pid_file"
  echo "$service_name: stopped"
}

status_service() {
  pid_file=$1
  service_name=$2
  service_url=$3
  service_port=$4

  cleanup_stale_pid_file "$pid_file"
  if [ -f "$pid_file" ]; then
    pid=$(read_pid "$pid_file")
    if is_port_in_use "$service_port"; then
      echo "$service_name: running (pid $pid, $service_url)"
    else
      echo "$service_name: process running without open port $service_port (pid $pid)"
    fi
  else
    if is_port_in_use "$service_port"; then
      echo "$service_name: stopped (port $service_port already in use by another process)"
    else
      echo "$service_name: stopped ($service_url)"
    fi
  fi
}

run_start() {
  require_command uv
  require_command npm
  require_command python3
  require_command lsof

  ensure_runtime_dir
  cleanup_stale_pid_file "$API_PID_FILE"
  cleanup_stale_pid_file "$WEB_PID_FILE"

  if [ -f "$API_PID_FILE" ]; then
    echo "api is already running" >&2
    exit 1
  fi
  if [ -f "$WEB_PID_FILE" ]; then
    echo "web is already running" >&2
    exit 1
  fi

  if is_port_in_use "$API_PORT"; then
    echo "port $API_PORT is already in use" >&2
    exit 1
  fi
  if is_port_in_use "$WEB_PORT"; then
    echo "port $WEB_PORT is already in use" >&2
    exit 1
  fi

  if [ ! -d "$FRONTEND_DIR" ]; then
    echo "frontend directory not found: $FRONTEND_DIR" >&2
    exit 1
  fi

  : > "$API_LOG_FILE"
  : > "$WEB_LOG_FILE"

  start_api
  if ! wait_for_pid "$API_PID_FILE" || ! wait_for_port "$API_PORT"; then
    stop_pid_file "$API_PID_FILE" "api" >/dev/null
    rm -f "$API_PID_FILE"
    echo "failed to start api service" >&2
    exit 1
  fi

  start_web
  if ! wait_for_pid "$WEB_PID_FILE" || ! wait_for_port "$WEB_PORT"; then
    stop_pid_file "$API_PID_FILE" "api" >/dev/null
    stop_pid_file "$WEB_PID_FILE" "web" >/dev/null
    rm -f "$WEB_PID_FILE"
    echo "failed to start web service" >&2
    exit 1
  fi

  echo "api: running (http://$API_HOST:$API_PORT)"
  echo "web: running (http://$WEB_HOST:$WEB_PORT)"
  echo "logs: $API_LOG_FILE $WEB_LOG_FILE"
}

run_stop() {
  ensure_runtime_dir
  stop_pid_file "$API_PID_FILE" "api"
  stop_pid_file "$WEB_PID_FILE" "web"
}

run_status() {
  ensure_runtime_dir
  status_service "$API_PID_FILE" "api" "http://$API_HOST:$API_PORT" "$API_PORT"
  status_service "$WEB_PID_FILE" "web" "http://$WEB_HOST:$WEB_PORT" "$WEB_PORT"
}

run_restart() {
  run_stop
  run_start
}

command_name=${1:-}
case "$command_name" in
  start)
    run_start
    ;;
  stop)
    run_stop
    ;;
  restart)
    run_restart
    ;;
  status)
    run_status
    ;;
  *)
    usage
    exit 1
    ;;
esac
