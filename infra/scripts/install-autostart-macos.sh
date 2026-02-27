#!/usr/bin/env bash
set -euo pipefail

INFRA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AUTO_START_SCRIPT="$INFRA_DIR/scripts/autostart-up.sh"
LABEL="${AUTO_START_LABEL:-com.umipolaris.docarchive.autostart}"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
PLIST_PATH="$LAUNCH_AGENTS_DIR/$LABEL.plist"
LOG_DIR="$INFRA_DIR/data/logs"
OUT_LOG="$LOG_DIR/${LABEL}.out.log"
ERR_LOG="$LOG_DIR/${LABEL}.err.log"

APP_PROFILE_VALUE="${APP_PROFILE:-dev}"
AUTO_START_BUILD_VALUE="${AUTO_START_BUILD:-false}"
AUTO_START_WAIT_SECONDS_VALUE="${AUTO_START_WAIT_SECONDS:-300}"
AUTO_START_POLL_SECONDS_VALUE="${AUTO_START_POLL_SECONDS:-3}"
AUTO_START_MAX_RETRIES_VALUE="${AUTO_START_MAX_RETRIES:-6}"
AUTO_START_RETRY_INTERVAL_VALUE="${AUTO_START_RETRY_INTERVAL:-20}"
AUTO_START_ALLOW_BUILD_ON_MISS_VALUE="${AUTO_START_ALLOW_BUILD_ON_MISS:-true}"

mkdir -p "$LAUNCH_AGENTS_DIR" "$LOG_DIR"
chmod +x "$AUTO_START_SCRIPT"

cat >"$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${AUTO_START_SCRIPT}</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <dict>
    <key>SuccessfulExit</key>
    <false/>
  </dict>
  <key>ThrottleInterval</key>
  <integer>30</integer>
  <key>WorkingDirectory</key>
  <string>${INFRA_DIR}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>APP_PROFILE</key>
    <string>${APP_PROFILE_VALUE}</string>
    <key>AUTO_START_BUILD</key>
    <string>${AUTO_START_BUILD_VALUE}</string>
    <key>AUTO_START_WAIT_SECONDS</key>
    <string>${AUTO_START_WAIT_SECONDS_VALUE}</string>
    <key>AUTO_START_POLL_SECONDS</key>
    <string>${AUTO_START_POLL_SECONDS_VALUE}</string>
    <key>AUTO_START_MAX_RETRIES</key>
    <string>${AUTO_START_MAX_RETRIES_VALUE}</string>
    <key>AUTO_START_RETRY_INTERVAL</key>
    <string>${AUTO_START_RETRY_INTERVAL_VALUE}</string>
    <key>AUTO_START_ALLOW_BUILD_ON_MISS</key>
    <string>${AUTO_START_ALLOW_BUILD_ON_MISS_VALUE}</string>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
  <key>StandardOutPath</key>
  <string>${OUT_LOG}</string>
  <key>StandardErrorPath</key>
  <string>${ERR_LOG}</string>
</dict>
</plist>
EOF

uid="$(id -u)"
launchctl bootout "gui/${uid}" "$PLIST_PATH" >/dev/null 2>&1 || true

if ! launchctl bootstrap "gui/${uid}" "$PLIST_PATH" >/dev/null 2>&1; then
  launchctl load -w "$PLIST_PATH"
fi

launchctl kickstart -k "gui/${uid}/${LABEL}" >/dev/null 2>&1 || true

echo "Installed launch agent: ${LABEL}"
echo "Plist: ${PLIST_PATH}"
echo "Log(out): ${OUT_LOG}"
echo "Log(err): ${ERR_LOG}"
echo
echo "Check status:"
echo "  launchctl print gui/${uid}/${LABEL}"
