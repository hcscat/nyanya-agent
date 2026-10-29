"""Synthetic-only regressions for the provider transfer boundary."""

import hashlib
import json
import sys

import pytest

from nyanya_agent import reviewed_changes as files
from nyanya_agent.context_security import (
    child_environment, inline_context_only, select_context_paths, sensitive_content, validate_provider_prompt,
    context_references,
)
from nyanya_agent.process_runner import run_command
from nyanya_agent.task_outcomes import SafeOperationError


INLINE_ANALYSIS = (
    "파일 읽기나 수정, 명령 실행 없이 아래 코드만 분석해줘. "
    "Python 함수 `def average(values): return sum(values) / len(values)` 에서 빈 리스트와 "
    "[2, 4, 6] 입력의 동작을 설명하고, 빈 리스트에는 ValueError를 내는 개선 코드를 "
    "답변 안에만 작성해줘. 정상 입력, 빈 입력, 음수 입력의 예시와 예상 결과를 함께 설명해줘."
)


@pytest.mark.parametrize("prompt", [
    INLINE_ANALYSIS,
    "파일을 읽지 말고 Python 함수를 분석해줘. README.md 경로도 열지 마.",
    "파일 접근 없이 아래 내용을 설명해줘.",
    "파일을 읽지 마.",
    "파일을 열지 마.",
    "파일에 접근하지 마.",
    "파일을 읽거나 수정하지 말고, 방금 요청한 파일 변경은 끝난 거지? 한 문장으로 알려줘.",
    "파일을 읽거나 수정하지 마. 상태만 알려줘.",
    "파일을 읽거나 변경하지 말고 README.md도 열지 마.",
    "현재 요청만 처리해줘. 기존 파일을 읽거나 수정하거나 삭제하지 마. 새 파일 note.txt를 만들어줘.",
    "기존 파일을 읽거나 수정하거나 삭제하지 마. README.md 내용은 추측하지 말고 새 파일을 만들어줘.",
    "파일을 열거나 삭제하지 말아줘. 저장된 결과로 답해줘.",
    "파일에 접근하거나 수정하지 말고 진행 상태만 알려줘.",
    "파일을 조회하거나 편집하지 않고 지금 대화로만 답해줘.",
    "아래 코드만 분석해줘: def average(values): return sum(values) / len(values)",
    "다음 텍스트만 검토해줘: synthetic example",
    "Without reading or modifying files, explain the Python function in this message.",
    "Do not read workspace files. Inspect README.md only if necessary.",
    "No filesystem access. Explain this snippet.",
    "Analyze only the code below: def average(values): return sum(values) / len(values)",
    "Use only the text in this message: synthetic example",
])
def test_inline_only_requests_never_traverse_or_read_workspace(tmp_path, monkeypatch, prompt):
    def denied(*args, **kwargs):
        pytest.fail("Inline-only request attempted workspace traversal or reading")

    monkeypatch.setattr(files.os, "walk", denied)
    monkeypatch.setattr(files.os, "fwalk", denied)
    monkeypatch.setattr(files, "read_file", denied)
    assert inline_context_only(prompt)
    assert files.snapshot(tmp_path, prompt) == {}
    assert select_context_paths(["README.md", "Python/runtime.py"], prompt, tmp_path) == []


@pytest.mark.parametrize("prompt", [
    "파일 수정 없이 README.md 분석해줘.",
    "README.md를 읽고 답변 안에만 분석 내용을 작성해줘.",
    "파일을 읽고 수정하지 말고 README.md 분석해줘.",
    "파일을 읽어보고 수정 없이 README.md 분석해줘.",
    "파일에 접근하되 수정하지 말고 README.md 설명해줘.",
    "파일을 읽어서 검토하되 수정하지 마. README.md 내용을 설명해줘.",
    "파일을 수정하지 말고 README.md 읽어줘.",
    "이 파일만 읽어서 첫 문장을 확인해줘: README.md. 승인 전에는 수정하지 마.",
    "파일을 읽거나 수정할 수 있는지 README.md를 읽어서 판단해줘.",
    "파일을 읽거나 수정하지 말라는 뜻은 아니고 README.md만 읽어줘.",
    "파일을 읽거나 수정하지 말라고 한 건 아니고 README.md 내용을 확인해줘.",
    "파일을 읽거나 수정하지 않는 게 아니라 README.md를 읽되 수정만 하지 마.",
    "파일을 읽거나 수정하거나 삭제하지 말라는 뜻은 아니야. README.md만 읽어줘.",
    "Do not modify files. Read README.md and answer only in this message.",
])
def test_output_or_write_restrictions_still_allow_requested_reads(tmp_path, prompt):
    (tmp_path / "README.md").write_text("# Synthetic project overview")
    assert not inline_context_only(prompt)
    assert set(files.snapshot(tmp_path, prompt)) == {"README.md"}


