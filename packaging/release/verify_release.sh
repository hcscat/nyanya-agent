#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

pack_args=(--dry-run --json)
if [ "$#" -eq 1 ] && [ "$1" = "--skip-build" ]; then
  pack_args+=(--ignore-scripts)
elif [ "$#" -ne 0 ]; then
  echo "Usage: verify_release.sh [--skip-build]" >&2
  exit 2
fi

umask 077
NYANYA_VERIFY_DIR="$(mktemp -d)"
export NYANYA_VERIFY_DIR
trap 'rm -rf "$NYANYA_VERIFY_DIR"' EXIT

failures=0

fail() {
  echo "[FAIL] $*"
  failures=$((failures + 1))
}

ok() {
  echo "[OK] $*"
}

check_required_path() {
  local path="$1"
  if [ -e "$path" ]; then
    ok "required path exists: $path"
  else
    fail "missing required path: $path"
  fi
}

while IFS= read -r path; do
  case "$path" in
    ""|\#*) continue ;;
  esac
  check_required_path "$path"
done < packaging/release/package-allowlist.txt

while IFS= read -r pattern; do
  case "$pattern" in
    ""|\#*) continue ;;
  esac
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    tracked_matches="$(git ls-files -- "$pattern" || true)"
  else
    tracked_matches=""
  fi
  if [ -n "$tracked_matches" ]; then
    echo "$tracked_matches"
    fail "denylisted path is tracked by git: $pattern"
  else
    ok "denylisted path is not tracked: $pattern"
  fi
done < packaging/release/package-denylist.txt

python3 -m compileall -q src/nyanya_agent
ok "python modules compile"

bash -n packaging/install/install.sh
bash -n packaging/install/uninstall.sh
bash -n packaging/release/generate_checksums.sh
bash -n scripts/backup_state.sh
bash -n scripts/restore_state.sh
ok "shell scripts parse"

if command -v npm >/dev/null 2>&1; then
  npm pack "${pack_args[@]}" >"$NYANYA_VERIFY_DIR/npm-pack.json"
  if python3 packaging/release/package_checks.py manifest "$NYANYA_VERIFY_DIR/npm-pack.json"
  then
    ok "npm pack includes required assets, resolves documentation links and excludes private/generated paths"
  else
    fail "npm package contents are incomplete or unsafe"
  fi
else
  echo "[WARN] npm not found; skipped npm pack dry-run"
fi

tracked_paths=()
while IFS= read -r -d '' path; do
  if [ -f "$path" ]; then
    tracked_paths+=("$path")
  fi
done < <(git ls-files --cached --others --exclude-standard -z)

python3 packaging/release/package_checks.py privacy "$NYANYA_VERIFY_DIR" "${tracked_paths[@]}"

if [ -s "$NYANYA_VERIFY_DIR/personal-data-scan.txt" ]; then
  sed -n '1,100p' "$NYANYA_VERIFY_DIR/personal-data-scan.txt"
  fail "personal/default workspace path, email, tailnet hostname, or long identifier found in public worktree files"
else
  ok "all public worktree files contain no personal/default workspace path, email, tailnet hostname, or long identifier"
fi

if [ -s "$NYANYA_VERIFY_DIR/secret-scan.txt" ]; then
  sed -n '1,100p' "$NYANYA_VERIFY_DIR/secret-scan.txt"
  fail "potential secret found in public worktree files"
else
  ok "all public worktree files contain no token-like or private-key values"
fi

package_version="$(node -p "require('./package.json').version")"
lock_version="$(node -p "require('./package-lock.json').version")"
python_version="$(python3 -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')"
if [ "$package_version" = "$lock_version" ] && [ "$package_version" = "$python_version" ]; then
  ok "package, lock, and Python versions match: $package_version"
else
  fail "version mismatch: package=$package_version lock=$lock_version python=$python_version"
fi

if [ "$failures" -gt 0 ]; then
  echo "Release verification failed: $failures issue(s)."
  exit 1
fi

echo "Release verification passed."
