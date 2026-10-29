"""Request-scoped provider input and least-privilege child environments.

This is a conservative transfer filter, not an OS sandbox or a complete secret
classifier. Authentication files reachable through HOME remain a CLI boundary.
"""

from contextlib import contextmanager
import io
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat

from nyanya_agent.task_outcomes import SafeOperationError


_SECRET_KEY = re.compile(
    r"(?i)(?:api[_-]?key|access[_-]?token|refresh[_-]?token|auth[_-]?token|"
    r"password|passwd|client[_-]?secret|private[_-]?key|credential|"
    r"(?:discord|dashboard|telegram|bot)[_-]?token|(?:^|[_-])token(?:$|[_-])|"
    r"authorization|cookie|connection[_-]?string|secret)"
)
_ASSIGNMENT = re.compile(
    '(?ix)(?<![\\w.-])["\']?([\\w.-]+)["\']?[^\\S\\r\\n]*[:=][^\\S\\r\\n]*(?:["\']([^"\'\\r\\n]*)["\']|([^\\s,;}\\r\\n]+))'
)
_INDENTED_ASSIGNMENT = re.compile(
    '(?im)^[ \\t]*["\']?([\\w.-]+)["\']?[ \\t]*:[ \\t]*(?=\\r?\\n[ \\t]+(?:["\']([^"\'\\r\\n]*)["\']|([^\\s,;}\\r\\n]+)))'
)
_SECRET_LITERAL = re.compile(
    r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----|"
    r"\b(?:sk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|"
    r"AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,})\b|"
    r"(?i:authorization[\"']?\s*[:=]\s*[\"']?(?:bearer|basic)\s+\S+)|"
    r"(?i:(?<![a-z0-9+.-])[a-z][a-z0-9+.-]*://[^\s/:]+:[^\s/@]+@)"
)
_PLACEHOLDERS = {"", "none", "null", "false", "true", "changeme", "change-me", "example", "placeholder"}
_BASE_ENV = frozenset({
    "PATH", "HOME", "USER", "LOGNAME", "SHELL", "LANG", "LANGUAGE", "LC_ALL", "LC_CTYPE",
    "TMPDIR", "TMP", "TEMP", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT",
    "SSL_CERT_FILE", "SSL_CERT_DIR",
})
_PROVIDER_ENV = {
    "codex": frozenset({"OPENAI_API_KEY", "OPENAI_ORG_ID", "OPENAI_PROJECT_ID", "CODEX_HOME"}),
    "agy": frozenset({"GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_CLOUD_PROJECT"}),
}


def child_environment(provider=None, environ=None):
    """Never inherit connector, dashboard, Python injection or unrelated auth vars."""
    source = os.environ if environ is None else environ
    if provider is not None and provider not in _PROVIDER_ENV:
        raise SafeOperationError("Unknown provider environment policy")
    allowed = _BASE_ENV | _PROVIDER_ENV.get(provider, frozenset())
    return {key: value for key, value in source.items() if key.upper() in allowed}


def _filled(value):
    value = str(value).strip()
    if value.casefold() in _PLACEHOLDERS or re.fullmatch(r"\$\{[A-Z_][A-Z0-9_]*\}|<[A-Z][A-Z0-9_-]*>", value):
        return False
    # References to environment lookups are source code, not embedded credentials.
    if value.startswith(("os.getenv(", "os.environ", "process.env.", "getenv(")):
        return False
    return True



