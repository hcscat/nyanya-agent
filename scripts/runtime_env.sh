#!/usr/bin/env bash
# Shared runtime environment for launchd and terminal entrypoints.

set -euo pipefail

NYANYA_DEFAULT_PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/local/sbin:/usr/bin:/bin:/usr/sbin:/sbin"
export PATH="$NYANYA_DEFAULT_PATH${PATH:+:$PATH}"
