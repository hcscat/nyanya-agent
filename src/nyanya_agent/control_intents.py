"""Bounded, local recognition of operation-ledger questions and commands."""

from __future__ import annotations

from dataclasses import dataclass
import re


TASK_ID = r"task_[A-Za-z0-9_]+"
_ID_COMMAND = re.compile(rf"^/?(why|cancel|dismiss|resume|ack-delivery|설명|취소|종결)\s+({TASK_ID})$", re.I)
_KNOWN_TASK_COMMAND = re.compile(
    r"^(?:/?(?:why|cancel|dismiss|resume|ack-delivery|tasks|recovery|status)|(?:설명|취소|종결|작업목록|복구))(?:\s|$)",
    re.I,
)
_QUOTED = re.compile(r"[\"'`“”‘’]|```|>\s")
_QUOTED_RUNTIME = re.compile(r'''^["'`“‘].*(?:timeout|타임아웃|실행\s*제한|제한\s*시간).*["'`”’]$''', re.I)
_NEGATED = re.compile(r"(취소|제거|삭제|종결).{0,12}(하지\s*마|안\s*할|말아|않|고민|방법|어떻게|가능|여부|생각)")
_DOCUMENT = re.compile(r"(?:문서|파일|README|TODO|프로젝트).{0,24}(?:할\s*일|미완료|남은\s*작업)|(?:할\s*일|미완료).{0,24}(?:문서|파일|README|TODO)", re.I)
_CONTROL_WORD = re.compile(r"미완료|남은\s*작업|작업\s*목록|작업들|취소|제거|종결|ack-delivery", re.I)
_RUNTIME_STATUS_QUERY = re.compile(
    r"(?:(?:현재|지금)\s*)?(?:(?:냐냐|nyanya|에이전트|너)(?:의)?\s*)?"
    r"(?:실행\s*(?:제한\s*시간|시간\s*제한)|제한\s*시간|타임아웃|timeout)(?:은|이|을|를)?\s*"
    r"(?:(?:몇\s*(?:초|분)(?:로)?|얼마|무엇|뭐)(?:인가(?:요)?|야|인지)?"
    r"(?:\s*(?:설정)?되어\s*있(?:는가|나요|습니까))?|알려(?:줘|주세요)|확인해(?:줘|주세요))?\s*[?？.!。！]*"
    r"|what\s+is\s+(?:your|nyanya(?:'s)?|the\s+agent(?:'s)?)\s+(?:execution\s+)?(?:timeout|time\s+limit)\s*[?？.!]*",
    re.I,
)
_LIST = re.compile(r"^(?:(?:다른|현재|지금|내|나의|전체)\s*)?(?:미완료\s*)?(?:작업(?:들)?|할\s*일)(?:이|은|들)?(?:\s*(?:무엇|뭐|존재하나|있나|있어|몇\s*개|목록|리스트|보여줘|알려줘|조회|확인|남았|남아))?.*$")
_CANCEL_VERB = re.compile(r"취소|제거|종결|하지\s*않겠|안\s*하겠|하지\s*마")
_LIST_SCOPE = re.compile(r"미완료|남은\s*작업|이전\s*목록|위\s*목록|방금\s*목록|작업들|전부|모두|전체")
_WORK_ACTION = re.compile(r"\b(?:fix|implement|change|update|debug|refactor|test|write|improve|analyze|review|create|make)\b|(?:수정|구현|개선|분석|테스트|고쳐|작성|생성|만들)(?:해|하|해줘|해주세요|해라)?", re.I)
_WORK_TARGET = re.compile(r"\b(?:worker|logic|function|code|test|bug|file|module|script|implementation)\b|로직|코드|함수|테스트|버그|파일|모듈|스크립트|구현", re.I)
_LIST_WITH_QUALIFIER = re.compile(
    r"^(?:(?:현재|지금|내|나의|전체)\s*)?"
    r"(?:미완료\s*작업(?:들)?|남은\s*작업(?:들)?)\s*목록(?:만|을|만을)?\s*"
    r"(?:보여(?:줘|주세요)|알려(?:줘|주세요)|조회해(?:줘|주세요))"
    r"(?:\s*[.!。！;,，]\s*|\s+)(?P<qualifier>.+)$"
)
_NON_MUTATION_QUALIFIER = re.compile(
    r"(?:(?:(?:기존|현재|이전|미완료|남은)\s*)?작업(?:들)?(?:은|을)?\s*)?"
    r"(?:(?:취소|삭제|변경|재실행|다시\s*실행|재개)\s*(?:하거나|및|또는|/|,)\s*)*"
    r"(?:취소|삭제|변경|재실행|다시\s*실행|재개)\s*하지\s*(?:마(?:세요)?|말아(?:줘|주세요)?)\s*[.!。！]*"
)
_FILE_SAFETY = re.compile(
    r"(?:^|(?<=[.!。！;,，]))\s*(?:기존|현재|이전|전체|원본)\s*파일(?:들)?(?:은|을|도)?\s*"
    r"(?:(?:수정|삭제|변경)\s*(?:하거나|및|또는|/|,)\s*)*"
    r"(?:수정|삭제|변경)\s*하지\s*(?:마(?:세요)?|말아(?:줘|주세요)?)\s*(?=$|[.!。！;,，])"
)


