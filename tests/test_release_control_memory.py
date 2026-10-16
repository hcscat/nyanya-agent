"""Release regressions for safety-clause task-control intake."""


import pytest


from nyanya_agent.control_intents import classify


ACTUAL_A = (
    "[SYNTHETIC-READ-ONLY] 읽기 전용 기능 테스트입니다. "
    "파일·설정의 생성/수정/삭제와 명령 실행은 하지 마세요. "
    "HTTP GET과 POST의 차이를 두 문장으로 설명해 주세요."
)


RESOURCE_SAFETY = "파일·설정의 생성/수정/삭제와 명령 실행은 하지 마세요."


@pytest.mark.parametrize("text", [
    ACTUAL_A,
    RESOURCE_SAFETY + " HTTP GET과 POST의 차이를 설명해 주세요.",
    "HTTP GET과 POST의 차이를 설명해 주세요. " + RESOURCE_SAFETY,
    "파일과 설정을 변경하지 마세요. 명령도 실행하지 마세요. HTTP GET은 무엇인가요?",
    "기존 파일은 수정하거나 삭제하지 마. HTTP GET과 POST의 차이를 설명해 주세요.",
    "등록된 작업공간의 README.md 한 파일만 읽어줘. " + RESOURCE_SAFETY,
])
def test_complete_resource_safety_does_not_turn_questions_into_task_controls(text):
    assert classify(text).kind == "work_request"


@pytest.mark.parametrize(("text", "kind"), [
    (RESOURCE_SAFETY, "clarify"),
    (RESOURCE_SAFETY + " 취소", "clarify"),
    ("기존 파일은 삭제하지 마. 취소", "clarify"),
    ("기존 파일은 수정하거나 삭제하지 마.", "clarify"),
    ("취소하지 마", "clarify"),
    ("취소할지 알려줘", "clarify"),
    (RESOURCE_SAFETY + " task_previous는 취소해줘.", "clarify"),
    (RESOURCE_SAFETY + " 모두 취소해줘.", "clarify"),
    (RESOURCE_SAFETY + " cancel task_previous extra", "clarify"),
    (RESOURCE_SAFETY + ' "미완료 작업 취소"', "clarify"),
    ('"' + RESOURCE_SAFETY + '" HTTP GET을 설명해줘.', "clarify"),
    ("새 파일을 만들어줘. 기존 파일은 수정하거나 삭제하지 마라는 문구를 넣어줘.", "clarify"),
    ("cancel task_previous", "task_cancel"),
    ("미완료 모두 취소", "task_cancel_selection"),
    ("미완료 작업 목록만 보여줘. 기존 작업은 변경하거나 취소하지 마.", "task_list"),
])
def test_resource_safety_keeps_ambiguous_and_explicit_task_control_boundaries(text, kind):
    assert classify(text).kind == kind

