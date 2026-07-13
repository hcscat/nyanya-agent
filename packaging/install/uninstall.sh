#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
NyaNya Agent uninstaller

Usage:
  uninstall.sh [options]

Options:
  --install-dir PATH  Code directory. Default: ~/.local/lib/nyanya-agent
  --state-dir PATH    State directory. OS-specific default.
  --bin-dir PATH      Command directory. Default: ~/.local/bin
  --purge-data        Remove install directory including local config/data.
  --help              Show this help.
USAGE
}

INSTALL_DIR="${NYANYA_INSTALL_DIR:-$HOME/.local/lib/nyanya-agent}"
if [ "$(uname -s)" = "Darwin" ]; then
  DEFAULT_STATE_DIR="$HOME/Library/Application Support/NyaNya Agent"
else
  DEFAULT_STATE_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/nyanya-agent"
fi
STATE_DIR="${NYANYA_HOME:-$DEFAULT_STATE_DIR}"
BIN_DIR="${NYANYA_BIN_DIR:-$HOME/.local/bin}"
PURGE_DATA=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --install-dir)
      INSTALL_DIR="${2:?missing value for --install-dir}"
      shift 2
      ;;
    --bin-dir)
      BIN_DIR="${2:?missing value for --bin-dir}"
      shift 2
      ;;
    --state-dir)
      STATE_DIR="${2:?missing value for --state-dir}"
      shift 2
      ;;
    --purge-data)
      PURGE_DATA=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

for command in nyanya nyanya-agent nyanyactl nyanya-discord nyanya-telegram nyanya-dashboard nyanya-memory-worker; do
  rm -f "$BIN_DIR/$command"
done

if [ -x "$STATE_DIR/.venv/bin/python" ] && [ -d "$INSTALL_DIR/src/nyanya_agent" ]; then
  NYANYA_PROJECT_ROOT="$INSTALL_DIR" NYANYA_HOME="$STATE_DIR" \
    "$STATE_DIR/.venv/bin/python" -m nyanya_agent.manager uninstall-all >/dev/null 2>&1 || true
fi

rm -rf "$INSTALL_DIR"
echo "Removed code directory: $INSTALL_DIR"

if [ "$PURGE_DATA" -eq 1 ]; then
  rm -rf "$STATE_DIR"
  echo "Removed state directory: $STATE_DIR"
else
  echo "User state kept: $STATE_DIR"
  echo "Run with --purge-data to remove local config/data as well."
fi
