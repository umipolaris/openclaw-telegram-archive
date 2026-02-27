#!/usr/bin/env bash
set -euo pipefail

LABEL="${AUTO_START_LABEL:-com.umipolaris.docarchive.autostart}"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
PLIST_PATH="$LAUNCH_AGENTS_DIR/$LABEL.plist"
uid="$(id -u)"

launchctl bootout "gui/${uid}" "$PLIST_PATH" >/dev/null 2>&1 || true
launchctl unload -w "$PLIST_PATH" >/dev/null 2>&1 || true

if [[ -f "$PLIST_PATH" ]]; then
  rm -f "$PLIST_PATH"
fi

echo "Removed launch agent: ${LABEL}"