def test_negated_coordinated_quote_does_not_override_an_actual_later_read_ban(tmp_path, monkeypatch):
    prompt = "파일을 읽거나 수정하지 말라는 뜻은 아니야. 하지만 지금은 파일을 읽지 말고 상태만 알려줘."

    def denied(*args, **kwargs):
        pytest.fail("A negated quote overrode a real current read ban")

    monkeypatch.setattr(files, "read_file", denied)
    monkeypatch.setattr(files.os, "walk", denied)
    monkeypatch.setattr(files.os, "fwalk", denied)
    assert inline_context_only(prompt)
    assert files.snapshot(tmp_path, prompt) == {}


def test_inline_prompt_keeps_secret_screening_with_empty_context(tmp_path):
    assert files.snapshot(tmp_path, INLINE_ANALYSIS) == {}
    validate_provider_prompt(INLINE_ANALYSIS + "\nSnapshot:\n{}")
    secret_prompt = INLINE_ANALYSIS + '\napi_key = "synthetic-secret-value"'
    assert files.snapshot(tmp_path, secret_prompt) == {}
    with pytest.raises(SafeOperationError, match="sensitive"):
        validate_provider_prompt(secret_prompt + "\nSnapshot:\n{}")


def test_language_name_is_not_implicit_directory_intent(tmp_path, monkeypatch):
    (tmp_path / "README.md").write_text("# Synthetic project overview")
    (tmp_path / "Python").mkdir()
    (tmp_path / "Python/runtime.py").write_text("synthetic runtime")
    seen = []
    original = files.read_file

    def read(root, name):
        seen.append(name)
        return original(root, name)

    monkeypatch.setattr(files, "read_file", read)
    assert set(files.snapshot(tmp_path, "Explain a Python function")) == {"README.md"}
    assert seen == ["README.md"]


def test_many_query_words_do_not_expand_unrelated_directories(tmp_path):
    names = [f"topic{i}/unrelated.txt" for i in range(4000)] + ["src/worker.py", "README.md"]
    prompt = "Inspect src/ " + " ".join(f"topic{i}" for i in range(4000))
    assert select_context_paths(names, prompt, tmp_path) == ["src/worker.py"]


def test_long_query_token_keeps_bounded_overview_selection(tmp_path):
    assert select_context_paths(["README.md", "src/worker.py"], "x" * 59_000, tmp_path) == ["README.md"]


@pytest.mark.parametrize("prompt", ["Inspect Python/", "Inspect the Python directory", "Python 폴더 분석", "Inspect folder Python"])
def test_named_directory_requires_path_or_directory_intent(tmp_path, prompt):
    (tmp_path / "Python").mkdir()
    (tmp_path / "Python/example.py").write_text("print('example')")
    (tmp_path / "unrelated.txt").write_text("unrelated")
    assert set(files.snapshot(tmp_path, prompt)) == {"Python/example.py"}


@pytest.mark.parametrize("prompt", [None, "Inspect conda_envs/ site-packages/ venv/ node_modules/ .venv/"])
def test_snapshot_excludes_conventional_dependency_trees(tmp_path, monkeypatch, prompt):
    (tmp_path / "src").mkdir()
    (tmp_path / "src/worker.py").write_text("def work(): return 1")
    for directory in ("conda_envs", "site-packages", "venv", "node_modules", ".venv"):
        (tmp_path / directory).mkdir()
        (tmp_path / directory / "runtime.py").write_text("synthetic dependency")
    original = files.read_file
    seen = []

    def read(root, name):
        seen.append(name)
        return original(root, name)

    monkeypatch.setattr(files, "read_file", read)
    expected = {"src/worker.py"} if prompt is None else set()
    assert set(files.snapshot(tmp_path, prompt)) == expected
    assert set(seen) == expected


def test_request_selection_does_not_read_unrelated_files(tmp_path, monkeypatch):
    (tmp_path / "src").mkdir()
    (tmp_path / "src/worker.py").write_text("def work(): return 1\n")
    (tmp_path / "notes.txt").write_text("unrelated private notes")
    original = files.read_file
    seen = []

    def read(root, name):
        seen.append(name)
        return original(root, name)

    monkeypatch.setattr(files, "read_file", read)
    assert set(files.snapshot(tmp_path, "Please fix timeout logic in the worker")) == {"src/worker.py"}
    assert seen == ["src/worker.py"]


