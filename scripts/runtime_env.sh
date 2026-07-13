#!/usr/bin/env bash
# Shared runtime environment for launchd and terminal entrypoints.

set -euo pipefail

NYANYA_DEFAULT_PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/local/sbin:/usr/bin:/bin:/usr/sbin:/sbin"
export PATH="$NYANYA_DEFAULT_PATH${PATH:+:$PATH}"

nyanya_runtime_python() {
  local code_root="$1"
  local state_root="${NYANYA_HOME:-$code_root}"
  if [[ -x "$state_root/.venv/bin/python" ]]; then
    printf '%s\n' "$state_root/.venv/bin/python"
  else
    printf '%s\n' "${PYTHON:-python3}"
  fi
}