_SECRET_REFERENCE_KEY = re.compile(r"(?i)(?:[_-]file|[_-]path)$")
_SECRET_REFERENCE_PATH = re.compile(r"^[A-Za-z0-9_~./${}\\:-]+$")
PRIVATE_PATH_PARTS = frozenset({
    ".git", ".env", ".venv", "node_modules", "__pycache__", ".codex", ".gemini",
    ".ssh", ".aws", "data", "logs", "run", "sessions", "private", "downloads",
    "user_workspaces.json", "local_system.md", "credentials.json", "auth.json",
    "backups", "backup", "reports",
})
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
_UPLOAD_TEXT_SUFFIXES = frozenset({
    "", ".txt", ".md", ".rst", ".csv", ".tsv", ".json", ".jsonl", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".conf", ".xml", ".html", ".css", ".js", ".ts",
    ".jsx", ".tsx", ".py", ".sh", ".sql", ".r",
})
_UPLOAD_PRIVATE_SUFFIXES = frozenset({".pem", ".key", ".token", ".db", ".sqlite", ".sqlite3", ".log", ".bak", ".backup"})
_LOCAL_HOME_PATH = re.compile(
    r"(?i)(?:/(?:Users|home)/[^\s/]+|[A-Z]:[\\/](?:Users|Documents and Settings)[\\/]|~[\\/])"
)
_BINARY_HEADERS = (b"%PDF-", b"PK\x03\x04", b"\x1f\x8b", b"\x7fELF", b"MZ", b"\x89PNG")


def private_path_part(part):
    name = part.casefold()
    return (
        name in PRIVATE_PATH_PARTS
        or name.startswith(("backup-", "backup_", "backups-", "backups_", "report-", "report_", "reports-", "reports_"))
        or name.startswith(".env")
        or name.startswith("agents") and (
            name.endswith(".md") or ".md." in name or name.endswith((".bak", ".backup", "~"))
        )
    )


def _secret_assignment(key, value):
    if not _SECRET_KEY.search(str(key)) or not _filled(value):
        return False
    if isinstance(value, str) and _SECRET_REFERENCE_KEY.search(str(key)):
        # A file reference never grants access to the referenced credential.
        if _SECRET_REFERENCE_PATH.fullmatch(value) and (
            "/" in value or "\\" in value
            or Path(value).suffix.casefold() in {".token", ".key", ".pem", ".json", ".txt", ".env"}
        ):
            return False
    return True


def sensitive_content(content, environ=None):
    """Inspect contents, structured credential fields, and known local secret values."""
    if _SECRET_LITERAL.search(content):
        return True
    source = os.environ if environ is None else environ
    if any(len(value) >= 8 and _secret_assignment(key, value) and value in content for key, value in source.items()):
        return True
    try:
        parsed = json.loads(content)
    except (ValueError, TypeError):
        parsed = None

    def sensitive_value(value):
        if isinstance(value, dict):
            return any(
                (item is not None and _secret_assignment(key, item)) or sensitive_value(item)
                for key, item in value.items()
            )
        if isinstance(value, list):
            return any(sensitive_value(item) for item in value)
        return False

    if sensitive_value(parsed):
        return True
    return any(
        _secret_assignment(match[1], match[2] if match[2] is not None else match[3])
        for match in _ASSIGNMENT.finditer(content)
    ) or any(
        _secret_assignment(match[1], match[2] if match[2] is not None else match[3])
        for match in _INDENTED_ASSIGNMENT.finditer(content)
    )


def validate_provider_prompt(prompt):
    if sensitive_content(prompt):
        raise SafeOperationError("Provider input contains sensitive material; use sanitized text or files")


