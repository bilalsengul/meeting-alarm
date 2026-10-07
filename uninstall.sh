#!/bin/bash
# Remove the launchd agent. With --purge, also delete the data dir (credentials, state, logs).
set -euo pipefail
BASE="${MEETING_ALARM_HOME:-$HOME/.meeting-alarm}"
LABEL="com.meeting-alarm.daemon"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$PLIST"
echo "removed: $PLIST"
if [ "${1:-}" = "--purge" ]; then
  if [ -z "$BASE" ] || [ "$BASE" = "/" ] || [ "$BASE" = "$HOME" ]; then
    echo "refusing to purge unsafe path: '$BASE'" >&2
    exit 1
  fi
  rm -r -f "$BASE"
  echo "purged: $BASE"
fi
