"""Intake failures update request envelopes without authorizing execution."""

import json
from unittest.mock import Mock

import pytest

from nyanya_agent import dashboard_store
from nyanya_agent.bridge_store import NyaNyaConversationStore


@pytest.fixture
def intake(tmp_path, monkeypatch):
    monkeypatch.setenv("NYANYA_DASHBOARD_DB_PATH", str(tmp_path / "intake.db"))
    monkeypatch.setenv("NYANYA_WORKSPACE_ROOTS", str(tmp_path))
    registration = tmp_path / "workspaces.json"
    # A different owner's registration and an allowed root confer no authority.
    registration.write_text(json.dumps({"users": {"other": {"workspace": str(tmp_path)}}}))
    monkeypatch.setenv("NYANYA_USER_WORKSPACES_FILE", str(registration))
    store = NyaNyaConversationStore({})
    try:
        yield store
    finally:
        store.close()


def submit_request(store, mode="auto"):
    request_id = dashboard_store.create_agent_request(
        source="discord", trigger="prefix", command="message", mode=mode, prompt="inspect workspace"
    )
    responder = Mock()
    response = store.submit(
        owner_key="unassigned",
        conversation_key="fixture-conversation",
        prompt="inspect workspace",
        mode=mode,
        responder=responder,
        request_id=request_id,
    )
    responder.assert_not_called()
    return request_id, response


def assert_blocked_envelope(store, request_id, response):
    request = dashboard_store.get_request(request_id)
    assert request["status"] == "blocked"
    assert request["result_summary"] == response
    assert request["started_at"] is None
    assert [event["event_type"] for event in request["events"]] == ["received", "prerequisite_failed"]
    assert request["events"][-1]["message"] == response
    with dashboard_store.connect(store.operations.path) as conn:
        # Check the actual compatibility envelope, not only its read model.
        envelope = conn.execute("SELECT status FROM agent_requests WHERE id=?", (request_id,)).fetchone()
        assert envelope["status"] == "blocked"
        assert conn.execute("SELECT COUNT(*) FROM task_operations").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM executions").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM operation_workers").fetchone()[0] == 0
    return request


@pytest.mark.parametrize("mode", ["auto", "gemini", "codex", "codex_write"])
def test_missing_owner_workspace_records_block_without_submission(intake, monkeypatch, mode):
    operation_submit = Mock(side_effect=AssertionError("Unregistered workspace reached submission"))
    legacy_submit = Mock(side_effect=AssertionError("Unregistered workspace reached legacy submission"))
    worker_start = Mock(side_effect=AssertionError("Unregistered workspace started a worker"))
    monkeypatch.setattr(intake.operations, "submit", operation_submit)
    monkeypatch.setattr(intake.durable_tasks, "submit", legacy_submit)
    monkeypatch.setattr(intake.operations, "ensure_worker", worker_start)

    request_id, response = submit_request(intake, mode)

    assert response == "등록된 사용자 작업공간이 없습니다. 관리자가 홈워크스페이스를 등록한 뒤 다시 요청하세요."
    assert_blocked_envelope(intake, request_id, response)
    operation_submit.assert_not_called()
    legacy_submit.assert_not_called()
    worker_start.assert_not_called()


@pytest.mark.parametrize("error_type", [ValueError, OSError, RuntimeError])
@pytest.mark.parametrize("failure_stage", ["workspace", "submission"])
def test_generic_prerequisite_failure_records_only_safe_diagnostic(
    intake, monkeypatch, tmp_path, capsys, error_type, failure_stage
):
    private_detail = "SYNTHETIC_PRIVATE_DIAGNOSTIC_DO_NOT_RECORD"
    failing_call = Mock(side_effect=error_type(private_detail))
    if failure_stage == "workspace":
        monkeypatch.setattr(intake, "execution_workspace", failing_call)
        operation_submit = Mock(side_effect=AssertionError("Prerequisite failure reached submission"))
        monkeypatch.setattr(intake.operations, "submit", operation_submit)
    else:
        registration = tmp_path / "workspaces.json"
        registration.write_text(json.dumps({"users": {"unassigned": {"workspace": str(tmp_path)}}}))
        monkeypatch.setattr(intake.operations, "submit", failing_call)

    request_id, response = submit_request(intake)

    assert response == f"작업 접수 보류: {error_type.__name__}. 워크스페이스와 worker 준비 상태를 확인하세요."
    request = assert_blocked_envelope(intake, request_id, response)
    failing_call.assert_called_once()
    if failure_stage == "workspace":
        operation_submit.assert_not_called()
    captured = capsys.readouterr()
    assert private_detail not in response + json.dumps(request) + captured.out + captured.err
