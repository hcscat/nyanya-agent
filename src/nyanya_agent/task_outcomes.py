"""Machine-readable outcomes; user-facing text never determines task status."""

from dataclasses import dataclass
import subprocess


@dataclass(frozen=True)
class TaskOutcome:
    status: str
    text: str

    def __post_init__(self) -> None:
        if self.status not in {"succeeded", "failed", "timed_out", "cancelled", "awaiting_approval", "blocked"}:
            raise ValueError("Unknown task outcome")


class OutcomeSignal(Exception):
    def __init__(self, status: str, text: str):
        super().__init__(text)
        self.outcome = TaskOutcome(status, text)


class SafeOperationError(ValueError):
    """A fixed, public diagnostic authored by the operation engine, never raw tool output."""


def outcome_from_error(exc: Exception) -> TaskOutcome:
    if isinstance(exc, OutcomeSignal):
        return exc.outcome
    if isinstance(exc, SafeOperationError):
        return TaskOutcome("blocked", str(exc))
    if isinstance(exc, subprocess.TimeoutExpired):
        return TaskOutcome("timed_out", "실행 제한 시간을 초과했습니다. 실행 상태를 확인한 뒤 재개 여부를 결정하세요.")
    # Exceptions can contain prompts, credentials, CLI arguments and host paths.
    return TaskOutcome("failed", f"작업 실행에 실패했습니다 ({type(exc).__name__}). 로컬 실행 환경을 점검하세요.")


def as_outcome(value: str | TaskOutcome) -> TaskOutcome:
    if isinstance(value, TaskOutcome):
        return value
    if not isinstance(value, str):
        raise TypeError("Task runners must return text or TaskOutcome")
    return TaskOutcome("succeeded", value)
