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
  src/nyanya_agent/execution_store.py \
  src/nyanya_agent/adapter_runner.py \
  src/nyanya_agent/execution_adapters.py \
  src/nyanya_agent/execution_runtime.py \
  src/nyanya_agent/manager.py \
  src/nyanya_agent/memory_worker.py
ok "python modules compile"

bash -n packaging/install/install.sh
bash -n packaging/install/uninstall.sh
bash -n packaging/release/generate_checksums.sh
bash -n scripts/backup_state.sh
bash -n scripts/restore_state.sh
ok "shell scripts parse"

if command -v npm >/dev/null 2>&1; then
  npm pack --dry-run --json >/tmp/nyanya-npm-pack.json
  if node <<'NODE'
const fs = require("fs");
const result = JSON.parse(fs.readFileSync("/tmp/nyanya-npm-pack.json", "utf8"))[0];
const paths = new Set((result.files || []).map((file) => file.path));
const required = [
  "src/nyanya_agent/execution_store.py",
  "src/nyanya_agent/execution_adapters.py",
  "src/nyanya_agent/execution_runtime.py",
  "src/nyanya_agent/dashboard_static/index.html",
  "src/nyanya_agent/dashboard_static/styles.css",
  "src/nyanya_agent/dashboard_static/app.js",
];
const missing = required.filter((path) => !paths.has(path));
const privatePrefixes = ["data/", "logs/", "run/", "downloads/", "docs/private/"];
const privatePath = [...paths].find(
  (path) => path === ".env" || privatePrefixes.some((prefix) => path.startsWith(prefix))
);
const localReportPrefixes = ["docs/nyanya_orca_remote_agent_office_plan_", "docs/phase0_baseline_"];
const localReport = [...paths].find((path) => localReportPrefixes.some((prefix) => path.startsWith(prefix)));
if (missing.length || privatePath || localReport) {
  if (missing.length) console.error(`missing package assets: ${missing.join(", ")}`);
  if (privatePath) console.error(`private/generated package path: ${privatePath}`);
  if (localReport) console.error(`local planning/evidence document in package: ${localReport}`);
  process.exit(1);
}
NODE
  then
    ok "npm pack includes dashboard assets and excludes private/generated paths"
  else
    fail "npm package contents are incomplete or unsafe"
  fi
else
  echo "[WARN] npm not found; skipped npm pack dry-run"
fi

tracked_paths=()
while IFS= read -r -d '' path; do
  if [ -f "$path" ] && [ "$path" != "packaging/release/verify_release.sh" ]; then
    tracked_paths+=("$path")
  fi
done < <(git ls-files -z)

python3 - "${tracked_paths[@]}" <<'PY'
from pathlib import Path
import re
import sys

output_paths = {
    "personal": Path("/tmp/nyanya-personal-data-scan.txt"),
    "secret": Path("/tmp/nyanya-secret-scan.txt"),
}
patterns = {
    "personal": re.compile(
        r"/Users/[A-Za-z0-9._-]+/"
        r"|\b[0-9]{17,20}\b"
        r"|[A-Za-z0-9._%+-]+@(gmail|naver|icloud|outlook|hotmail)\.[A-Za-z]{2,}"
        r"|tail[0-9]{4,}\.ts\.net",
        re.IGNORECASE,
    ),
    "secret": re.compile(
        r"BEGIN (RSA|OPENSSH|EC|DSA) PRIVATE KEY"
        r"|AKIA[0-9A-Z]{16}"
        r"|github_pat_[A-Za-z0-9_]{20,}"
        r"|gh[pousr]_[A-Za-z0-9_]{20,}"
        r"|AIza[0-9A-Za-z_-]{20,}"
        r"|sk-[A-Za-z0-9_-]{20,}"
        r"|xox[baprs]-[A-Za-z0-9-]{20,}"
        r"|[MN][A-Za-z0-9_-]{23,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{20,}"
        r"|DISCORD_BOT_TOKEN=.+|NYANYA_DISCORD_BOT_TOKEN=.+|OPENAI_API_KEY=.+"
    ),
}
matches = {name: [] for name in patterns}

for raw_path in sys.argv[1:]:
    path = Path(raw_path)
    data = path.read_bytes()
    if b"\0" in data:
        continue
    text = data.decode("utf-8", errors="ignore")
    for name, pattern in patterns.items():
        if pattern.search(text):
            matches[name].append(raw_path)

for name, output_path in output_paths.items():
    content = "\n".join(matches[name])
    output_path.write_text(f"{content}\n" if content else "", encoding="utf-8")
PY

if [ -s /tmp/nyanya-personal-data-scan.txt ]; then
  sed -n '1,100p' /tmp/nyanya-personal-data-scan.txt
  fail "personal path, email, tailnet hostname, or long account/message identifier found in tracked files"
else
  ok "all tracked files contain no personal path, email, tailnet hostname, or long account/message identifier"
fi

if [ -s /tmp/nyanya-secret-scan.txt ]; then
  sed -n '1,100p' /tmp/nyanya-secret-scan.txt
  fail "potential secret found in tracked files"
else
  ok "all tracked files contain no token-like or private-key values"
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
