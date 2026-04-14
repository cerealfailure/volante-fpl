#!/bin/zsh
set -euo pipefail

AGENTS_DIR="$HOME/Library/LaunchAgents"
USER_DOMAIN="gui/$(id -u)"

for label in com.volante.api com.volante.web; do
  plist="$AGENTS_DIR/${label}.plist"
  launchctl bootout "$USER_DOMAIN" "$plist" >/dev/null 2>&1 || true
  rm -f "$plist"
done

echo "Volante launchd services removed."
