#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

source "$ROOT_DIR/scripts/runtime_env.sh"
export NYANYA_PROJECT_ROOT="${NYANYA_PROJECT_ROOT:-$ROOT_DIR}"
export PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
exec "$(nyanya_runtime_python "$ROOT_DIR")" -m nyanya_agent.telegram_bridge "$@"
