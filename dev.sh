#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEB_DIR="$ROOT_DIR/apps/web"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

require_command npm

if [[ ! -f "$WEB_DIR/.env.local" ]]; then
  echo "Missing $WEB_DIR/.env.local" >&2
  echo "Copy $WEB_DIR/.env.example to .env.local and add your Google Maps key." >&2
  exit 1
fi

cd "$WEB_DIR"
exec npm run dev -- "$@"
