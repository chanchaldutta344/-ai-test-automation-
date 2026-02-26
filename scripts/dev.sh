#!/usr/bin/env bash
set -euo pipefail

# scripts/dev.sh - start/stop frontend+backend dev servers and show status
# Usage: scripts/dev.sh start | stop | restart | status | start-backend | start-frontend | stop-backend | stop-frontend

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_DIR="$ROOT/.dev/pids"
mkdir -p "$PID_DIR"

backend_pidfile="$PID_DIR/backend.pid"
frontend_pidfile="$PID_DIR/frontend.pid"

start_backend() {
  echo "Starting backend..."
  pushd "$ROOT/test-automation-backend" >/dev/null
  # If pidfile exists and process is running, skip starting a new one
  if [ -f "$backend_pidfile" ]; then
    existing_pid=$(grep -oE '"pid"[[:space:]]*:[[:space:]]*[0-9]+' "$backend_pidfile" | head -n1 | grep -oE '[0-9]+' || true)
    if [ -n "$existing_pid" ] && kill -0 "$existing_pid" >/dev/null 2>&1; then
      echo "Backend already running (pid $existing_pid), skipping start"
      popd >/dev/null
      return
    fi
  fi
  if command -v poetry >/dev/null 2>&1; then
    poetry run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 &
  else
    python3 -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 &
  fi
  pid=$!
  # Write descriptive pidfile (JSON) with metadata for easier debugging
  start_time=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  cmd="uvicorn app.main:app"
  cwd=$(pwd)
  user=$(whoami)
  cat > "$backend_pidfile" <<EOF
{"pid": $pid, "cmd": "$cmd", "start_time": "$start_time", "cwd": "$cwd", "user": "$user"}
EOF
  popd >/dev/null
  echo "Backend started (pid $pid)"
}

start_frontend() {
  echo "Starting frontend..."
  pushd "$ROOT/test-automation-frontend" >/dev/null
  # If pidfile exists and process is running, skip starting a new one
  if [ -f "$frontend_pidfile" ]; then
    existing_pid=$(grep -oE '"pid"[[:space:]]*:[[:space:]]*[0-9]+' "$frontend_pidfile" | head -n1 | grep -oE '[0-9]+' || true)
    if [ -n "$existing_pid" ] && kill -0 "$existing_pid" >/dev/null 2>&1; then
      echo "Frontend already running (pid $existing_pid), skipping start"
      popd >/dev/null
      return
    fi
  fi
  # If vite is already running, reuse it
  vite_pids=$(ps -u $(id -u) -o pid= -o args= | grep -E 'node_modules/.bin/vite|\bvite\b' | awk '{print $1}' | tr '\n' ' ' || true)
  if [ -n "$vite_pids" ]; then
    pid=$(echo "$vite_pids" | awk '{print $1}')
    echo "Found existing vite process (pid $pid), reusing"
    start_time=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    raw_cmd=$(ps -p "$pid" -o args= 2>/dev/null || true)
    cmd=$(echo "$raw_cmd" | sed 's/"/\\"/g')
    cwd=$(pwd)
    user=$(whoami)
    cat > "$frontend_pidfile" <<EOF
{"pid": $pid, "cmd": "$cmd", "start_time": "$start_time", "cwd": "$cwd", "user": "$user"}
EOF
    popd >/dev/null
    return
  fi
  # Start Vite and capture logs to .dev/frontend.log for easier debugging
  LOG_FILE="$ROOT/.dev/frontend.log"
  nohup npm run dev -- --host 127.0.0.1 > "$LOG_FILE" 2>&1 &
  pid=$!
  # Write descriptive pidfile (JSON) with metadata for easier debugging
  start_time=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  cmd="npm run dev -- --host 127.0.0.1 (logs: $LOG_FILE)"
  cwd=$(pwd)
  user=$(whoami)
  cat > "$frontend_pidfile" <<EOF
{"pid": $pid, "cmd": "$cmd", "start_time": "$start_time", "cwd": "$cwd", "user": "$user"}
EOF
  popd >/dev/null
  echo "Frontend started (pid $pid)"
}

stop_pidfile() {
  pidfile="$1"
  if [ -f "$pidfile" ]; then
    # Try to extract JSON pid value; fall back to legacy plain-pid format
    pid=$(grep -oE '"pid"[[:space:]]*:[[:space:]]*[0-9]+' "$pidfile" | head -n1 | grep -oE '[0-9]+' || true)
    if [ -z "$pid" ]; then
      pid=$(cat "$pidfile" 2>/dev/null || true)
    fi
    if kill -0 "$pid" >/dev/null 2>&1; then
      echo "Stopping pid $pid..."
      kill "$pid" || true
      sleep 0.5
    fi
    rm -f "$pidfile"
  else
    echo "No pidfile: $pidfile"
    echo "Searching for common dev processes to stop..."
    # Try to find and stop uvicorn (backend) processes launched from this repo
    uvicorn_pids=$(pgrep -f "uvicorn app.main:app" || true)
    if [ -n "$uvicorn_pids" ]; then
      echo "Found uvicorn pids: $uvicorn_pids";
      echo "$uvicorn_pids" | xargs -r kill || true
    fi
    # Try to find and stop vite dev server (frontend)
    vite_pids=$(pgrep -f "\bvite\b" || true)
    if [ -n "$vite_pids" ]; then
      echo "Found vite pids: $vite_pids";
      echo "$vite_pids" | xargs -r kill || true
    fi
  fi
}