def inline_context_only(request):
    """Honor explicit input boundaries, independently of output/write constraints."""
    if request is None:
        return False
    coordinated = (
        r"파일\s*(?:을|은|에)?\s*(?:읽|열|접근하|탐색하|조회하|열람하)거나\s*"
        r"(?:(?:수정|변경|편집|삭제|생성)\s*(?:하거나|및|또는|/|,)\s*)*"
        r"(?:수정|변경|편집|삭제|생성)하지\s*(?:말|마|않)"
    )
    for match in re.finditer(coordinated, request):
        # A quoted prohibition that is explicitly negated is not a read ban.
        tail = request[match.end():match.end() + 80]
        denied_quote = (
            r"^(?:(?:으)?라는\s*(?:뜻|의미|요청|요구|지시)(?:은|는|이|가)?\s*(?:아니|없)"
            r"|라고\s*(?:한|하는)\s*(?:건|것)(?:은|이)?\s*아니"
            r"|는\s*(?:게|것|건)(?:은|이)?\s*아니)"
        )
        if not re.search(denied_quote, tail):
            return True
    patterns = (
        r"파일\s*(?:을|은|에)?\s*(?:읽|열)(?:지\s*(?:말|마|않)|기(?:\s*(?:나|와|및)\s*[^.!?\n]{0,40})?\s*(?:없이|금지))",
        r"파일\s*(?:을|은|에)?\s*(?:접근|탐색|조회|열람)(?:하지\s*(?:말|마|않)|(?:\s*(?:이나|나|과|및)\s*[^.!?\n]{0,40})?\s*(?:없이|금지))",
        r"\bwithout\s+(?:\w+\s+){0,3}(?:reading|accessing|opening|scanning)\b[^.!?\n]{0,60}\bfiles?\b",
        r"\b(?:do\s+not|don't|never)\s+(?:read|access|open|scan)\b[^.!?\n]{0,60}\bfiles?\b",
        r"\bno\s+(?:local\s+|workspace\s+)?file(?:system)?\s+(?:reads?|reading|access|inspection)\b",
        r"(?:아래|다음|위|제공한|제공된|붙여\s*넣은|메시지에\s*있는)\s*(?:코드|내용|텍스트)만",
        r"\b(?:analy[sz]e|explain|review)\s+only\s+(?:the\s+)?(?:code|text|snippet)\s+(?:below|above|in\s+(?:this|the)\s+message)\b",
        r"\b(?:use|using)\s+only\s+(?:the\s+)?(?:code|text|snippet)\s+(?:below|above|in\s+(?:this|the)\s+message)\b",
    )
    return any(re.search(pattern, request, re.IGNORECASE) for pattern in patterns)


def context_references(request, root):
    """Return bounded literal paths and directory intent, without filesystem access."""
    if request is None or inline_context_only(request):
        return [], request is not None
    tokens = re.findall(r"[\w./@+~-]+", request, re.UNICODE)
    directory_tokens = set()
    for pattern in (
        r"\b(?:directory|folder)\s+[`'\"]?([\w./@+~-]+)",
        r"(?<![\w./@+~-])([\w./@+~-]+)[`'\"]?\s*(?:directory\b|folder\b|디렉터리|디렉토리|폴더)",
    ):
        directory_tokens.update(token.rstrip(".,:;").casefold() for token in re.findall(pattern, request, re.IGNORECASE))
    file_references = []
    directory_references = []
    attempts = 0
    for token in tokens:
        trailing_slash = token.endswith("/")
        token = token.rstrip(".,:;")
        token = re.sub(r"(\.[A-Za-z0-9]{1,16})(?:를|을|은|는|만|의|에)$", r"\1", token)
        directory_intent = "/" in token or token.casefold() in directory_tokens
        if not directory_intent and "." not in token:
            continue
        attempts += 1
        file_reference = not trailing_slash and token.casefold() not in directory_tokens
        if ".." in PurePosixPath(token).parts:
            continue
        if token.startswith("/"):
            try:
                token = Path(token).relative_to(Path(root)).as_posix()
            except ValueError:
                continue
        token = token.removeprefix("./").rstrip("/")
        if token == "." and directory_intent:
            token = ""
        if (token or directory_intent) and len(PurePosixPath(token).parts) <= 200:
            reference = (token, directory_intent)
            bucket = file_references if file_reference else directory_references
            if len(bucket) < 80 and reference not in bucket:
                bucket.append(reference)
    return (file_references + directory_references)[:80], attempts > 0