@pytest.mark.parametrize("prompt", ["Inspect src/task.py", "Inspect task.py", "Inspect src/", "absolute"])
def test_explicit_paths_are_usable(tmp_path, prompt):
    (tmp_path / "src").mkdir()
    (tmp_path / "src/task.py").write_text("print('example')\n")
    (tmp_path / "other.txt").write_text("unrelated")
    if prompt == "absolute":
        prompt = f"Inspect {tmp_path}/src/task.py"
    assert set(files.snapshot(tmp_path, prompt)) == {"src/task.py"}


def test_general_analysis_gets_overview_without_workspace_dump(tmp_path):
    (tmp_path / "README.md").write_text("# Project\nA useful overview.")
    (tmp_path / "private-notes.txt").write_text("unrelated private notes")
    assert set(files.snapshot(tmp_path, "Explain this project's architecture")) == {"README.md"}


@pytest.mark.parametrize("content", [
    '{"service": {"api_key": "synthetic-secret-value"}}',
    'API_KEY = "synthetic-secret-value"',
    'password: synthetic-password',
    'Authorization: Bearer synthetic-auth-value',
    '-----BEGIN PRIVATE KEY-----\nsynthetic-key\n-----END PRIVATE KEY-----',
    'https://service:synthetic-password@example.invalid/',
])
def test_sensitive_content_excluded_even_in_explicit_ordinary_files(tmp_path, content):
    (tmp_path / "ordinary.txt").write_text(content)
    assert files.snapshot(tmp_path, "Read ordinary.txt") == {}
    with pytest.raises(SafeOperationError, match="sensitive"):
        validate_provider_prompt(content)


def test_known_secret_values_and_local_instructions_never_in_context(tmp_path, monkeypatch):
    monkeypatch.setenv("NYANYA_DISCORD_TOKEN", "synthetic-discord-private-value")
    (tmp_path / "ordinary.txt").write_text("Value without a label: synthetic-discord-private-value")
    (tmp_path / "AGENTS.md").write_text("Local private instructions")
    (tmp_path / "AGENTS.override.md.bak").write_text("Local private instructions")
    (tmp_path / ".env").write_text("CONFIG=synthetic-value")
    assert files.snapshot(tmp_path, "Read ordinary.txt AGENTS.md AGENTS.override.md.bak .env") == {}


def test_sanitized_templates_and_source_references_are_usable():
    assert not sensitive_content('api_key = os.getenv("OPENAI_API_KEY")')
    assert not sensitive_content('{"api_key": "<YOUR_API_KEY>", "password": "${PASSWORD}"}')


def test_provider_specific_environment_policy():
    source = {
        "PATH": "/usr/bin", "HOME": "/fixture", "OPENAI_API_KEY": "synthetic-openai",
        "GEMINI_API_KEY": "synthetic-gemini", "DISCORD_TOKEN": "synthetic-discord",
        "NYANYA_DASHBOARD_TOKEN": "synthetic-dashboard", "PYTHONPATH": "/injection",
        "LD_PRELOAD": "/injection", "UNRELATED_AUTH_TOKEN": "synthetic-unrelated",
    }
    assert child_environment("codex", source) == {key: source[key] for key in ("PATH", "HOME", "OPENAI_API_KEY")}
    assert child_environment("agy", source) == {key: source[key] for key in ("PATH", "HOME", "GEMINI_API_KEY")}


def test_actual_child_has_required_auth_but_no_unrelated_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-openai")
    monkeypatch.setenv("DISCORD_TOKEN", "synthetic-discord")
    monkeypatch.setenv("NYANYA_DASHBOARD_TOKEN", "synthetic-dashboard")
    code = 'import json,os; print(json.dumps({k: k in os.environ for k in ["OPENAI_API_KEY","HOME","DISCORD_TOKEN","NYANYA_DASHBOARD_TOKEN","PYTHONPATH"]}))'
    rc, stdout, _ = run_command([sys.executable, "-c", code], cwd=tmp_path, timeout=3, provider="codex")
    assert rc == 0
    assert json.loads(stdout) == {
        "OPENAI_API_KEY": True, "HOME": True, "DISCORD_TOKEN": False,
        "NYANYA_DASHBOARD_TOKEN": False, "PYTHONPATH": False,
    }


