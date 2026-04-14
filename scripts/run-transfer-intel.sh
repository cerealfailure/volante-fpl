#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -x "$ROOT_DIR/.venv/bin/python3" ]]; then
  exec "$ROOT_DIR/.venv/bin/python3" server/intel_cli.py "$@"
fi

if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  exec "$ROOT_DIR/.venv/bin/python" server/intel_cli.py "$@"
fi

exec python3 server/intel_cli.py "$@"