# Complete resource constraints are not instructions to cancel ledger work.
_RESOURCE_SAFETY = re.compile(
    r"(?:^|(?<=[.!。！;,，]))\s*(?:(?:기존|현재|이전|전체|원본)\s*)?"
    r"(?:파일|설정)(?:들)?(?:\s*(?:·|및|과|와|/|,)\s*(?:파일|설정)(?:들)?)*"
    r"(?:의|은|는|을|를|도)?\s*"
    r"(?:생성|수정|삭제|변경)(?:\s*(?:하거나|및|또는|/|,|·)\s*(?:생성|수정|삭제|변경))*"
    r"(?:\s*(?:와|과|및)\s*명령\s*실행(?:은|을|도)?)?\s*"
    r"하지\s*(?:마(?:세요)?|말아(?:줘|주세요)?)\s*(?=$|[.!。！;,，])"
)


@dataclass(frozen=True)
class ControlIntent:
    kind: str
    task_id: str = ""


def classify(text: str) -> ControlIntent:
    """Return work_request only when no operation-control meaning is present."""
    value = " ".join(text.strip().split())
    if not value:
        return ControlIntent("work_request")
    match = _ID_COMMAND.fullmatch(value)
    if match:
        verb, task_id = match.groups()
        return ControlIntent({"설명": "task_explain", "why": "task_explain", "취소": "task_cancel", "cancel": "task_cancel", "종결": "task_dismiss", "dismiss": "task_dismiss", "resume": "task_resume", "ack-delivery": "delivery_ack"}[verb.lower()], task_id)
    simple = value.lower().strip("?？!！.。 ")
    if simple in {"tasks", "작업목록", "recovery", "복구", "남은 작업은", "남은 작업은 무엇인가", "남은 작업은 뭐야", "미완료 작업 목록만", "미완료 작업들 존재하나 목록만"}:
        return ControlIntent("task_list")
    if simple in {"status", "/status", "현재 상태", "실행 제한시간", "현재 실행 제한은", "현재 실행 제한시간은"}:
        return ControlIntent("runtime_status")
    if simple in {"취소", "cancel", "/cancel", "이전 목록 모두 취소", "미완료 모두 취소"}:
        return ControlIntent("task_cancel_selection")
    if simple == "tasks all":
        return ControlIntent("work_request")  # Existing Discord admin-only read command.
    if _KNOWN_TASK_COMMAND.match(value):
        return ControlIntent("clarify")
    qualified_list = _LIST_WITH_QUALIFIER.fullmatch(value)
    if qualified_list:
        # Accept only a complete negative safety clause; mixed effects stay held.
        return ControlIntent(
            "task_list" if _NON_MUTATION_QUALIFIER.fullmatch(qualified_list["qualifier"]) else "clarify"
        )
    work_value = _RESOURCE_SAFETY.sub(" ", _FILE_SAFETY.sub(" ", value))
    if work_value != value and (
        _NEGATED.search(work_value) or re.search(TASK_ID, work_value)
        or re.search(r"\b(?:cancel|dismiss|resume|ack-delivery)\b", work_value, re.I)
        or (_LIST_SCOPE.search(work_value) and _CANCEL_VERB.search(work_value))
        or (_QUOTED.search(work_value) and _CONTROL_WORD.search(work_value))
    ):
        return ControlIntent("clarify")
    if _DOCUMENT.search(value):
        return ControlIntent("work_request")
    if (_QUOTED.search(value) and _CONTROL_WORD.search(value)) or _QUOTED_RUNTIME.fullmatch(value):
        return ControlIntent("clarify")
    if work_value != value:
        # Reclassify the actual question; intake retains every original constraint.
        remainder = work_value.strip(" .!。！;,，")
        intent = classify(remainder) if remainder else ControlIntent("clarify")
        return intent if intent.kind in {"work_request", "task_list", "runtime_status"} else ControlIntent("clarify")
    if _NEGATED.search(value):
        return ControlIntent("clarify")
    if _WORK_ACTION.search(value) and _WORK_TARGET.search(value) and not (
        _LIST_SCOPE.search(value) and _CANCEL_VERB.search(value)
    ):
        return ControlIntent("work_request")
    if _RUNTIME_STATUS_QUERY.fullmatch(value):
        return ControlIntent("runtime_status")
    if _LIST_SCOPE.search(value) and _CANCEL_VERB.search(value):
        return ControlIntent("task_cancel_selection") if re.search(r"(?:취소|제거|종결)(?:\s*(?:해|해라|해줘|해주세요|하겠습니다|할게|한다|해요))?[.!。！]*$|하지\s*않겠다", value) else ControlIntent("clarify")
    if _LIST.search(value) and re.search(r"무엇|뭐|존재|있|목록|리스트|보여|알려|조회|확인|남았|남아|몇|\?|？", value):
        return ControlIntent("task_list")
    if _CONTROL_WORD.search(value):
        return ControlIntent("clarify")
    return ControlIntent("work_request")
