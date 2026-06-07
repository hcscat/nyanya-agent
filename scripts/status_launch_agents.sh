#!/usr/bin/env bash
set -euo pipefail

DOMAIN="gui/$(id -u)"

for LABEL in com.hcs.nyanya.discord com.hcs.nyanya.telegram; do
  echo "== $LABEL =="
  if launchctl print "$DOMAIN/$LABEL" >/tmp/hcs-nyanya-launchctl-status.$$ 2>/dev/null; then
    grep -E 'state =|pid =|last exit code =' /tmp/hcs-nyanya-launchctl-status.$$ || true
  else
    echo "not loaded"
  fi
  rm -f /tmp/hcs-nyanya-launchctl-status.$$
  echo
done
