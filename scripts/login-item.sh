#!/bin/bash
set -euo pipefail
label='org.lgtvcontrol.macos'
plist="$HOME/Library/LaunchAgents/$label.plist"
case "${1:-}" in
 enable)
  app="$HOME/Applications/LG TV Control.app"
  [ -d "$app" ] || { echo 'Install the app first.' >&2; exit 1; }
  mkdir -p "$HOME/Library/LaunchAgents"
  /usr/libexec/PlistBuddy -c 'Clear dict' -c "Add :Label string $label" \
    -c 'Add :ProgramArguments array' -c 'Add :ProgramArguments:0 string /usr/bin/open' \
    -c 'Add :ProgramArguments:1 string -g' -c "Add :ProgramArguments:2 string $app" \
    -c 'Add :RunAtLoad bool true' "$plist"
  launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$plist"
  ;;
 disable)
  launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
  if [ -f "$plist" ]; then rm "$plist"; fi
  ;;
 *) echo 'Usage: scripts/login-item.sh enable|disable' >&2; exit 1 ;;
esac
