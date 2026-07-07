#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
NyaNya Agent installer

Usage:
  install.sh [options]

Options:
  --source PATH        Install from a local checkout instead of the script repository.
  --install-dir PATH   Install directory. Default: ~/.local/share/nyanya-agent
  --bin-dir PATH       Command directory. Default: ~/.local/bin
  --repo-url URL       Git repository URL for clone installs.
  --force              Replace the existing install directory backup.
  --skip-deps          Skip Python package installation.
  --help               Show this help.

Environment:
  NYANYA_INSTALL_DIR
  NYANYA_BIN_DIR
  NYANYA_REPO_URL
USAGE
}

INSTALL_DIR="${NYANYA_INSTALL_DIR:-$HOME/.local/share/nyanya-agent}"
BIN_DIR="${NYANYA_BIN_DIR:-$HOME/.local/bin}"
REPO_URL="${NYANYA_REPO_URL:-https://github.com/hcscat/nyanya-agent.git}"
SOURCE_DIR=""
FORCE=0
SKIP_DEPS=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --source)
      SOURCE_DIR="${2:?missing value for --source}"
      shift 2
      ;;
    --install-dir)
      INSTALL_DIR="${2:?missing value for --install-dir}"
      shift 2
      ;;
    --bin-dir)
      BIN_DIR="${2:?missing value for --bin-dir}"
      shift 2
      ;;
    --repo-url)
      REPO_URL="${2:?missing value for --repo-url}"
      shift 2
      ;;
    --force)
      FORCE=1
      shift
      ;;
    --skip-deps)
      SKIP_DEPS=1
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

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

resolve_path() {
  python3 - "$1" <<'PY'
from pathlib import Path
import sys
print(Path(sys.argv[1]).expanduser().resolve(strict=False))
PY
}

copy_source() {
  local src="$1"
  local dst="$2"
  mkdir -p "$dst"
  tar \
    --exclude .git \
    --exclude .venv \
    --exclude .pytest_cache \
    --exclude .ruff_cache \
    --exclude __pycache__ \
    --exclude data \
    --exclude logs \
    --exclude run \
    --exclude downloads \
    --exclude docs/private \
    --exclude .env \
    -C "$src" -cf - . | tar -C "$dst" -xf -
}

write_launcher() {
  local name="$1"
  local module="$2"
  local path="$BIN_DIR/$name"
  cat > "$path" <<EOF
#!/usr/bin/env bash
set -euo pipefail
export NYANYA_PROJECT_ROOT="$INSTALL_DIR"
exec "$INSTALL_DIR/.venv/bin/python" -m "$module" "\$@"
EOF
  chmod 0755 "$path"
}

require_command python3
require_command tar

INSTALL_DIR="$(resolve_path "$INSTALL_DIR")"
BIN_DIR="$(resolve_path "$BIN_DIR")"
mkdir -p "$BIN_DIR"

TMP_DIR=""
if [ -z "$SOURCE_DIR" ]; then
  require_command git
  TMP_DIR="$(mktemp -d)"
  git clone --depth 1 "$REPO_URL" "$TMP_DIR/nyanya-agent"
  SOURCE_DIR="$TMP_DIR/nyanya-agent"
fi
SOURCE_DIR="$(resolve_path "$SOURCE_DIR")"

if [ ! -f "$SOURCE_DIR/pyproject.toml" ] || [ ! -d "$SOURCE_DIR/src/nyanya_agent" ]; then
  echo "Source path does not look like a nyanya-agent checkout: $SOURCE_DIR" >&2
  exit 1
fi

if [ -d "$INSTALL_DIR" ]; then
  BACKUP_DIR="${INSTALL_DIR}.backup.$(date +%Y%m%d%H%M%S)"
  if [ "$FORCE" -eq 1 ]; then
    rm -rf "$BACKUP_DIR"
  fi
  mv "$INSTALL_DIR" "$BACKUP_DIR"
  echo "Existing install moved to: $BACKUP_DIR"
fi

copy_source "$SOURCE_DIR" "$INSTALL_DIR"

if [ ! -f "$INSTALL_DIR/.env" ] && [ -f "$INSTALL_DIR/.env.example" ]; then
  cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
  chmod 0600 "$INSTALL_DIR/.env"
fi

python3 -m venv "$INSTALL_DIR/.venv"
if [ "$SKIP_DEPS" -eq 0 ]; then
  "$INSTALL_DIR/.venv/bin/python" -m pip install --upgrade pip
  "$INSTALL_DIR/.venv/bin/python" -m pip install -e "$INSTALL_DIR[bots,dashboard]"
fi

write_launcher nyanya nyanya_agent.core
write_launcher nyanya-agent nyanya_agent.core
write_launcher nyanyactl nyanya_agent.manager
write_launcher nyanya-discord nyanya_agent.discord_bridge
write_launcher nyanya-telegram nyanya_agent.telegram_bridge
write_launcher nyanya-dashboard nyanya_agent.dashboard_api
write_launcher nyanya-memory-worker nyanya_agent.memory_worker

if [ -n "$TMP_DIR" ]; then
  rm -rf "$TMP_DIR"
fi

cat <<EOF
NyaNya Agent installed.

Install dir: $INSTALL_DIR
Command dir: $BIN_DIR

Next:
  nyanya --check
  nyanya

If '$BIN_DIR' is not on PATH, add it to your shell profile.
EOF