def select_context_paths(names, request, root):
    """Select literal scopes first, then filename topics and overview docs."""
    if request is None:  # Internal reviewed-plan callers still get the bounded baseline.
        return names
    if inline_context_only(request):
        return []
    references, has_explicit = context_references(request, root)
    explicit = {name.casefold() for name, _ in references}
    directories = {name.casefold() for name, is_directory in references if is_directory}
    selected = []
    inferred = []
    tokens = re.findall(r"[\w./@+~-]+", request, re.UNICODE)
    topics = {token.casefold() for token in tokens if len(token) >= 3 and "/" not in token and "." not in token}
    for name in names:
        path = PurePosixPath(name)
        folded = name.casefold()
        components = set(re.split(r"[_\-.]", path.stem.casefold()))
        if (
            folded in explicit or path.name.casefold() in explicit
            or "" in directories or any(parent.as_posix().casefold() in directories for parent in path.parents)
        ):
            selected.append(name)
        elif components & topics:
            inferred.append(name)
    if has_explicit:
        return selected
    if selected or inferred:
        return selected + inferred
    overview = {"readme.md", "readme.txt", "docs/readme.md", "docs/architecture.md", "docs/architecture_and_roadmap.md"}
    return [name for name in names if name.casefold() in overview]


def _upload_private_part(part):
    # Automatic model context retains its broader PRIVATE_PATH_PARTS policy.
    ordinary = {"data", "logs", "run", "private", "downloads", "reports"}
    name = part.casefold()
    return (
        name.startswith(".") or name in PRIVATE_PATH_PARTS - ordinary
        or name.startswith(("backup-", "backup_", "backups-", "backups_"))
        or name.startswith("agents") and (name.endswith(".md") or ".md." in name)
    )


@contextmanager
def open_upload_file(root, value, *, max_bytes=None):
    """Freeze bounded bytes and inspect the whole supported document locally.

    privacy_counts requires a separate owner/hash/destination-bound confirmation.
    Unsupported or incompletely extracted documents fail closed. A zero pattern
    count is not a complete personal-information or DLP guarantee.
    """
    from nyanya_agent.upload_document_privacy import inspect_document
    if os.name != "posix":
        raise SafeOperationError("Secure uploads require POSIX no-follow file operations")
    limit = MAX_UPLOAD_BYTES if max_bytes is None else max_bytes
    if type(limit) is not int or limit < 1:
        raise SafeOperationError("Upload byte limit is unavailable")
    limit = min(limit, MAX_UPLOAD_BYTES)
    root = Path(root)
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        parts = Path(os.path.abspath(candidate)).relative_to(root).parts
    except ValueError as exc:
        raise SafeOperationError("Upload path is outside the registered workspace") from exc
    if not parts:
        raise SafeOperationError("Upload requires a regular file")
    if any(_upload_private_part(part) for part in parts) or Path(parts[-1]).suffix.casefold() in _UPLOAD_PRIVATE_SUFFIXES:
        raise SafeOperationError("Upload path contains private material")
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    child = None
    try:
        for part in parts[:-1]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        child = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        info = os.fstat(child)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise SafeOperationError("Upload requires a single-link regular file")
        if info.st_size > limit:
            raise SafeOperationError("Upload exceeds the byte bound")
        def identity(value):
            return dict(dev=value.st_dev, ino=value.st_ino, size=value.st_size,
                        mtime_ns=value.st_mtime_ns, ctime_ns=value.st_ctime_ns)
        original = identity(info)
        with os.fdopen(child, "rb") as source:
            child = None
            data = source.read(limit + 1)
            final = os.fstat(source.fileno())
        if len(data) > limit:
            raise SafeOperationError("Upload exceeds the byte bound")
        if len(data) != info.st_size or identity(final) != original:
            raise SafeOperationError("Upload changed while being inspected")
        report = inspect_document(data, parts[-1])
        with io.BytesIO(data) as stream:
            stream.sha256 = hashlib.sha256(data).hexdigest()
            stream.identity = original
            stream.size = len(data)
            stream.privacy_counts = dict(report.counts)
            yield stream
    finally:
        if child is not None:
            os.close(child)
        os.close(fd)
