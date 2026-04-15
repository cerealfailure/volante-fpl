#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
AGENTS_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$HOME/Library/Logs"
USER_DOMAIN="gui/$(id -u)"
NPM_BIN="${VOLANTE_NPM_BIN:-$HOME/.nvm/versions/node/v24.13.1/bin/npm}"
API_LABEL="com.thenameszinski.volante-fpl-api"
WEB_LABEL="com.thenameszinski.volante-fpl-web"

mkdir -p "$AGENTS_DIR" "$LOG_DIR"

if [[ ! -x "$NPM_BIN" ]]; then
  NPM_BIN="$(command -v npm)"
fi

escape_sed() {
  printf '%s' "$1" | sed 's/[&|]/\\&/g'
}

ROOT_ESCAPED="$(escape_sed "$ROOT_DIR")"
HOME_ESCAPED="$(escape_sed "$HOME")"

render_plist() {
  local template="$1"
  local target="$2"
  sed \
    -e "s|__ROOT_DIR__|$ROOT_ESCAPED|g" \
    -e "s|__HOME__|$HOME_ESCAPED|g" \
    "$template" > "$target"
}

cd "$ROOT_DIR/app"
"$NPM_BIN" run build

render_plist "$ROOT_DIR/ops/launchd/${API_LABEL}.plist" "$AGENTS_DIR/${API_LABEL}.plist"
render_plist "$ROOT_DIR/ops/launchd/${WEB_LABEL}.plist" "$AGENTS_DIR/${WEB_LABEL}.plist"

for label in "$API_LABEL" "$WEB_LABEL"; do
  plist="$AGENTS_DIR/${label}.plist"
  launchctl bootout "$USER_DOMAIN" "$plist" >/dev/null 2>&1 || true
  launchctl bootstrap "$USER_DOMAIN" "$plist"
  launchctl kickstart -k "$USER_DOMAIN/$label"
done

echo "Volante is running under launchd."
echo "  Frontend: http://localhost:5556"
echo "  API:      http://localhost:8556"
echo "  Logs:     $LOG_DIR/volante-fpl-web.log and $LOG_DIR/volante-fpl-api.log"
