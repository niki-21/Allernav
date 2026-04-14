#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_DIR="$ROOT_DIR/apps/api"
WEB_DIR="$ROOT_DIR/apps/web"
API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-3000}"

api_pid=""
web_pid=""

cleanup() {
  if [[ -n "$web_pid" ]] && kill -0 "$web_pid" 2>/dev/null; then
    kill "$web_pid" 2>/dev/null || true
  fi
  if [[ -n "$api_pid" ]] && kill -0 "$api_pid" 2>/dev/null; then
    kill "$api_pid" 2>/dev/null || true
  fi
  wait 2>/dev/null || true
}

trap cleanup EXIT INT TERM

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

check_port() {
  local port="$1"
  if lsof -ti "tcp:${port}" >/dev/null 2>&1; then
    echo "Port ${port} is already in use. Stop the existing process first." >&2
    exit 1
  fi
}

load_google_key() {
  if [[ -n "${GOOGLE_MAPS_API_KEY:-}" ]]; then
    return
  fi

  local env_file="$WEB_DIR/.env.local"
  if [[ -f "$env_file" ]]; then
    local key
    key="$(sed -n 's/^NEXT_PUBLIC_GOOGLE_MAPS_API_KEY=//p' "$env_file" | tail -n 1)"
    if [[ -n "$key" ]]; then
      export GOOGLE_MAPS_API_KEY="$key"
    fi
  fi
}

run_api() {
  cd "$API_DIR"
  if [[ ! -x ".venv/bin/uvicorn" ]]; then
    echo "Missing API venv at $API_DIR/.venv" >&2
    exit 1
  fi

  .venv/bin/uvicorn main:app --reload --port "$API_PORT" 2>&1 | while IFS= read -r line; do
    printf '[api] %s\n' "$line"
  done
}

run_web() {
  cd "$WEB_DIR"
  NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:${API_PORT}" npm run dev -- --port "$WEB_PORT" 2>&1 | while IFS= read -r line; do
    printf '[web] %s\n' "$line"
  done
}

require_command lsof
require_command npm
load_google_key

if [[ -z "${GOOGLE_MAPS_API_KEY:-}" ]]; then
  echo "GOOGLE_MAPS_API_KEY is not set, and no key was found in $WEB_DIR/.env.local" >&2
  exit 1
fi

check_port "$API_PORT"
check_port "$WEB_PORT"

echo "Starting Allernav..."
echo "Web: http://127.0.0.1:${WEB_PORT}"
echo "API: http://127.0.0.1:${API_PORT}/health"
echo "Press Ctrl+C to stop both services."

run_api &
api_pid=$!

run_web &
web_pid=$!

while true; do
  api_alive=0
  web_alive=0

  if kill -0 "$api_pid" 2>/dev/null; then
    api_alive=1
  fi

  if kill -0 "$web_pid" 2>/dev/null; then
    web_alive=1
  fi

  if [[ "$api_alive" -eq 0 || "$web_alive" -eq 0 ]]; then
    break
  fi

  sleep 1
done