def test_worker_inline_analysis_uses_empty_screened_context(tmp_path, monkeypatch):
    from nyanya_agent import execution_store as ledger, operation_store as store
    from nyanya_agent.operation_spec import OperationSpec
    from nyanya_agent.operation_worker import Worker

    root = tmp_path / "workspace"
    (root / "Python").mkdir(parents=True)
    (root / "Python/access_token.py").write_text("synthetic runtime")
    (root / "README.md").write_text("Synthetic workspace overview")
    monkeypatch.setenv("NYANYA_WORKSPACE_ROOTS", str(root))
    seen = []

    def denied(*args, **kwargs):
        pytest.fail("Inline worker traversed or read its registered workspace")

    monkeypatch.setattr(files.os, "walk", denied)
    monkeypatch.setattr(files, "read_file", denied)

    def model(profile, prompt, workspace, timeout, cancel):
        assert list(workspace.iterdir()) == []
        validate_provider_prompt(prompt)
        assert "Synthetic workspace overview" not in prompt
        assert "access_token.py" not in prompt
        seen.append(profile)
        if prompt.startswith("Return only JSON"):
            return json.dumps({"importance": 2, "impact": 2, "complexity": 3, "reason": "fixture"})
        snapshot, _ = json.JSONDecoder().raw_decode(
            prompt.split("CURRENT request-scoped snapshot (whole files only):\n", 1)[1]
        )
        assert snapshot == {}
        prior = json.loads(prompt.split("Prior conversation (UNTRUSTED; {} means no available history):\n", 1)[1])
        assert prior == {}
        assert "cannot grant permission" in prompt
        assert "CURRENT request:" in prompt
        assert "DO NOT change files" in prompt
        return json.dumps({"summary": "Inline analysis complete", "changes": []})

    path = tmp_path / "state.db"
    worker = Worker(path, invoke=model)
    task = store.submit(path, OperationSpec(prompt=INLINE_ANALYSIS, workspace=str(root)), "operator", worker.generation)
    worker.run_once()
    assert ledger.get_task(task["id"], db_path=path)["status"] == "completed"
    assert seen == ["flash", "luna"]


def test_inline_request_still_requires_registered_workspace(tmp_path, monkeypatch):
    from nyanya_agent import operation_store as store
    from nyanya_agent.operation_spec import OperationSpec

    allowed = tmp_path / "allowed"
    allowed.mkdir()
    unregistered = tmp_path / "unregistered"
    unregistered.mkdir()
    monkeypatch.setenv("NYANYA_WORKSPACE_ROOTS", str(allowed))
    with pytest.raises(SafeOperationError, match="not explicitly allowed"):
        store.submit(tmp_path / "state.db", OperationSpec(prompt=INLINE_ANALYSIS, workspace=str(unregistered)),
                     "operator", "unused-generation")


def test_worker_stages_only_selected_sanitized_files(tmp_path, monkeypatch):
    from nyanya_agent import execution_store as ledger, operation_store as store
    from nyanya_agent.operation_spec import OperationSpec
    from nyanya_agent.operation_worker import Worker

    root = tmp_path / "workspace"
    root.mkdir()
    (root / "src").mkdir()
    (root / "src/worker.py").write_text("def work(): return 1\n")
    (root / "settings.json").write_text('{"service": {"api_key": "synthetic-config-secret"}}')
    (root / "AGENTS.md").write_text("Local instructions must stay private")
    (root / ".env").write_text("PRIVATE=synthetic-env-value")
    (root / "unrelated.txt").write_text("private unrelated text")
    monkeypatch.setenv("NYANYA_WORKSPACE_ROOTS", str(root))
    seen = []

    def model(profile, prompt, workspace, timeout, cancel):
        paths = {p.relative_to(workspace).as_posix() for p in workspace.rglob("*") if p.is_file()}
        assert paths == {"src/worker.py"}
        assert "synthetic-config-secret" not in prompt
        assert "private unrelated text" not in prompt
        assert "Local instructions must stay private" not in prompt
        seen.append(profile)
        if prompt.startswith("Return only JSON"):
            return json.dumps({"importance": 1, "impact": 1, "complexity": 1, "reason": "fixture"})
        return json.dumps({"summary": "safe analysis complete", "changes": []})

    path = tmp_path / "state.db"
    worker = Worker(path, invoke=model)
    task = store.submit(path, OperationSpec(
        prompt="Inspect src/worker.py and settings.json AGENTS.md .env", workspace=str(root),
    ), "operator", worker.generation)
    worker.run_once()
    assert ledger.get_task(task["id"], db_path=path)["status"] == "completed"
    assert len(seen) == 2


