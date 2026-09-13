"""Offline package checks; report file names, never matched private values."""

from __future__ import annotations

import json
from pathlib import Path
import posixpath
import re
import runpy
import sys
from urllib.parse import unquote, urlsplit


PRIVACY_PATTERNS = {
    "personal": re.compile(
        r"/Users/[A-Za-z0-9._-]+/"
        r"|\b[0-9]{17,20}\b"
        r"|[A-Za-z0-9._%+-]+@(gmail|naver|icloud|outlook|hotmail)\.[A-Za-z]{2,}"
        r"|tail[0-9]{4,}\.ts\.net",
        re.IGNORECASE,
    ),
    # Uppercase home-folder literals are operator defaults, unlike public author
    # branding or standard locations such as Library and .config. Command examples
    # must use an explicit /absolute/... or <workspace> placeholder.
    "workspace": re.compile(
        r'''\b(?:pathlib\.)?Path\.home\(\)\s*/\s*["'][A-Z][A-Z0-9_-]+["']'''
        r"|(?<![\w~])~/[A-Z][A-Z0-9_-]+(?=[/`'\"\s]|$)"
        r"|\bset_home\s+(?:discord_user_id|telegram_user_id|discord-user:discord_user_id)"
        r"\s+[A-Za-z][A-Za-z0-9_.-]*",
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
        r"|(?:DISCORD_BOT_TOKEN|NYANYA_DISCORD_BOT_TOKEN|OPENAI_API_KEY)=.+"
    ),
}

REQUIRED_ASSETS = {
    "src/nyanya_agent/execution_store.py",
    "src/nyanya_agent/task_service.py",
    "src/nyanya_agent/execution_adapters.py",
    "src/nyanya_agent/execution_runtime.py",
    "prompts/policy.md",
    "prompts/policy_technical.md",
    "prompts/policy_governance.md",
    "src/nyanya_agent/dashboard_static/index.html",
    "src/nyanya_agent/dashboard_static/styles.css",
    "src/nyanya_agent/dashboard_static/app.js",
    "scripts/mark_dist_executable.js",
    "packaging/release/package_checks.py",
}
# Load the dependency-free source helper without requiring an installed package
# or modifying sys.path; this script also runs from clean source distributions.
is_private_distribution_path = runpy.run_path(str(
    Path(__file__).resolve().parents[2] / "src/nyanya_agent/distribution_copy.py"
))["is_private_distribution_path"]
MARKDOWN_LINK = re.compile(r"\[[^\]\n]+\]\(([^)\n]+)\)")


def scan_text(text: str) -> set[str]:
    findings = {kind for kind, pattern in PRIVACY_PATTERNS.items() if pattern.search(text)}
    if "workspace" in findings:
        findings.remove("workspace")
        findings.add("personal")
    return findings


def write_privacy_reports(output: Path, paths: list[str]) -> None:
    findings: dict[str, list[str]] = {"personal": [], "secret": []}
    for raw in sorted(set(paths)):
        data = Path(raw).read_bytes()
        if b"\0" in data:
            continue
        for kind in scan_text(data.decode("utf-8", errors="ignore")):
            findings[kind].append(raw)
    for kind, matches in findings.items():
        filename = "personal-data-scan.txt" if kind == "personal" else "secret-scan.txt"
        (output / filename).write_text("".join(f"{path}\n" for path in matches), encoding="utf-8")


def package_errors(root: Path, paths: set[str]) -> list[str]:
    errors = [f"missing package asset: {path}" for path in sorted(REQUIRED_ASSETS - paths)]
    for path in sorted(paths):
        if is_private_distribution_path(path):
            errors.append(f"private/generated package path: {path}")
            continue
        if not path.endswith(".md"):
            continue
        text = (root / path).read_text(encoding="utf-8")
        for match in MARKDOWN_LINK.finditer(text):
            target = urlsplit(match.group(1).strip().split()[0].strip("<>"))
            if target.scheme or target.netloc or not target.path:
                continue
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(path), unquote(target.path)))
            if resolved not in paths and not any(item.startswith(resolved + "/") for item in paths):
                # Only print the public source location, not potentially private link values.
                line = text.count("\n", 0, match.start()) + 1
                errors.append(f"unpackaged relative link: {path}:{line}")
    return errors


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "privacy":
        write_privacy_reports(Path(sys.argv[2]), sys.argv[3:])
        return 0
    if len(sys.argv) == 3 and sys.argv[1] == "manifest":
        package = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))[0]
        errors = package_errors(Path.cwd(), {item["path"] for item in package["files"]})
        for error in errors:
            print(error, file=sys.stderr)
        return int(bool(errors))
    print("Usage: package_checks.py manifest <npm-pack.json> | privacy <report-dir> [files...]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
