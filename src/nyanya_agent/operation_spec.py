"""Versioned data-only operations. Never deserialize executable Python or shell."""

from nyanya_agent.task_outcomes import SafeOperationError
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Literal, get_args


OperationProfile = Literal["auto", "flash", "luna", "sol", "astra"]
OPERATION_PROFILES = get_args(OperationProfile)


@dataclass(frozen=True)
class OperationSpec:
    version: int = 1
    kind: str = "request"
    prompt: str = ""
    workspace: str = ""
    profile: OperationProfile = "auto"
    timeout_seconds: int = 600
    plan_id: str = ""
    draft_id: str = ""

    def validate(self):
        if type(self.version) is not int or self.version != 1 or self.kind not in {"request", "apply"}:
            raise SafeOperationError("Unsupported operation version or kind")
        if self.profile not in OPERATION_PROFILES:
            raise SafeOperationError("Unknown model profile")
        if not isinstance(self.prompt, str) or len(self.prompt.encode()) > 60_000:
            raise SafeOperationError("Prompt exceeds operation limit")
        if type(self.timeout_seconds) is not int or not 1 <= self.timeout_seconds <= 3600:
            raise SafeOperationError("Invalid timeout")
        if not Path(self.workspace).is_absolute():
            raise SafeOperationError("An absolute registered workspace is required")
        if self.kind == "apply" and not self.plan_id:
            raise SafeOperationError("Apply requires a persisted plan")
        if not isinstance(self.draft_id, str) or len(self.draft_id) > 80 or (
            self.draft_id and (self.kind != "request" or not self.draft_id.startswith("draft_") or not self.draft_id[6:].isalnum())
        ):
            raise SafeOperationError("Invalid draft identity")
        return self

    def dumps(self):
        return json.dumps(asdict(self.validate()), ensure_ascii=False, sort_keys=True)

    @classmethod
    def loads(cls, value):
        if len(value) > 500_000:
            raise SafeOperationError("Operation too large")
        return cls(**json.loads(value)).validate()
