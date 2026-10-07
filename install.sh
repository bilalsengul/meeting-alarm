#!/bin/bash
# Compile the overlay and (re)install the launchd agent (macOS). Idempotent.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
BASE="${MEETING_ALARM_HOME:-$HOME/.meeting-alarm}"
LABEL="com.meeting-alarm.daemon"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
PY="$(command -v python3)"
mkdir -p "$BASE" "$HOME/Library/LaunchAgents"
xcrun swiftc -O -o "$BASE/overlay" "$HERE/overlay/overlay.swift"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>$PY</string><string>$HERE/alarm.py</string></array>
  <key>EnvironmentVariables</key><dict><key>MEETING_ALARM_HOME</key><string>$BASE</string></dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>30</integer>
  <key>StandardOutPath</key><string>$BASE/launchd.out.log</string>
  <key>StandardErrorPath</key><string>$BASE/launchd.err.log</string>
</dict></plist>
PL
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl print "gui/$(id -u)/$LABEL" | grep -E 'state|pid' | head -3 || true
echo "installed: $PLIST"
