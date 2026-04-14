#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
NPM_BIN="${VOLANTE_NPM_BIN:-$(command -v npm)}"

if [[ -z "$NPM_BIN" || ! -x "$NPM_BIN" ]]; then
  echo "npm not found. Install Node.js or set VOLANTE_NPM_BIN to the npm path." >&2
  exit 1
fi

export PATH="$(dirname "$NPM_BIN"):/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
cd "$ROOT_DIR/app"

exec "$NPM_BIN" run dev -- \
  --host "${VOLANTE_WEB_HOST:-127.0.0.1}" \
  --port "${VOLANTE_WEB_PORT:-5555}" \
  --strictPort
