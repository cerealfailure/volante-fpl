#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${VOLANTE_PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
USER_ENV_FILE="${VOLANTE_ENV_FILE:-$HOME/.fulcrum/.env}"
PROJECT_ENV_FILE="$ROOT_DIR/.env"

if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3)"
fi

load_env_file() {
  local env_file="$1"
  [[ -f "$env_file" ]] || return 0

  # Keep the parser narrow: the settings UI writes plain KEY=value lines.
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -z "$line" || "$line" == \#* || "$line" != *=* ]] && continue
    local key="${line%%=*}"
    local value="${line#*=}"
    [[ -n "${(P)key:-}" ]] && continue
    export "$key=$value"
  done < "$env_file"
}

load_env_file "$USER_ENV_FILE"
load_env_file "$PROJECT_ENV_FILE"

cd "$ROOT_DIR/server"
export PYTHONUNBUFFERED=1

exec "$PYTHON_BIN" -m uvicorn main:app \
  --host "${VOLANTE_API_HOST:-127.0.0.1}" \
  --port "${VOLANTE_API_PORT:-8556}"
