"""Release regressions: one model-profile contract across API and operations."""

import pytest
from pydantic import ValidationError

from nyanya_agent import model_routing
from nyanya_agent.dashboard_api import OperationCreate
from nyanya_agent.operation_spec import OPERATION_PROFILES, OperationSpec
from nyanya_agent.task_outcomes import SafeOperationError


def test_operation_profile_contract_matches_available_profiles():
    assert set(OPERATION_PROFILES) == {"auto", *model_routing.PROFILES}


@pytest.mark.parametrize("profile", ["auto", "flash", "luna", "sol", "astra"])
def test_dashboard_accepts_every_operation_profile(tmp_path, profile):
    payload = OperationCreate(prompt="Inspect a synthetic example", workspace=str(tmp_path), profile=profile)
    assert OperationSpec(prompt=payload.prompt, workspace=payload.workspace, profile=payload.profile).validate().profile == profile


@pytest.mark.parametrize("profile", ["", "unknown", "SOL", "sol-extra", " sol", "sol\n"])
def test_dashboard_and_operation_reject_invalid_profiles(tmp_path, profile):
    with pytest.raises(ValidationError):
        OperationCreate(prompt="inspect", workspace=str(tmp_path), profile=profile)
    with pytest.raises(SafeOperationError):
        OperationSpec(workspace=str(tmp_path), profile=profile).validate()
