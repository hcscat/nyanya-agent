#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
NyaNya Agent uninstaller

Usage:
  uninstall.sh [options]

Options:
  --install-dir PATH  Install directory. Default: ~/.local/share/nyanya-agent
  --bin-dir PATH      Command directory. Default: ~/.local/bin
  --purge-data        Remove install directory including local config/data.
  --help              Show this help.
USAGE
}

INSTALL_DIR="${NYANYA_INSTALL_DIR:-$HOME/.local/share/nyanya-agent}"
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

if [ "$PURGE_DATA" -eq 1 ]; then
  rm -rf "$INSTALL_DIR"
  echo "Removed install directory: $INSTALL_DIR"
else
  echo "Commands removed. Install directory kept: $INSTALL_DIR"
  echo "Run with --purge-data to remove local config/data as well."
fi