@pytest.mark.parametrize("crowding", ["directories", "filenames"])
def test_exact_late_file_is_read_before_bounded_broad_discovery(tmp_path, crowding):
    if crowding == "directories":
        for index in range(205):
            directory = tmp_path / f"a{index:03d}"
            directory.mkdir()
            (directory / "unrelated.txt").write_text("unrelated")
    else:
        for index in range(4005):
            (tmp_path / f"a{index:04d}.txt").write_text("unrelated")
    target = tmp_path / "nyanya-tasks/document/task-fixture/note.txt"
    target.parent.mkdir(parents=True)
    target.write_text("첫째 줄\n두 번째 줄\n")
    captured = files.snapshot(tmp_path, "이 파일만 읽어줘: `nyanya-tasks/document/task-fixture/note.txt`")
    assert captured == {"nyanya-tasks/document/task-fixture/note.txt": {
        "content": target.read_text(), "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
    }}


def test_exact_file_does_not_require_any_directory_discovery(tmp_path, monkeypatch):
    target = tmp_path / "late/deep/note.txt"
    target.parent.mkdir(parents=True)
    target.write_text("first\nsecond\n")

    def denied(*args, **kwargs):
        pytest.fail("Exact file access depended on broad discovery")

    monkeypatch.setattr(files.os, "walk", denied)
    monkeypatch.setattr(files.os, "fwalk", denied)
    assert set(files.snapshot(tmp_path, f"Read only {target}")) == {"late/deep/note.txt"}


def test_exact_files_precede_large_explicit_directory_and_byte_budget(tmp_path):
    directory = tmp_path / "a-directory"
    directory.mkdir()
    for index in range(80):
        (directory / f"{index:03d}.txt").write_text("x" * 700)
    target = tmp_path / "z-target/note.txt"
    target.parent.mkdir()
    target.write_text("required exact file\n")
    captured = files.snapshot(tmp_path, "Inspect directory a-directory and z-target/note.txt")
    assert list(captured)[0] == "z-target/note.txt"
    assert captured["z-target/note.txt"]["content"] == target.read_text()
    assert len(captured) <= 80 and sum(len(item["content"].encode()) for item in captured.values()) <= 50_000


def test_exact_file_references_take_priority_over_many_directory_references(tmp_path):
    target = tmp_path / "z-target/note.txt"
    target.parent.mkdir()
    target.write_text("required exact file")
    prompt = "Read " + " ".join(f"directory{index}/" for index in range(100)) + " z-target/note.txt"
    assert set(files.snapshot(tmp_path, prompt)) == {"z-target/note.txt"}
    references, _ = context_references(prompt, tmp_path)
    assert references[0][0] == "z-target/note.txt" and len(references) == 80


def test_direct_file_with_multiple_hardlinks_is_not_context(tmp_path):
    target = tmp_path / "exact/note.txt"
    target.parent.mkdir()
    target.write_text("shared inode")
    (tmp_path / "second-link.txt").hardlink_to(target)
    assert files.snapshot(tmp_path, "Read exact/note.txt") == {}


@pytest.mark.parametrize("capability", ["fwalk", "O_NOFOLLOW"])
def test_missing_secure_discovery_capability_fails_closed(tmp_path, monkeypatch, capability):
    (tmp_path / "README.md").write_text("overview")
    monkeypatch.delattr(files.os, capability)
    assert files.snapshot(tmp_path, "Explain this project") == {}
    if capability == "O_NOFOLLOW":
        assert files.snapshot(tmp_path, "Read README.md") == {}


def test_explicit_directory_discovery_is_scoped_and_still_bounded(tmp_path, monkeypatch):
    target = tmp_path / "z-target"
    target.mkdir()
    for index in range(205):
        directory = target / f"d{index:03d}"
        directory.mkdir()
        (directory / "note.txt").write_text("note")
    (tmp_path / "README.md").write_text("unrelated overview")
    calls = []
    original = files.os.fwalk

    def walking(*args, **kwargs):
        calls.append(kwargs["dir_fd"])
        yield from original(*args, **kwargs)

    monkeypatch.setattr(files.os, "fwalk", walking)
    captured = files.snapshot(tmp_path, "Inspect directory z-target")
    assert len(calls) == 1
    assert captured and all(name.startswith("z-target/") for name in captured)
    assert len(captured) <= 80


