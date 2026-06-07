#!/usr/bin/env python3
"""Telegram bridge for NyaNya using the Bot API long-polling endpoint."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from nyanya_agent.bridge_common import (
    CANCEL_ALL_COMMANDS,
    CANCEL_COMMANDS,
    CANCEL_USER_COMMANDS,
    GET_HOME_COMMANDS,
    HELP_COMMANDS,
    NyaNyaConversationStore,
    SET_HOME_COMMANDS,
    UNSET_HOME_COMMANDS,
    command_name,
    env_first,
    load_runtime_config,
    normalize_owner_key,
    parse_bool,
    parse_id_set,
    split_message,
    telegram_help_text,
)


TELEGRAM_LIMIT = 3900


class TelegramBridge:
    def __init__(self, token: str, store: NyaNyaConversationStore) -> None:
        self.token = token
        self.store = store
        self.api_base = f"https://api.telegram.org/bot{token}"
        self.allowed_chat_ids = parse_id_set(os.getenv("NYANYA_TELEGRAM_ALLOWED_CHAT_IDS"))
        self.allowed_user_ids = parse_id_set(os.getenv("NYANYA_TELEGRAM_ALLOWED_USER_IDS"))
        self.allow_unlisted = parse_bool(os.getenv("NYANYA_ALLOW_UNLISTED"), False)
        self.offset = 0

    def run(self) -> int:
        print("NyaNya Telegram bridge started.")
        while True:
            try:
                updates = self.api("getUpdates", {"timeout": 30, "offset": self.offset}).get("result", [])
                for update in updates:
                    self.offset = max(self.offset, int(update.get("update_id", 0)) + 1)
                    self.handle_update(update)
            except KeyboardInterrupt:
                print()
                return 0
            except Exception as exc:  # noqa: BLE001 - long-running bridge should keep polling.
                print(f"Telegram bridge error: {exc}", file=sys.stderr)
                time.sleep(3)

    def handle_update(self, update: dict[str, Any]) -> None:
        message = update.get("message") or update.get("edited_message")
        if not message:
            return
        text = (message.get("text") or "").strip()
        if not text:
            return
        chat = message.get("chat", {})
        sender = message.get("from", {})
        chat_id = str(chat.get("id", ""))
        user_id = str(sender.get("id", ""))

        command = command_name(text)
        if command == "/start" or command in HELP_COMMANDS:
            self.send(
                chat_id,
                telegram_help_text(
                    chat_id=chat_id,
                    user_id=user_id,
                    is_admin=self.store.is_owner(user_id),
                ),
            )
            return

        if not self.is_allowed(chat_id, user_id):
            self.send(
                chat_id,
                "이 채팅은 아직 NyaNya 허용 목록에 없습니다.\n"
                f"NYANYA_TELEGRAM_ALLOWED_CHAT_IDS={chat_id}\n"
                f"NYANYA_TELEGRAM_ALLOWED_USER_IDS={user_id}\n"
                "위 값 중 하나를 .env에 추가한 뒤 브리지를 다시 시작하세요.",
            )
            return

        owner_key = f"telegram-user:{user_id}"
        conversation_key = f"telegram:{chat_id}:user:{user_id}"
        response = self.handle_command(owner_key, conversation_key, chat_id, user_id, text)
        self.send(chat_id, response)

    def is_allowed(self, chat_id: str, user_id: str) -> bool:
        if self.allow_unlisted:
            return True
        return chat_id in self.allowed_chat_ids or user_id in self.allowed_user_ids

    def handle_command(self, owner_key: str, conversation_key: str, chat_id: str, user_id: str, text: str) -> str:
        command = command_name(text)
        responder = lambda response: self.send(chat_id, response)
        if command in CANCEL_ALL_COMMANDS:
            if not self.store.is_owner(user_id):
                return "전체 취소는 관리자만 사용할 수 있습니다."
            return self.store.cancel_all()
        if command in CANCEL_USER_COMMANDS:
            if not self.store.is_owner(user_id):
                return "사용자 취소는 관리자만 사용할 수 있습니다."
            target = text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) > 1 else ""
            if not target:
                return "사용법: 사용자취소 telegram_user_id 또는 사용자취소 telegram-user:telegram_user_id"
            target_owner = target if ":" in target else f"telegram-user:{target}"
            return self.store.cancel_owner(target_owner)
        if command in CANCEL_COMMANDS:
            return self.store.cancel_owner(owner_key)
        if command in SET_HOME_COMMANDS:
            if not self.store.is_owner(user_id):
                return "홈워크스페이스 설정은 관리자만 사용할 수 있습니다."
            parts = text.split(maxsplit=2)
            if len(parts) < 3:
                return "사용법: /set_home telegram_user_id HCS 또는 /set_home discord-user:discord_user_id HCS"
            try:
                target_owner = normalize_owner_key(parts[1], "telegram")
            except ValueError as exc:
                return str(exc)
            return self.store.set_home(target_owner, parts[2], set_by=owner_key)
        if command in UNSET_HOME_COMMANDS:
            if not self.store.is_owner(user_id):
                return "홈워크스페이스 해제는 관리자만 사용할 수 있습니다."
            target = text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) > 1 else ""
            if not target:
                return "사용법: /unset_home telegram_user_id 또는 /unset_home discord-user:discord_user_id"
            try:
                target_owner = normalize_owner_key(target, "telegram")
            except ValueError as exc:
                return str(exc)
            return self.store.unset_home(target_owner)
        if command in GET_HOME_COMMANDS:
            target = text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) > 1 else ""
            if target:
                if not self.store.is_owner(user_id):
                    return "다른 사용자의 홈워크스페이스 조회는 관리자만 사용할 수 있습니다."
                try:
                    target_owner = normalize_owner_key(target, "telegram")
                except ValueError as exc:
                    return str(exc)
            else:
                target_owner = owner_key
            return self.store.home_text(target_owner)
        if command == "/reset":
            self.store.reset(conversation_key)
            return "대화 컨텍스트를 초기화했습니다."
        if command == "/save":
            path = self.store.save(conversation_key)
            return f"저장했습니다: {path}" if path else "세션 저장이 꺼져 있습니다."
        if command == "/status":
            return (
                "NyaNya bridge is running.\n"
                f"provider={self.store.config.get('provider')}\n"
                f"model={self.store.config.get('model')}"
            )
        if command == "/config":
            return self.store.status_text()
        if command == "/gemini":
            prompt = text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) > 1 else ""
            if not prompt:
                return "사용법: /gemini Google CLI에 물어볼 내용을 적어주세요."
            return self.store.submit(
                owner_key=owner_key,
                conversation_key=conversation_key,
                prompt=prompt,
                mode="gemini",
                responder=responder,
            )
        if command == "/codex":
            prompt = text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) > 1 else ""
            if not prompt:
                return "사용법: /codex 검수하거나 조사할 내용을 적어주세요."
            return self.store.submit(
                owner_key=owner_key,
                conversation_key=conversation_key,
                prompt=prompt,
                mode="codex",
                responder=responder,
            )
        if command in {"/codex_work", "/codexwork"}:
            prompt = text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) > 1 else ""
            if not prompt:
                return "사용법: /codex_work Codex에 맡길 작업을 적어주세요."
            return self.store.submit(
                owner_key=owner_key,
                conversation_key=conversation_key,
                prompt=prompt,
                mode="codex_write",
                responder=responder,
            )
        if command in {"/resources", "/resource", "/리소스"}:
            try:
                return self.store.resources()
            except Exception as exc:  # noqa: BLE001
                return f"리소스 조회 실패: {exc}"
        return self.store.submit(
            owner_key=owner_key,
            conversation_key=conversation_key,
            prompt=text,
            mode="auto",
            responder=responder,
        )

    def send(self, chat_id: str, text: str) -> None:
        for chunk in split_message(text, TELEGRAM_LIMIT):
            self.api("sendMessage", {"chat_id": chat_id, "text": chunk})

    def api(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = urllib.parse.urlencode(payload).encode("utf-8")
        request = urllib.request.Request(f"{self.api_base}/{method}", data=data)
        with urllib.request.urlopen(request, timeout=45) as response:
            body = response.read().decode("utf-8")
        parsed = json.loads(body)
        if not parsed.get("ok"):
            raise RuntimeError(parsed)
        return parsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run NyaNya Telegram bridge")
    parser.add_argument("--config", help="Path to NyaNya JSON config")
    parser.add_argument("--check-config", action="store_true", help="Validate bridge config and exit")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_runtime_config(args.config)
    token = env_first("NYANYA_TELEGRAM_BOT_TOKEN", "TELEGRAM_BOT_TOKEN")
    if args.check_config:
        print(f"telegram_token_configured={bool(token)}")
        print(f"provider={config.get('provider')}")
        print(f"model={config.get('model')}")
        print(f"allowed_chat_ids={bool(os.getenv('NYANYA_TELEGRAM_ALLOWED_CHAT_IDS'))}")
        print(f"allowed_user_ids={bool(os.getenv('NYANYA_TELEGRAM_ALLOWED_USER_IDS'))}")
        print(f"allow_unlisted={parse_bool(os.getenv('NYANYA_ALLOW_UNLISTED'), False)}")
        return 0 if token else 2
    if not token:
        print("Missing NYANYA_TELEGRAM_BOT_TOKEN in .env", file=sys.stderr)
        return 2
    return TelegramBridge(token, NyaNyaConversationStore(config)).run()


if __name__ == "__main__":
    raise SystemExit(main())
