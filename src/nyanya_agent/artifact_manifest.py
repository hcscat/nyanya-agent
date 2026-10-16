"""Record exact public artifact contents without local machine identifiers."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from pathlib import Path, PurePosixPath
import stat
import subprocess

MANIFEST_NAME = 'artifact-manifest.json'


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode('utf-8')


def source_revision(source: Path) -> dict:
    try:
        def git(*args):
            return subprocess.check_output(['git', '-C', str(source), *args], stderr=subprocess.DEVNULL,
                                           timeout=10, text=True).strip()
        if Path(git('rev-parse', '--show-toplevel')).resolve() != source.resolve():
            return {'commit': None, 'dirty': None}
        return {'commit': git('rev-parse', 'HEAD'), 'dirty': bool(git('status', '--porcelain'))}
    except (OSError, subprocess.SubprocessError):
        return {'commit': None, 'dirty': None}


def _entry(root: Path, relative: str) -> dict:
    parts = PurePosixPath(relative).parts
    if not parts or PurePosixPath(relative).is_absolute() or '..' in parts or '\\' in relative:
        raise ValueError('Invalid artifact path')
    target = root
    for part in parts:
        target = target / part
        if target.is_symlink():
            raise ValueError('Symlinks are not supported in release artifacts')
    mode = target.stat().st_mode
    if not stat.S_ISREG(mode):
        raise ValueError('Artifact entries must be regular files')
    digest = hashlib.sha256()
    with target.open('rb') as stream:
        for block in iter(lambda: stream.read(128 * 1024), b''):
            digest.update(block)
    return {'sha256': digest.hexdigest(), 'size': target.stat().st_size, 'mode': stat.S_IMODE(mode)}


def write_manifest(root: Path, source: Path) -> dict:
    # Also support the dependency-free source installer entry point.
    import runpy
    is_private_distribution_path = runpy.run_path(str(
        Path(__file__).with_name("distribution_copy.py")
    ))["is_private_distribution_path"]

    files = {}
    for item in sorted(root.rglob('*')):
        relative = item.relative_to(root).as_posix()
        if item.is_symlink():
            raise ValueError('Symlinks are not supported in release artifacts')
        if item.is_file() and relative != MANIFEST_NAME:
            if is_private_distribution_path(relative):
                raise ValueError('Private material in release artifact')
            files[relative] = _entry(root, relative)
    record = {'schema_version': 1, 'version': json.loads((root / 'package.json').read_text())['version'],
              'source': source_revision(source), 'files': files}
    record['artifact_id'] = hashlib.sha256(_canonical(record)).hexdigest()
    with (root / MANIFEST_NAME).open('x', encoding='utf-8') as stream:
        json.dump(record, stream, sort_keys=True, indent=2)
        stream.write('\n')
    return record


_EGG_METADATA = frozenset({
    'PKG-INFO', 'SOURCES.txt', 'dependency_links.txt', 'entry_points.txt',
    'requires.txt', 'top_level.txt',
})


def _generated_entry(relative: str, expected: dict) -> str | None:
    """Classify only known generated paths; build copies must match their source."""
    path = PurePosixPath(relative)
    parts = path.parts
    if (len(parts) == 3 and parts[:2] == ('src', 'nyanya_agent.egg-info')
            and parts[2] in _EGG_METADATA):
        return 'metadata'
    if path.parent.name == '__pycache__':
        match = re.fullmatch(r'(.+)\.cpython-[0-9]+(?:\.opt-[12])?\.pyc', path.name)
        if match:
            source = (path.parent.parent / (match[1] + '.py')).as_posix()
            if source in expected:
                return 'bytecode'
            if source.startswith('build/lib/') and ('src/' + source.removeprefix('build/lib/')) in expected:
                return 'bytecode'
    if relative.startswith('build/lib/'):
        source = 'src/' + relative.removeprefix('build/lib/')
        if source in expected:
            return source
    return None


def _valid_record(record) -> bool:
    if not isinstance(record, dict) or set(record) != {'schema_version', 'version', 'source', 'files', 'artifact_id'}:
        return False
    if type(record['schema_version']) is not int or record['schema_version'] != 1:
        return False
    if not isinstance(record['version'], str) or not record['version']:
        return False
    identity = record['artifact_id']
    if not isinstance(identity, str) or not re.fullmatch('[0-9a-f]{64}', identity):
        return False
    source = record['source']
    if not isinstance(source, dict) or set(source) != {'commit', 'dirty'}:
        return False
    if source['commit'] is not None and (
        not isinstance(source['commit'], str) or not re.fullmatch('[0-9a-f]{40}|[0-9a-f]{64}', source['commit'])
    ):
        return False
    if source['dirty'] is not None and type(source['dirty']) is not bool:
        return False
    files = record['files']
    if not isinstance(files, dict) or 'package.json' not in files or MANIFEST_NAME in files:
        return False
    import runpy
    private_path = runpy.run_path(str(Path(__file__).with_name('distribution_copy.py')))['is_private_distribution_path']
    for relative, entry in files.items():
        if (not isinstance(relative, str) or PurePosixPath(relative).as_posix() != relative
                or private_path(relative)):
            return False
        if not isinstance(entry, dict) or set(entry) != {'sha256', 'size', 'mode'}:
            return False
        if not isinstance(entry['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', entry['sha256']):
            return False
        if type(entry['size']) is not int or entry['size'] < 0:
            return False
        if type(entry['mode']) is not int or not 0 <= entry['mode'] <= 0o7777:
            return False
    return True


def verify_manifest(root: Path) -> list[str]:
    """Verify recorded sources, allowing narrowly named local Python build outputs.

    Bytecode and egg metadata are not source provenance or privacy evidence.
    Build/lib copies must match recorded sources; unexpected files still fail.
    """
    try:
        manifest = root / MANIFEST_NAME
        info = manifest.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 4_000_000:
            return ['Invalid or incomplete artifact manifest']
        record = json.loads(manifest.read_text(encoding='utf-8'))
        if not _valid_record(record):
            return ['Invalid or incomplete artifact manifest']
        identity = record.pop('artifact_id')
        if hashlib.sha256(_canonical(record)).hexdigest() != identity:
            return ['Manifest identity mismatch']
        expected = record['files']
        actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if not p.is_dir() or p.is_symlink()}
        actual.discard(MANIFEST_NAME)
        errors = ['Artifact file set differs'] if set(expected) - actual else []
        for relative, original in expected.items():
            if _entry(root, relative) != original:
                errors.append(f'Artifact content or mode differs: {relative}')
        for relative in sorted(actual - set(expected)):
            generated = _generated_entry(relative, expected)
            if generated is None:
                errors.append('Artifact file set differs')
                continue
            entry = _entry(root, relative)  # Generated entries may not be symlinks or special files.
            if generated == 'bytecode':
                with (root / relative).open('rb') as stream:
                    if stream.read(4) != importlib.util.MAGIC_NUMBER:
                        errors.append(f'Invalid generated Python bytecode: {relative}')
            if generated not in {'metadata', 'bytecode'}:
                original = expected[generated]
                # Setuptools normalizes copied public files (including 0600/0755) to 0644.
                safe_mode = not entry['mode'] & 0o7022 and entry['mode'] in {original['mode'], 0o644}
                same_content = entry['sha256'] == original['sha256'] and entry['size'] == original['size']
                if not safe_mode or not same_content:
                    errors.append(f'Generated build copy differs: {relative}')
        return list(dict.fromkeys(errors))
    except (OSError, ValueError, KeyError, TypeError):
        return ['Invalid or incomplete artifact manifest']