@pytest.mark.parametrize("name", [
    "AGENTS.md", "nested/AGENTS.override.md", "backup-data/note.txt", ".hidden/note.txt",
    "nested/.env", "private/note.txt", "conda_envs/note.txt", "site-packages/note.txt",
    "nested/venv/note.txt", "node_modules/note.txt", "nested/key.PEM",
])
def test_explicit_prioritized_paths_keep_private_hidden_dependency_exclusions(tmp_path, monkeypatch, name):
    target = tmp_path / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("not provider context")

    def denied(*args, **kwargs):
        pytest.fail("Excluded explicit path attempted reading or fallback discovery")

    monkeypatch.setattr(files, "read_file", denied)
    monkeypatch.setattr(files.os, "fwalk", denied)
    assert files.snapshot(tmp_path, f"Read only {name}") == {}


@pytest.mark.parametrize("reference", ["../outside.txt", "nested/../../outside.txt", "absolute"])
def test_invalid_explicit_path_cannot_read_or_trigger_overview(tmp_path, monkeypatch, reference):
    root = tmp_path / "workspace"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside workspace")
    (root / "README.md").write_text("do not export overview")
    if reference == "absolute":
        reference = str(outside)

    def denied(*args, **kwargs):
        pytest.fail("Invalid explicit path attempted reading or fallback discovery")

    monkeypatch.setattr(files, "read_file", denied)
    monkeypatch.setattr(files.os, "fwalk", denied)
    assert files.snapshot(root, f"Read only {reference}") == {}


@pytest.mark.parametrize("reference", ["link/note.txt", "link/", "leaf.txt", "root"])
def test_explicit_symlinks_and_ancestors_cannot_be_traversed(tmp_path, monkeypatch, reference):
    root = tmp_path / "workspace"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "note.txt").write_text("external content")
    (root / "link").symlink_to(outside, target_is_directory=True)
    (root / "leaf.txt").symlink_to(outside / "note.txt")
    if reference == "root":
        alias = tmp_path / "root-alias"
        alias.symlink_to(root, target_is_directory=True)
        root, reference = alias, "leaf.txt"
    original = files.os.fwalk
    walked = []

    def walking(*args, **kwargs):
        walked.append(args[0])
        yield from original(*args, **kwargs)

    monkeypatch.setattr(files.os, "fwalk", walking)
    assert files.snapshot(root, f"Read only {reference}") == {}
    if reference in {"link/note.txt", "link/"} or root.name == "root-alias":
        assert walked == []


def test_missing_literal_references_have_bounded_open_attempts(tmp_path, monkeypatch):
    calls = []

    def absent(root, name):
        calls.append(name)
        return None

    monkeypatch.setattr(files, "read_file", absent)
    prompt = "Read " + " ".join(f"missing{i}/note.txt" for i in range(2000))
    assert files.snapshot(tmp_path, prompt) == {}
    assert len(calls) == 80
    assert len(context_references(prompt, tmp_path)[0]) == 80


@pytest.mark.parametrize("content", [b"a" * 50_001, b"invalid\xff", b"binary\0data"])
def test_prioritized_file_keeps_full_preimage_utf8_and_size_filters(tmp_path, content):
    target = tmp_path / "exact/note.txt"
    target.parent.mkdir()
    target.write_bytes(content)
    assert files.snapshot(tmp_path, "Read exact/note.txt") == {}


def test_direct_named_file_plan_uses_current_full_preimage(tmp_path, monkeypatch):
    from nyanya_agent import operation_store as store
    from nyanya_agent.operation_spec import OperationSpec

    target = tmp_path / "nyanya-tasks/document/task-fixture/note.txt"
    target.parent.mkdir(parents=True)
    target.write_text("first\nkeep second\n")
    monkeypatch.setenv("NYANYA_WORKSPACE_ROOTS", str(tmp_path))
    path = tmp_path / "state.db"
    store.register_worker(path, "worker")
    prompt = "Read only nyanya-tasks/document/task-fixture/note.txt and propose a first-line change"
    task = store.submit(path, OperationSpec(prompt=prompt, workspace=str(tmp_path)), "operator", "worker")
    baseline = files.snapshot(tmp_path, prompt)
    plan = files.propose(path, task["id"], "operator", tmp_path, [{
        "path": target.relative_to(tmp_path).as_posix(), "action": "modify",
        "content": "changed\nkeep second\n", "reason": "first line only",
    }], baseline)
    assert plan["status"] == "pending"
    assert target.read_text() == "first\nkeep second\n"
