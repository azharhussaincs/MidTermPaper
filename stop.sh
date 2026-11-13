#!/usr/bin/env bash
# MindBridge Intake AI — stop the backend and frontend started by ./start.sh.
#
# Only processes belonging to THIS project are touched: the PIDs in .run/ (and their child
# processes), plus any leftover uvicorn/vite/esbuild started from this directory's
# backend/.venv or frontend/node_modules. Servers of other projects are never affected.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="$ROOT/.run"

if [ -t 1 ]; then GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RESET=$'\033[0m'; else GREEN=""; YELLOW=""; RESET=""; fi

is_alive() { [ -n "${1:-}" ] && kill -0 "$1" 2>/dev/null; }

# A PID and all of its descendants (children first is not required; we signal all at once).
descendants() {
  local pid="$1" child
  echo "$pid"
  for child in $(pgrep -P "$pid" 2>/dev/null); do descendants "$child"; done
}

# Does this PID run one of our launch commands? (Guards against a recycled PID.)
belongs_to_project() {
  local cmd
  cmd="$(ps -o command= -p "$1" 2>/dev/null || true)"
  case "$cmd" in
    *"$ROOT/backend/.venv/"*|*"$ROOT/frontend/node_modules/"*) return 0 ;;
    *) return 1 ;;
  esac
}

terminate() {
  # $@: PIDs. SIGTERM, wait up to 10 s, then SIGKILL whatever is left.
  local pids="$*" pid waited=0
  [ -z "$pids" ] && return 0
  kill -TERM $pids 2>/dev/null || true
  while [ $waited -lt 20 ]; do
    local alive=""
    for pid in $pids; do is_alive "$pid" && alive="$alive $pid"; done
    [ -z "$alive" ] && return 0
    sleep 0.5
    waited=$((waited + 1))
  done
  kill -KILL $alive 2>/dev/null || true
}

stopped=0
for name in backend frontend; do
  pid_file="$RUN_DIR/$name.pid"
  [ -f "$pid_file" ] || continue
  pid="$(cat "$pid_file")"
  if is_alive "$pid" && belongs_to_project "$pid"; then
    terminate $(descendants "$pid")
    printf '%s✓%s Stopped %s (pid %s)\n' "$GREEN" "$RESET" "$name" "$pid"
    stopped=$((stopped + 1))
  else
    printf '%s·%s %s was not running\n' "$YELLOW" "$RESET" "$name"
  fi
  rm -f "$pid_file"
done

# Leftovers from this project only (e.g. a reloader worker or esbuild service that outlived its parent).
leftovers=""
for pattern in "$ROOT/backend/.venv/bin/python -m uvicorn app.main:app" "$ROOT/backend/.venv/bin/uvicorn app.main:app" \
  "$ROOT/frontend/node_modules/.bin/vite" \
  "$ROOT/frontend/node_modules/@esbuild/"; do
  for pid in $(pgrep -f -- "$pattern" 2>/dev/null); do
    [ "$pid" != "$$" ] && belongs_to_project "$pid" && leftovers="$leftovers $(descendants "$pid")"
  done
done
if [ -n "${leftovers// /}" ]; then
  terminate $leftovers
  printf '%s✓%s Cleaned up leftover project processes:%s\n' "$GREEN" "$RESET" "$leftovers"
fi

if [ -f "$RUN_DIR/ports.env" ]; then
  . "$RUN_DIR/ports.env"
  rm -f "$RUN_DIR/ports.env"
fi

if [ $stopped -eq 0 ] && [ -z "${leftovers// /}" ]; then
  echo "MindBridge was not running."
else
  printf '%s✓ MindBridge stopped%s (ports %s / %s released).\n' "$GREEN" "$RESET" "${BACKEND_PORT:-?}" "${FRONTEND_PORT:-?}"
fi
