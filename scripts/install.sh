#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
app="$HOME/Applications/LG TV Control.app"
[ -d 'dist/LG TV Control.app' ] || { echo 'Run scripts/build.sh first.' >&2; exit 1; }
if [ -e "$app" ]; then
  echo "Already exists: $app. Quit it, move it to Trash, then retry (configuration is preserved)." >&2
  exit 1
fi
mkdir -p "$HOME/Applications"
ditto 'dist/LG TV Control.app' "$app"
codesign --verify --deep --strict "$app"
echo "Installed: $app"
echo 'Configure and pair using README instructions before opening the app.'
