#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
AGENTS_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$HOME/Library/Logs"
USER_DOMAIN="gui/$(id -u)"
NPM_BIN="${VOLANTE_NPM_BIN:-$HOME/.nvm/versions/node/v24.13.1/bin/npm}"

mkdir -p "$AGENTS_DIR" "$LOG_DIR"

if [[ ! -x "$NPM_BIN" ]]; then
  NPM_BIN="$(command -v npm)"
fi

cd "$ROOT_DIR/app"
"$NPM_BIN" run build

cp "$ROOT_DIR/ops/launchd/com.thenameszinski.volante-api.plist" "$AGENTS_DIR/"
cp "$ROOT_DIR/ops/launchd/com.thenameszinski.volante-web.plist" "$AGENTS_DIR/"

for label in com.thenameszinski.volante-api com.thenameszinski.volante-web; do
  plist="$AGENTS_DIR/${label}.plist"
  launchctl bootout "$USER_DOMAIN" "$plist" >/dev/null 2>&1 || true
  launchctl bootstrap "$USER_DOMAIN" "$plist"
  launchctl kickstart -k "$USER_DOMAIN/$label"
done

echo "Volante is running under launchd."
echo "  Frontend: http://localhost:5555"
echo "  API:      http://localhost:8555"
echo "  Logs:     $LOG_DIR/volante-web.log and $LOG_DIR/volante-api.log"
