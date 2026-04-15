#!/bin/zsh
set -euo pipefail

AGENTS_DIR="$HOME/Library/LaunchAgents"
USER_DOMAIN="gui/$(id -u)"

for label in com.thenameszinski.volante-fpl-api com.thenameszinski.volante-fpl-web; do
  plist="$AGENTS_DIR/${label}.plist"
  launchctl bootout "$USER_DOMAIN" "$plist" >/dev/null 2>&1 || true
  rm -f "$plist"
done

echo "Volante launchd services removed."
