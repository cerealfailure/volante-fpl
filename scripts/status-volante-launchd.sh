#!/bin/zsh
set -euo pipefail

USER_DOMAIN="gui/$(id -u)"

for label in com.volante.api com.volante.web; do
  echo "== $label =="
  launchctl print "$USER_DOMAIN/$label" 2>/dev/null | rg "state =|pid =|last exit code =|path =" || true
  echo
done
