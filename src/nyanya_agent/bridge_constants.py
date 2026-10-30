#!/usr/bin/env python3
"""Constants and keyword tables for NyaNya messenger bridges."""

from __future__ import annotations

DEFAULT_TASK_QUEUE_MAX = 2
DEFAULT_PROTECTED_DELETE_PATHS = (
    ".env",
    ".env.sample",
    "src",
    "config",
    "prompts",
    "scripts",
    "pyproject.toml",
    "package.json",
)
CANCEL_COMMANDS = {"취소", "중지", "그만", "cancel", "/cancel", "stop", "/stop"}
CANCEL_ALL_COMMANDS = {"전체취소", "모두취소", "cancel_all", "/cancel_all", "stop_all", "/stop_all"}
CANCEL_USER_COMMANDS = {"사용자취소", "/사용자취소", "cancel_user", "/cancel_user", "stop_user", "/stop_user"}
SET_HOME_COMMANDS = {"set_home", "/set_home", "홈설정", "/홈설정"}
GET_HOME_COMMANDS = {"home", "/home", "get_home", "/get_home", "홈", "/홈"}
UNSET_HOME_COMMANDS = {"unset_home", "/unset_home", "홈해제", "/홈해제"}
HELP_COMMANDS = {"help", "/help", "commands", "/commands", "명령어", "/명령어", "도움말", "/도움말"}
REVIEWED_FILE_COMMANDS = frozenset({
    "plan", "plan-file", "approve", "revoke", "reconcile", "resolve",
    "open-draft", "draft-show", "draft-close", "draft-feedback",
})
TASK_STATUS_COMMANDS = {
    "tasks",
    "/tasks",
    "task",
    "/task",
    "queue",
    "/queue",
    "작업",
    "/작업",
    "작업목록",
    "/작업목록",
    "대기열",
    "/대기열",
    "진행상태",
    "/진행상태",
}
FILE_MUTATION_KEYWORDS = (
    "add",
    "append",
    "change",
    "copy",
    "create",
    "delete",
    "edit",
    "make",
    "mkdir",
    "modify",
    "move",
    "patch",
    "remove",
    "rename",
    "replace",
    "save",
    "touch",
    "update",
    "write",
    "고쳐",
    "덮어",
    "만들",
    "바꿔",
    "복사",
    "삭제",
    "생성",
    "수정",
    "옮겨",
    "이동",
    "작성",
    "저장",
    "추가",
    "패치",
)
FILE_MUTATION_NEGATIONS = (
    "no changes",
    "no edit",
    "no modification",
    "read only",
    "read-only",
    "without changing",
    "without deleting",
    "without editing",
    "without modifying",
    "변경 없이",
    "삭제 없이",
    "생성 없이",
    "수정 없이",
    "쓰기 없이",
    "작성 없이",
    "저장 없이",
    "추가 없이",
    "편집 없이",
    "읽기 전용",
)
PROTECTED_DELETE_KEYWORDS = (
    "delete",
    "erase",
    "move",
    "remove",
    "rename",
    "rm",
    "rm -rf",
    "trash",
    "truncate",
    "unlink",
    "비워",
    "삭제",
    "없애",
    "옮겨",
    "이동",
    "이름 변경",
    "제거",
    "지워",
    "초기화",
)
