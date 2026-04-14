#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
AGENTS_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$HOME/Library/Logs"
USER_DOMAIN="gui/$(id -u)"
NPM_BIN="${VOLANTE_NPM_BIN:-$(command -v npm)}"

if [[ -z "$NPM_BIN" || ! -x "$NPM_BIN" ]]; then
  echo "npm not found. Install Node.js or set VOLANTE_NPM_BIN to the npm path." >&2
  exit 1
fi

mkdir -p "$AGENTS_DIR" "$LOG_DIR"

cd "$ROOT_DIR/app"
"$NPM_BIN" run build

render_plist() {
  local template="$1"
  local dest="$2"
  sed -e "s|@@VOLANTE_ROOT@@|$ROOT_DIR|g" \
      -e "s|@@HOME@@|$HOME|g" \
      "$template" > "$dest"
}

render_plist "$ROOT_DIR/ops/launchd/com.volante.api.plist.template" "$AGENTS_DIR/com.volante.api.plist"
render_plist "$ROOT_DIR/ops/launchd/com.volante.web.plist.template" "$AGENTS_DIR/com.volante.web.plist"

for label in com.volante.api com.volante.web; do
  plist="$AGENTS_DIR/${label}.plist"
  launchctl bootout "$USER_DOMAIN" "$plist" >/dev/null 2>&1 || true
  launchctl bootstrap "$USER_DOMAIN" "$plist"
  launchctl kickstart -k "$USER_DOMAIN/$label"
done

echo "Volante is running under launchd."
echo "  Frontend: http://localhost:5555"
echo "  API:      http://localhost:8555"
echo "  Logs:     $LOG_DIR/volante-web.log and $LOG_DIR/volante-api.log"
