from nyanya_agent import core, execution_store as ledger


def test_terminal_single_prompt_uses_durable_execution_path(tmp_path, monkeypatch, capsys, fixture_worker):
    path = tmp_path / "terminal.db"
    monkeypatch.setenv("NYANYA_DASHBOARD_DB_PATH", str(path))
    monkeypatch.setenv("NYANYA_WORKSPACE_ROOTS", str(tmp_path))
    assert core.run_single_prompt({"agent_name": "NyaNya"}, "hello") == 0
    assert capsys.readouterr().out.startswith("done")
    tasks = ledger.list_tasks(db_path=path)
    assert len(tasks) == 1 and tasks[0]["status"] == "completed"
    with ledger.legacy.connect(path) as conn:
        assert conn.execute("SELECT count(*) FROM task_operations").fetchone()[0] == 1
    assert tasks[0]["requested_by"] == "operator"


def test_terminal_repl_keeps_previous_file_scope_out_of_current_request(tmp_path, monkeypatch):
    from nyanya_agent import core, bridge_policy, operation_service
    from nyanya_agent.task_outcomes import TaskOutcome

    prompts = []
    class Service:
        path = tmp_path / "state.db"
        def control(self, *args, **kwargs):
            return None
        def submit(self, prompt, *args, **kwargs):
            prompts.append(prompt)
            return {"id": "synthetic-task"}
        def wait(self, *args, **kwargs):
            return TaskOutcome("succeeded", "Synthetic reply")
        def close(self):
            pass

    inputs = iter(["Inspect old-file.txt", "Use only this inline text", "/exit"])
    monkeypatch.setattr(operation_service, "OperationService", Service)
    monkeypatch.setattr(bridge_policy, "default_codex_workdir", lambda: tmp_path)
    monkeypatch.setattr("builtins.input", lambda _prompt: next(inputs))
    monkeypatch.setattr(core, "save_session", lambda *args: None)
    assert core.run_repl({"agent_name": "Synthetic", "save_transcripts": False}) == 0
    assert prompts == ["Inspect old-file.txt", "Use only this inline text"]
