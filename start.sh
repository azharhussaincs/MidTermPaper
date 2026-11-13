#!/usr/bin/env bash
# MindBridge Intake AI — start backend (FastAPI) + frontend (Vite) in the background.
#
#   ./start.sh                 # defaults: backend 8000, frontend 5173 (falls back to 8010 / 5174+ if busy)
#   BACKEND_PORT=9000 FRONTEND_PORT=3000 ./start.sh
#
# First run creates backend/.venv, installs requirements, runs `npm install` and creates
# backend/.env from .env.example. PIDs and logs go to .run/. Stop with ./stop.sh.
# Works with the stock bash 3.2 on macOS.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
RUN_DIR="$ROOT/.run"
VENV="$BACKEND/.venv"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-90}"

if [ -t 1 ]; then
  BOLD=$'\033[1m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RED=$'\033[31m'; RESET=$'\033[0m'
else
  BOLD=""; GREEN=""; YELLOW=""; RED=""; RESET=""
fi
info() { printf '%s▸%s %s\n' "$BOLD" "$RESET" "$*"; }
warn() { printf '%s! %s%s\n' "$YELLOW" "$*" "$RESET"; }
fail() { printf '%s✗ %s%s\n' "$RED" "$*" "$RESET" >&2; exit 1; }

is_alive() { [ -n "${1:-}" ] && kill -0 "$1" 2>/dev/null; }
read_pid() { [ -f "$RUN_DIR/$1.pid" ] && cat "$RUN_DIR/$1.pid" || true; }

hash_file() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1
  else shasum -a 256 "$1" | cut -d' ' -f1; fi
}

# True if something is LISTENING on the TCP port (any interface).
port_in_use() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
  elif command -v ss >/dev/null 2>&1; then
    [ -n "$(ss -ltnH "sport = :$port" 2>/dev/null)" ]
  else
    (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null
  fi
}

# Echo the preferred port if free, else the first free port from fallback..fallback+20.
pick_port() {
  local preferred="$1" fallback="$2" port
  if ! port_in_use "$preferred"; then echo "$preferred"; return; fi
  for port in $(seq "$fallback" $((fallback + 20))); do
    if [ "$port" != "$preferred" ] && ! port_in_use "$port"; then echo "$port"; return; fi
  done
  return 1
}

http_ok() {
  if command -v curl >/dev/null 2>&1; then
    curl -fsS -o /dev/null --max-time 2 "$1" 2>/dev/null
  else
    "$VENV/bin/python" - "$1" <<'PY' 2>/dev/null
import sys, urllib.request
urllib.request.urlopen(sys.argv[1], timeout=2)
PY
  fi
}

find_python() {
  local candidate
  for candidate in python3.13 python3.12 python3.11 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 \
      && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
      echo "$candidate"; return
    fi
  done
  return 1
}

# ---------------------------------------------------------------------------
# Already running?
# ---------------------------------------------------------------------------
mkdir -p "$RUN_DIR"
if is_alive "$(read_pid backend)" || is_alive "$(read_pid frontend)"; then
  [ -f "$RUN_DIR/ports.env" ] && . "$RUN_DIR/ports.env"
  warn "MindBridge is already running (run ./stop.sh first to restart)."
  printf '  Frontend: http://localhost:%s\n  API docs: http://localhost:%s/docs\n' \
    "${FRONTEND_PORT:-?}" "${BACKEND_PORT:-?}"
  exit 0
fi

# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------
command -v node >/dev/null 2>&1 || fail "Node.js 20+ is required (https://nodejs.org)."
command -v npm >/dev/null 2>&1 || fail "npm is required (it ships with Node.js)."

REQ_HASH="$(hash_file "$BACKEND/requirements.txt")"
if [ ! -x "$VENV/bin/python" ]; then
  PYTHON="$(find_python)" || fail "Python 3.11+ is required (python3.11 / python3.12 / python3.13)."
  info "Creating backend virtual environment with $PYTHON ($("$PYTHON" --version 2>&1))"
  "$PYTHON" -m venv "$VENV"
fi
if [ "$(cat "$VENV/.requirements.sha256" 2>/dev/null || true)" != "$REQ_HASH" ]; then
  info "Installing backend requirements (first run or requirements.txt changed)…"
  "$VENV/bin/python" -m pip install --quiet --upgrade pip
  "$VENV/bin/python" -m pip install --quiet -r "$BACKEND/requirements.txt"
  echo "$REQ_HASH" > "$VENV/.requirements.sha256"
fi

if [ ! -d "$FRONTEND/node_modules" ]; then
  info "Installing frontend dependencies (npm install)…"
  (cd "$FRONTEND" && npm install --no-audit --no-fund --loglevel=error)
fi

if [ ! -f "$BACKEND/.env" ]; then
  cp "$BACKEND/.env.example" "$BACKEND/.env"
  warn "Created backend/.env from .env.example. Add GEMINI_API_KEY there (or use local Ollama)."
fi

# ---------------------------------------------------------------------------
# Ports (never take over a port another app is using)
# ---------------------------------------------------------------------------
WANT_BACKEND="${BACKEND_PORT:-8000}"
WANT_FRONTEND="${FRONTEND_PORT:-5173}"
BACKEND_PORT="$(pick_port "$WANT_BACKEND" 8010)" || fail "No free backend port found."
FRONTEND_PORT="$(pick_port "$WANT_FRONTEND" 5174)" || fail "No free frontend port found."
[ "$BACKEND_PORT" = "$WANT_BACKEND" ] || warn "Port $WANT_BACKEND is busy; backend will use $BACKEND_PORT."
[ "$FRONTEND_PORT" = "$WANT_FRONTEND" ] || warn "Port $WANT_FRONTEND is busy; frontend will use $FRONTEND_PORT."

BACKEND_URL="http://localhost:$BACKEND_PORT"
FRONTEND_URL="http://localhost:$FRONTEND_PORT"
export CORS_ORIGINS="$FRONTEND_URL,http://127.0.0.1:$FRONTEND_PORT"
export VITE_API_BASE_URL="$BACKEND_URL"
printf 'BACKEND_PORT=%s\nFRONTEND_PORT=%s\n' "$BACKEND_PORT" "$FRONTEND_PORT" > "$RUN_DIR/ports.env"

# ---------------------------------------------------------------------------
# Launch (absolute paths, so stop.sh can recognise exactly these processes)
# ---------------------------------------------------------------------------
STARTED_OK=0
cleanup_on_failure() {
  if [ "$STARTED_OK" != 1 ]; then
    warn "Startup failed; stopping anything that was started."
    "$ROOT/stop.sh" >/dev/null 2>&1 || true
  fi
}
trap cleanup_on_failure EXIT

info "Starting backend on $BACKEND_URL"
(
  cd "$BACKEND"
  # `python -m` rather than .venv/bin/uvicorn: that script's shebang pins the folder's old path,
  # so it breaks if the project is moved or renamed after the venv was created.
  exec nohup "$VENV/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port "$BACKEND_PORT" \
    > "$RUN_DIR/backend.log" 2>&1 < /dev/null
) &
echo $! > "$RUN_DIR/backend.pid"

info "Starting frontend on $FRONTEND_URL"
(
  cd "$FRONTEND"
  exec nohup "$FRONTEND/node_modules/.bin/vite" --port "$FRONTEND_PORT" --strictPort \
    > "$RUN_DIR/frontend.log" 2>&1 < /dev/null
) &
echo $! > "$RUN_DIR/frontend.pid"

# ---------------------------------------------------------------------------
# Health checks
# ---------------------------------------------------------------------------
wait_for() {
  local name="$1" url="$2" pid_name="$3" waited=0
  while ! http_ok "$url"; do
    if ! is_alive "$(read_pid "$pid_name")"; then
      printf '%s--- last lines of .run/%s.log ---%s\n' "$RED" "$pid_name" "$RESET" >&2
      tail -n 25 "$RUN_DIR/$pid_name.log" >&2 || true
      fail "$name exited during startup."
    fi
    if [ "$waited" -ge "$HEALTH_TIMEOUT" ]; then
      fail "$name did not become healthy within ${HEALTH_TIMEOUT}s (see .run/$pid_name.log)."
    fi
    sleep 1
    waited=$((waited + 1))
  done
}

wait_for "Backend" "http://127.0.0.1:$BACKEND_PORT/api/system/health" backend
wait_for "Frontend" "http://localhost:$FRONTEND_PORT/" frontend
STARTED_OK=1

cat <<EOF

${GREEN}${BOLD}✓ MindBridge Intake AI is running${RESET}

  Frontend UI   ${BOLD}$FRONTEND_URL${RESET}
  API (Swagger) ${BOLD}$BACKEND_URL/docs${RESET}
  Health        $BACKEND_URL/api/system/health

  Logs: .run/backend.log, .run/frontend.log
  Stop: ./stop.sh
EOF

if ! grep -Eq '^GEMINI_API_KEY=.+' "$BACKEND/.env" || grep -q '^GEMINI_API_KEY=your-gemini-api-key-here' "$BACKEND/.env"; then
  printf '\n%sNo GEMINI_API_KEY in backend/.env: chat needs it, or a working local Ollama model.%s\n' "$YELLOW" "$RESET"
fi
