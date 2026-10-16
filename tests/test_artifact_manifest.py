import json
from pathlib import Path

from nyanya_agent.artifact_manifest import write_manifest, verify_manifest
from nyanya_agent.distribution_copy import copy_distribution


def test_manifest_binds_files_modes_and_provenance_without_absolute_paths(tmp_path):
    code = tmp_path / 'code'
    code.mkdir()
    (code / 'package.json').write_text(json.dumps({'version': '0.3.0'}))
    (code / 'hello.py').write_text('print("hello")\n')
    manifest = write_manifest(code, tmp_path)
    assert manifest['source'] == {'commit': None, 'dirty': None}
    assert str(tmp_path) not in (code / 'artifact-manifest.json').read_text()
    assert verify_manifest(code) == []
    (code / 'hello.py').write_text('print("changed")\n')
    assert verify_manifest(code)


def test_added_files_and_manifest_tampering_are_detected(tmp_path):
    (tmp_path / 'package.json').write_text(json.dumps({'version': '0.3.0'}))
    write_manifest(tmp_path, tmp_path)
    extra = tmp_path / 'unexpected.txt'
    extra.write_text('unexpected')
    assert verify_manifest(tmp_path) == ['Artifact file set differs']
    extra.unlink()
    path = tmp_path / 'artifact-manifest.json'
    record = json.loads(path.read_text())
    record['version'] = 'different'
    path.write_text(json.dumps(record))
    assert verify_manifest(tmp_path) == ['Manifest identity mismatch']


def test_distribution_copy_records_verified_public_artifact(tmp_path):
    source = Path(__file__).resolve().parents[1]
    target = tmp_path / 'release'
    copy_distribution(source, target)
    manifest = json.loads((target / 'artifact-manifest.json').read_text())
    assert manifest['source']['commit']
    assert 'AGENTS.md' not in manifest['files']
    assert verify_manifest(target) == []
    assert not (target / '.dev-state').exists()


