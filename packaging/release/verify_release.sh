#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

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

python3 -m py_compile \
  src/nyanya_agent/runtime_paths.py \
  src/nyanya_agent/core.py \
  src/nyanya_agent/bridge_common.py \
  src/nyanya_agent/discord_bridge.py \
  src/nyanya_agent/telegram_bridge.py \
  src/nyanya_agent/dashboard_api.py \
  src/nyanya_agent/dashboard_store.py \
  src/nyanya_agent/manager.py \
  src/nyanya_agent/memory_worker.py
ok "python modules compile"

bash -n packaging/install/install.sh
bash -n packaging/install/uninstall.sh
bash -n packaging/release/generate_checksums.sh
ok "shell scripts parse"

if command -v npm >/dev/null 2>&1; then
  npm pack --dry-run >/tmp/nyanya-npm-pack.txt
  if grep -E '(^|/)(\.env|data/|logs/|run/|downloads/|docs/private/)' /tmp/nyanya-npm-pack.txt >/dev/null; then
    fail "npm pack dry-run includes private/generated paths"
  else
    ok "npm pack dry-run excludes private/generated paths"
  fi
else
  echo "[WARN] npm not found; skipped npm pack dry-run"
fi

if rg --glob '!packaging/release/verify_release.sh' -n "DISCORD_BOT_TOKEN=.+|NYANYA_DISCORD_BOT_TOKEN=.+|OPENAI_API_KEY=.+|AIza[0-9A-Za-z_-]{20,}|ghp_[0-9A-Za-z_]{20,}|sk-[A-Za-z0-9_-]{20,}" \
  README.md README.KO.md docs/*.md docs/*.html .github packaging package.json pyproject.toml cli src bin scripts prompts config .env.example >/tmp/nyanya-secret-scan.txt; then
  cat /tmp/nyanya-secret-scan.txt
  fail "potential secret found"
else
  ok "secret scan found no token-like values in release paths"
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
