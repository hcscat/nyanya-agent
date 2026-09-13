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
