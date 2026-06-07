#!/usr/bin/env bash
set -euo pipefail

LABEL="com.hcs.nyanya.discord"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
rm -f "$PLIST"
echo "Removed $LABEL"