status() {
  echo "Dev status:"
  if [ -f "$backend_pidfile" ]; then
    # Read JSON pidfile metadata if present, else fallback to raw pid
    bpid=$(grep -oE '"pid"[[:space:]]*:[[:space:]]*[0-9]+' "$backend_pidfile" | head -n1 | grep -oE '[0-9]+' || true)
    if [ -z "$bpid" ]; then
      bpid=$(cat "$backend_pidfile" 2>/dev/null || true)
    fi
    bcmd=$(grep -oE '"cmd"[[:space:]]*:[[:space:]]*"[^"]+"' "$backend_pidfile" | sed -E 's/"cmd"[[:space:]]*:[[:space:]]*"([^"]+)"/\1/' || true)
    bstart=$(grep -oE '"start_time"[[:space:]]*:[[:space:]]*"[^"]+"' "$backend_pidfile" | sed -E 's/"start_time"[[:space:]]*:[[:space:]]*"([^"]+)"/\1/' || true)
    if [ -n "$bpid" ] && kill -0 "$bpid" >/dev/null 2>&1; then
      echo "  Backend running (pid $bpid)"
      [ -n "$bcmd" ] && echo "    cmd: $bcmd"
      [ -n "$bstart" ] && echo "    started: $bstart"
    else
      echo "  Backend pidfile exists but process not running"
      [ -n "$bcmd" ] && echo "    cmd: $bcmd"
      [ -n "$bstart" ] && echo "    started: $bstart"
    fi
  else
    echo "  Backend not running"
  fi

  if [ -f "$frontend_pidfile" ]; then
    fpid=$(grep -oE '"pid"[[:space:]]*:[[:space:]]*[0-9]+' "$frontend_pidfile" | head -n1 | grep -oE '[0-9]+' || true)
    if [ -z "$fpid" ]; then
      fpid=$(cat "$frontend_pidfile" 2>/dev/null || true)
    fi
    fcmd=$(grep -oE '"cmd"[[:space:]]*:[[:space:]]*"[^"]+"' "$frontend_pidfile" | sed -E 's/"cmd"[[:space:]]*:[[:space:]]*"([^"]+)"/\1/' || true)
    fstart=$(grep -oE '"start_time"[[:space:]]*:[[:space:]]*"[^"]+"' "$frontend_pidfile" | sed -E 's/"start_time"[[:space:]]*:[[:space:]]*"([^"]+)"/\1/' || true)
    if [ -n "$fpid" ] && kill -0 "$fpid" >/dev/null 2>&1; then
      echo "  Frontend running (pid $fpid)"
      [ -n "$fcmd" ] && echo "    cmd: $fcmd"
      [ -n "$fstart" ] && echo "    started: $fstart"
    else
      echo "  Frontend pidfile exists but process not running"
      [ -n "$fcmd" ] && echo "    cmd: $fcmd"
      [ -n "$fstart" ] && echo "    started: $fstart"
    fi
  else
    echo "  Frontend not running"
  fi
}

case "${1:-}" in
  start)
    start_backend
    start_frontend
    ;;
  start-backend)
    start_backend
    ;;
  start-frontend)
    start_frontend
    ;;
  stop)
    stop_pidfile "$backend_pidfile"
    stop_pidfile "$frontend_pidfile"
    echo "Performing additional cleanup for any remaining dev processes..."
    # Kill any remaining uvicorn processes owned by this user
    uvicorn_pids=$(pgrep -u $(id -u) -f "uvicorn app.main:app" || true)
    if [ -n "$uvicorn_pids" ]; then
      echo "Killing uvicorn pids: $uvicorn_pids"
      echo "$uvicorn_pids" | xargs -r kill || true
    fi
    # Kill any remaining vite processes owned by this user
    vite_pids=$(ps -u $(id -u) -o pid= -o args= | grep -E 'node_modules/.bin/vite|\bvite\b' | awk '{print $1}' | tr '\n' ' ' || true)
    if [ -n "$vite_pids" ]; then
      echo "Killing vite pids: $vite_pids"
      echo "$vite_pids" | xargs -r kill || true
    fi
    ;;
  stop-backend)
    stop_pidfile "$backend_pidfile"
    ;;
  stop-frontend)
    stop_pidfile "$frontend_pidfile"
    ;;
  restart)
    $0 stop
    $0 start
    ;;
  status)
    status
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|status|start-backend|start-frontend|stop-backend|stop-frontend}"
    exit 2
    ;;
esac
