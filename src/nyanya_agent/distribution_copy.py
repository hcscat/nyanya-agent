"""Copy only the package manifest's public assets for source installers."""

import json
from pathlib import Path, PurePosixPath
import re
import shutil
import sys


def is_private_distribution_path(path: str) -> bool:
    """Reject local state even when an overbroad manifest explicitly selects it."""
    relative = PurePosixPath(path.replace("\\", "/"))
    parts = tuple(part.lower() for part in relative.parts)
    if relative.is_absolute() or ".." in parts or not parts:
        return True
    name = parts[-1]
    normalized = "/".join(parts)
    if any(part in {
        ".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", ".ruff_cache",
        "data", "logs", "run", "sessions", "downloads", "tmp", "private", ".secrets",
        "backups", "credentials", "secrets", "keys", "reports",
    } for part in parts[:-1]):
        return True
    if name in {"agents.md", "agents.override.md"}:
        return True
    if name.startswith(".env") and relative.name not in {".env.example", ".env.sample"}:
        return True
    if normalized in {
        "config/user_workspaces.json", "prompts/local_system.md",
        "docs/operational_rollout_20260913.md",
    }:
        return True
    if normalized.startswith((
        "docs/nyanya_orca_remote_agent_office_plan_", "docs/phase0_baseline_",
        "docs/nyanya_remote_access_security_build_plan_",
    )) or (parts[0] == "docs" and name.endswith(".html")):
        return True
    if parts[0] == "config" and (
        name.startswith(("local.", "private.")) or ".local." in name or ".private." in name
        or name.startswith("user_workspaces.json.")
        or (name.startswith(("credentials", "secrets")) and name.endswith(".json"))
    ):
        return True
    if parts[0] == "prompts" and name.startswith("local_") and name.endswith(".md"):
        return True
    if name in {"credentials", "credentials.json", "credentials.yaml", "credentials.yml",
                "secrets.json", "secrets.yaml", "secrets.yml", "auth.json", "cookies.txt"}:
        return True
    return bool(re.search(
        r"(?:^id_(?:rsa|dsa|ecdsa|ed25519)(?:\.|$)"
        r"|\.(?:pem|key|p12|pfx|db|sqlite|sqlite3)(?:$|[.-])"
        r"|\.(?:log|pid|bak|backup)$)", name,
    ))


def copy_distribution(source: Path, destination: Path) -> None:
    source = source.resolve(strict=True)
    destination = destination.resolve(strict=False)
    if destination == source or destination.is_relative_to(source):
        raise ValueError("Install destination must be outside the source tree")
    manifest = json.loads((source / "package.json").read_text(encoding="utf-8"))
    selected: set[Path] = set()
    for pattern in [*manifest["files"], "package.json", "package-lock.json", "LICENSE", "README.md"]:
        if Path(pattern).is_absolute() or ".." in Path(pattern).parts:
            raise ValueError("Invalid package asset pattern")
        for item in source.glob(pattern):
            if item.is_symlink():
                raise ValueError("Symlinked package assets are not supported")
            if item.is_file():
                selected.add(item)
    # Validate everything before writing, including parent-directory symlinks.
    for item in selected:
        if not item.resolve().is_relative_to(source):
            raise ValueError("Package asset escapes the source tree")
        relative = item.relative_to(source)
        if is_private_distribution_path(relative.as_posix()):
            raise ValueError("Private state cannot be a package asset")
    destination.mkdir(parents=True, exist_ok=True)
    for item in sorted(selected):
        target = destination / item.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as output, item.open("rb") as original:
            shutil.copyfileobj(original, output)
        shutil.copymode(item, target)


if __name__ == "__main__":
    try:
        copy_distribution(Path(sys.argv[1]), Path(sys.argv[2]))
    except Exception as exc:
        print(f"Source installation copy failed ({type(exc).__name__})", file=sys.stderr)
        raise SystemExit(1) from None
