"""Additional original-workspace denial for model children, not a host sandbox."""

from contextlib import contextmanager
from contextvars import ContextVar
import json
from pathlib import Path
import sys

from nyanya_agent.task_outcomes import OutcomeSignal


_original = ContextVar("provider_original_workspace", default=None)


@contextmanager
def protect_original(root):
    token = _original.set(Path(root).resolve(strict=True))
    try:
        yield
    finally:
        _original.reset(token)


def isolated_command(command, cwd):
    root = _original.get()
    if root is None:
        return command
    sandbox = Path("/usr/bin/sandbox-exec")
    if sys.platform != "darwin" or not sandbox.is_file():
        raise OutcomeSignal("blocked", "Original-workspace isolation is unavailable on this platform.")
    scratch = Path(cwd).resolve(strict=True)
    if scratch == root or root in scratch.parents:
        raise OutcomeSignal("blocked", "Model scratch directory must be outside the original workspace.")
    # /var aliases and APFS firmlinks must not leave an alternate original path.
    roots = {str(root)}
    data_alias = Path("/System/Volumes/Data") / str(root).lstrip("/")
    if data_alias.is_dir() and data_alias.samefile(root):
        roots.add(str(data_alias))
    rules = "".join(
        "(deny file-read* file-write* (subpath " + json.dumps(value, ensure_ascii=False) + "))"
        for value in sorted(roots)
    )
    # Renaming an ancestor must not move the protected tree outside the rule.
    ancestors = {str(parent) for value in roots for parent in Path(value).parents}
    rules += "".join("(deny file-write* (literal " + json.dumps(value, ensure_ascii=False) + "))"
                     for value in sorted(ancestors))
    return [str(sandbox), "-p", "(version 1)(allow default)" + rules, *command]