def test_verifier_import_does_not_invalidate_copied_artifact(tmp_path):
    import os
    import subprocess
    import sys

    source = Path(__file__).resolve().parents[1]
    target = tmp_path / 'release'
    copy_distribution(source, target)
    env = dict(os.environ, PYTHONPATH=str(target / 'src'))
    env.pop('PYTHONDONTWRITEBYTECODE', None)
    result = subprocess.run([
        sys.executable, '-c',
        'import sys; from pathlib import Path; from nyanya_agent.artifact_manifest import verify_manifest; '
        'assert verify_manifest(Path(sys.argv[1])) == []', str(target),
    ], env=env, cwd=tmp_path, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert list(target.rglob('*.pyc'))


def test_only_known_python_build_outputs_are_permitted(tmp_path):
    import shutil

    (tmp_path / 'package.json').write_text(json.dumps({'version': '0.3.0'}))
    source = tmp_path / 'src/nyanya_agent/example.py'
    source.parent.mkdir(parents=True)
    source.write_text('print("fixture")\n')
    write_manifest(tmp_path, tmp_path)
    built = tmp_path / 'build/lib/nyanya_agent/example.py'
    built.parent.mkdir(parents=True)
    shutil.copy2(source, built)
    metadata = tmp_path / 'src/nyanya_agent.egg-info/PKG-INFO'
    metadata.parent.mkdir(parents=True)
    metadata.write_text('Metadata-Version: 2.4\nName: nyanya-agent\n')
    assert verify_manifest(tmp_path) == []
    built.write_text('print("modified")\n')
    assert verify_manifest(tmp_path) == ['Generated build copy differs: build/lib/nyanya_agent/example.py']
    shutil.copy2(source, built)
    (tmp_path / 'build/private.txt').write_text('unexpected fixture')
    assert verify_manifest(tmp_path) == ['Artifact file set differs']


def test_generated_paths_cannot_hide_unknown_sources_or_symlinks(tmp_path):
    (tmp_path / 'package.json').write_text(json.dumps({'version': '0.3.0'}))
    write_manifest(tmp_path, tmp_path)
    pyc = tmp_path / '__pycache__/unknown.cpython-314.pyc'
    pyc.parent.mkdir()
    pyc.write_bytes(b'not a recorded module')
    assert verify_manifest(tmp_path) == ['Artifact file set differs']
    pyc.unlink()
    metadata = tmp_path / 'src/nyanya_agent.egg-info/PKG-INFO'
    metadata.parent.mkdir(parents=True)
    metadata.symlink_to(tmp_path / 'package.json')
    assert verify_manifest(tmp_path) == ['Invalid or incomplete artifact manifest']


def test_malformed_self_hashed_manifest_fails_closed(tmp_path):
    import hashlib

    (tmp_path / 'package.json').write_text(json.dumps({'version': '0.3.0'}))
    original = write_manifest(tmp_path, tmp_path)
    for field, value in [('files', []), ('source', []), ('schema_version', True), ('files', {'../outside': {}})]:
        record = dict(original)
        record.pop('artifact_id')
        record[field] = value
        record['artifact_id'] = hashlib.sha256(json.dumps(record, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        (tmp_path / 'artifact-manifest.json').write_text(json.dumps(record))
        assert verify_manifest(tmp_path) == ['Invalid or incomplete artifact manifest']


def test_manifest_cannot_bless_private_paths_or_unsupported_entries(tmp_path):
    import hashlib
    import os

    (tmp_path / 'package.json').write_text(json.dumps({'version': '0.3.0'}))
    original = write_manifest(tmp_path, tmp_path)
    record = json.loads(json.dumps(original))
    record.pop('artifact_id')
    private = tmp_path / 'AGENTS.md'
    private.write_text('private fixture instructions')
    record['files']['AGENTS.md'] = {
        'sha256': hashlib.sha256(private.read_bytes()).hexdigest(),
        'size': private.stat().st_size, 'mode': private.stat().st_mode & 0o7777,
    }
    record['artifact_id'] = hashlib.sha256(json.dumps(record, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    (tmp_path / 'artifact-manifest.json').write_text(json.dumps(record))
    assert verify_manifest(tmp_path) == ['Invalid or incomplete artifact manifest']
    (tmp_path / 'artifact-manifest.json').write_text(json.dumps(original))
    private.unlink()
    os.mkfifo(tmp_path / 'unexpected-fifo')
    assert verify_manifest(tmp_path) == ['Artifact file set differs']


def test_setuptools_build_mode_normalization_preserves_content_and_source_checks(tmp_path):
    import shutil

    (tmp_path / 'package.json').write_text(json.dumps({'version': '0.3.0'}))
    sources = []
    for name, mode in [('private-mode.py', 0o600), ('executable.py', 0o755)]:
        source = tmp_path / 'src/nyanya_agent' / name
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text('print("fixture")\n')
        source.chmod(mode)
        sources.append(source)
    write_manifest(tmp_path, tmp_path)
    for source in sources:
        built = tmp_path / 'build/lib/nyanya_agent' / source.name
        built.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, built)
        built.chmod(0o644)
    assert verify_manifest(tmp_path) == []
    built.write_text('print("changed")\n')  # Same length, different hash.
    assert verify_manifest(tmp_path) == ['Generated build copy differs: build/lib/nyanya_agent/executable.py']
    shutil.copy2(sources[-1], built)
    built.chmod(0o644)
    sources[0].chmod(0o644)
    assert verify_manifest(tmp_path) == ['Artifact content or mode differs: src/nyanya_agent/private-mode.py']


def test_generated_build_modes_cannot_become_writable_or_privileged(tmp_path):
    import shutil

    (tmp_path / 'package.json').write_text(json.dumps({'version': '0.3.0'}))
    source = tmp_path / 'src/nyanya_agent/example.py'
    source.parent.mkdir(parents=True)
    source.write_text('print("fixture")\n')
    source.chmod(0o755)
    write_manifest(tmp_path, tmp_path)
    built = tmp_path / 'build/lib/nyanya_agent/example.py'
    built.parent.mkdir(parents=True)
    shutil.copy2(source, built)
    for mode in (0o646, 0o664, 0o4755, 0o2755, 0o1755):
        built.chmod(mode)
        assert verify_manifest(tmp_path) == ['Generated build copy differs: build/lib/nyanya_agent/example.py']
