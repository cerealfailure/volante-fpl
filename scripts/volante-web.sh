#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
NPM_BIN="${VOLANTE_NPM_BIN:-$HOME/.nvm/versions/node/v24.13.1/bin/npm}"

if [[ ! -x "$NPM_BIN" ]]; then
  NPM_BIN="$(command -v npm)"
fi

export PATH="$(dirname "$NPM_BIN"):/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
cd "$ROOT_DIR/app"

exec "$NPM_BIN" run dev -- \
  --host "${VOLANTE_WEB_HOST:-127.0.0.1}" \
  --port "${VOLANTE_WEB_PORT:-5556}" \
  --strictPort
