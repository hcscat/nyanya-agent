from __future__ import annotations

from nyanya_agent import dashboard_store as store


def test_agent_request_lifecycle_and_usage(tmp_path):
    db_path = tmp_path / "dashboard.db"

    request_id = store.create_agent_request(
        source="discord",
        channel_id="channel",
        user_id="user",
        trigger="prefix",
        command="status",
        mode="control",
        provider="gemini_cli",
        model="gemini-cli-default",
        prompt="status",
        db_path=db_path,
    )

    store.mark_request_status(request_id, "running", db_path=db_path)
    store.mark_request_status(request_id, "completed", result_summary="ok", db_path=db_path)

    request = store.get_request(request_id, db_path=db_path)
    assert request is not None
    assert request["status"] == "completed"
    assert request["duration_ms"] is not None
    assert request["events"][0]["event_type"] == "received"

    summary = store.dashboard_summary(db_path=db_path)
    assert summary["requests"] == 1
    assert summary["status_counts"]["completed"] == 1

    usage = store.usage_series(period="daily", db_path=db_path)
    assert usage[-1]["requests"] == 1
    assert usage[-1]["completed"] == 1


def test_project_phase_check_requires_confirmation_when_next_action_exists(tmp_path):
    db_path = tmp_path / "dashboard.db"
    project = store.create_project(name="Portfolio", goal="Ship dashboard", db_path=db_path)

    store.update_phase(
        project["id"],
        "planning",
        status="running",
        next_action="설계 검토를 시작한다.",
        db_path=db_path,
    )

    check = store.check_project_phase(project["id"], phase_key="planning", db_path=db_path)

    assert check["status"] == "needs_confirmation"
    assert check["confirmation_required"] == 1
    assert "설계 검토" in check["discord_message"]


def test_due_phase_checks_respects_interval(tmp_path):
    db_path = tmp_path / "dashboard.db"
    project = store.create_project(name="Agent", goal="Run checks", db_path=db_path)
    store.update_phase(
        project["id"],
        "planning",
        status="running",
        next_action="다음 단계 승인",
        db_path=db_path,
    )

    first = store.due_phase_checks(interval_seconds=3600, db_path=db_path)
    second = store.due_phase_checks(interval_seconds=3600, db_path=db_path)

    assert len(first) == 1
    assert first[0]["status"] == "needs_confirmation"
    assert second == []
