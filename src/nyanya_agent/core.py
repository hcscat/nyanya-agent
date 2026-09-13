#!/usr/bin/env python3
"""NyaNya local agent CLI.

This client uses only the Python standard library and can talk to:
- Ollama: http://127.0.0.1:11434/api/chat
- OpenAI-compatible local servers: http://127.0.0.1:8000/v1/chat/completions
- Gemini/Antigravity CLI: OAuth-backed `gemini` or `agy`
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from nyanya_agent import runtime_paths
from nyanya_agent.task_outcomes import OutcomeSignal

SOURCE_ROOT = runtime_paths.SOURCE_ROOT
PROJECT_ROOT = runtime_paths.CODE_ROOT
STATE_ROOT = runtime_paths.STATE_ROOT
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "nyanya.json"
DEFAULT_ENV = runtime_paths.ENV_FILE


def load_env(path: pathlib.Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def load_config(path: pathlib.Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    provider = os.getenv("NYANYA_PROVIDER", data.get("provider", "ollama"))
    if provider == "openai_compatible":
        base_url = os.getenv("NYANYA_OPENAI_BASE_URL", "http://127.0.0.1:8000")
    elif provider == "gemini_cli":
        base_url = ""
    else:
        base_url = os.getenv("NYANYA_OLLAMA_BASE_URL", data.get("base_url", "http://127.0.0.1:11434"))

    if provider == "gemini_cli":
        model = os.getenv("NYANYA_GEMINI_MODEL", "").strip() or os.getenv("NYANYA_MODEL", "").strip()
        model = model or "gemini-cli-default"
    elif provider == "ollama":
        model = os.getenv("NYANYA_OLLAMA_MODEL", "").strip() or os.getenv("NYANYA_MODEL", "").strip()
        model = model or data.get("model", "qwen3:4b")
    else:
        model = os.getenv("NYANYA_MODEL", data.get("model", "qwen3:4b"))

    data.update(
        {
            "provider": provider,
            "model": model,
            "base_url": base_url.rstrip("/"),
            "system_prompt_path": os.getenv("NYANYA_SYSTEM_PROMPT_PATH", data.get("system_prompt_path", "prompts/system.md")),
            "agent_memory_path": os.getenv(
                "NYANYA_AGENT_MEMORY_PATH",
                data.get("agent_memory_path", "prompts/agent_memory.md"),
            ),
            "sessions_dir": os.getenv("NYANYA_SESSIONS_DIR", data.get("sessions_dir", "sessions")),
            "temperature": float(os.getenv("NYANYA_TEMPERATURE", data.get("temperature", 0.3))),
            "timeout_seconds": int(os.getenv("NYANYA_TIMEOUT_SECONDS", data.get("timeout_seconds", 120))),
            "gemini_cli": os.getenv("NYANYA_GEMINI_CLI", "gemini"),
            "gemini_approval_mode": os.getenv("NYANYA_GEMINI_APPROVAL_MODE", "plan"),
            "save_transcripts": parse_bool(
                os.getenv("NYANYA_SAVE_TRANSCRIPTS", str(data.get("save_transcripts", True)))
            ),
        }
    )
    return data


def parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def agent_display_name(config: dict[str, Any]) -> str:
    return str(config.get("agent_name") or "NyaNya Agent")


def read_system_prompt(config: dict[str, Any]) -> str:
    prompt_path = pathlib.Path(config["system_prompt_path"])
    if not prompt_path.is_absolute():
        prompt_path = PROJECT_ROOT / prompt_path
    return prompt_path.read_text(encoding="utf-8")


def read_agent_memory(config: dict[str, Any]) -> str:
    memory_path_value = str(config.get("agent_memory_path", "")).strip()
    if not memory_path_value:
        return ""
    memory_path = pathlib.Path(memory_path_value)
    if not memory_path.is_absolute():
        memory_path = PROJECT_ROOT / memory_path
    if not memory_path.exists():
        return ""
    return memory_path.read_text(encoding="utf-8")


def build_system_context(config: dict[str, Any]) -> str:
    system_prompt = read_system_prompt(config).strip()
    agent_memory = read_agent_memory(config).strip()
    if not agent_memory:
        return system_prompt
    return f"{system_prompt}\n\n# NyaNya Agent Memory\n\n{agent_memory}"


def build_dynamic_memory_context(prompt: str, *, owner_key: str | None = None, limit: int | None = None) -> str:
    if not parse_bool(os.getenv("NYANYA_MEMORY_RETRIEVAL_ENABLED", "true")):
        return ""
    if not prompt.strip():
        return ""
    try:
        from nyanya_agent import dashboard_store

        memories = dashboard_store.search_approved_memories(
            prompt,
            owner_key=owner_key,
            limit=limit or int(os.getenv("NYANYA_MEMORY_RETRIEVAL_LIMIT", "5")),
        )
        return dashboard_store.format_memory_context(
            memories,
            char_limit=int(os.getenv("NYANYA_MEMORY_CONTEXT_MAX_CHARS", "1800")),
        )
    except Exception:  # noqa: BLE001 - memory retrieval must never break the main answer path.
        return ""


def request_json(url: str, payload: dict[str, Any] | None, timeout: int, headers: dict[str, str] | None = None) -> Any:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Backend URL must use http or https")
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=body, headers=req_headers)
    # The URL scheme is restricted to HTTP(S) immediately above.
    with urllib.request.urlopen(req, timeout=timeout) as response:  # nosec B310
        raw = response.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def check_backend(config: dict[str, Any]) -> int:
    provider = config["provider"]
    base_url = config["base_url"]
    timeout = config["timeout_seconds"]
    try:
        if provider == "ollama":
            data = request_json(f"{base_url}/api/version", None, timeout)
            print(f"OK: Ollama reachable at {base_url}; version={data.get('version', 'unknown')}")
        elif provider == "openai_compatible":
            headers = openai_headers()
            data = request_json(f"{base_url}/v1/models", None, timeout, headers=headers)
            count = len(data.get("data", [])) if isinstance(data, dict) else "unknown"
            print(f"OK: OpenAI-compatible server reachable at {base_url}; models={count}")
        elif provider == "gemini_cli":
            expected = "NYANYA_GEMINI_OK"
            answer = gemini_chat_once(config, [{"role": "user", "content": f"Return exactly: {expected}"}])
            cleaned = answer.strip()
            if cleaned != expected:
                print(f"Backend check failed: expected {expected}, got: {cleaned}", file=sys.stderr)
                return 1
            print(f"OK: Google CLI reachable; response={cleaned}")
        else:
            print(f"Unsupported provider: {provider}", file=sys.stderr)
            return 2
        return 0
    except subprocess.TimeoutExpired as exc:
        print(f"Backend check timed out after {exc.timeout} seconds", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"Backend check failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - backend checks should explain CLI failures.
        print(f"Backend check failed: {exc}", file=sys.stderr)
        return 1


def openai_headers() -> dict[str, str]:
    api_key = os.getenv("NYANYA_OPENAI_API_KEY", "")
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


def resolve_executable(command: str) -> str:
    expanded = str(pathlib.Path(command).expanduser()) if command.startswith(("~", "/")) else command
    resolved = shutil.which(expanded)
    if resolved:
        return resolved
    candidate = pathlib.Path(expanded)
    if candidate.exists():
        return str(candidate)
    return expanded


def resolve_gemini_like_cli(command: str) -> str:
    """An explicit executable must never silently switch provider installations."""
    resolved = shutil.which(os.path.expanduser(command))
    if not resolved or not pathlib.Path(resolved).is_file():
        raise OutcomeSignal("blocked", "설정된 Gemini/agy 실행 파일이 없거나 실행할 수 없습니다.")
    return resolved


def is_antigravity_cli(command: str) -> bool:
    path = pathlib.Path(command)
    name = path.name.lower()
    return name in {"agy", "antigravity"} or "antigravity" in str(path).lower()


def configured_workspace_roots() -> list[pathlib.Path]:
    raw_roots = os.getenv("NYANYA_WORKSPACE_ROOTS", "").strip()
    if raw_roots:
        roots = [
            pathlib.Path(item.strip()).expanduser().resolve(strict=False)
            for item in raw_roots.split(",")
            if item.strip()
        ]
    else:
        raw_root = os.getenv("NYANYA_WORKSPACE_ROOT", "").strip()
        roots = [pathlib.Path(raw_root).expanduser().resolve(strict=False)] if raw_root else [PROJECT_ROOT]
    unique: list[pathlib.Path] = []
    for root in roots:
        if root not in unique:
            unique.append(root)
    return unique


def default_cli_workspace() -> pathlib.Path:
    configured = os.getenv("NYANYA_CODEX_WORKDIR", "").strip()
    if configured:
        return pathlib.Path(configured).expanduser().resolve(strict=False)
    roots = configured_workspace_roots()
    return roots[0] if roots else PROJECT_ROOT


def dir_summary(path: pathlib.Path) -> str:
    if not path.exists():
        return f"{path}: missing"
    if not path.is_dir():
        return f"{path}: not a directory"
    file_count = 0
    total_bytes = 0
    for item in path.rglob("*"):
        if item.is_file():
            file_count += 1
            try:
                total_bytes += item.stat().st_size
            except OSError:
                pass
    return f"{path}: files={file_count}, size_mb={total_bytes / 1024 / 1024:.1f}"


def process_summary(pattern: str) -> str:
    proc = subprocess.run(["pgrep", "-af", pattern], text=True, capture_output=True, timeout=5, check=False)
    lines = [line for line in proc.stdout.splitlines() if "pgrep -af" not in line]
    return "none" if not lines else "; ".join(lines[:5])


def runtime_status_context(config: dict[str, Any]) -> str:
    resolved_google_cli = resolve_gemini_like_cli(str(config.get("gemini_cli") or "gemini"))
    google_cli_family = "antigravity" if is_antigravity_cli(resolved_google_cli) else "gemini"
    pid_file = STATE_ROOT / "run" / "ollama.pid"
    if pid_file.exists():
        pid_text = pid_file.read_text(encoding="utf-8").strip()
        pid_state = f"present value={pid_text or '<empty>'}"
    else:
        pid_state = "absent"

    configured_model_dir = pathlib.Path(os.getenv("NYANYA_OLLAMA_MODELS_DIR", "")).expanduser()
    if not str(configured_model_dir):
        configured_model_dir = pathlib.Path.home() / ".ollama" / "models"

    lines = [
        f"Runtime status as observed by {agent_display_name(config)} before calling the model:",
        f"- active_provider={config.get('provider')}",
        f"- active_model={config.get('model')}",
        f"- google_cli_family={google_cli_family}",
        f"- configured_google_cli={config.get('gemini_cli')}",
        f"- resolved_google_cli={resolved_google_cli}",
        f"- process_working_directory={PROJECT_ROOT}",
        f"- runtime_state_directory={STATE_ROOT}",
        f"- default_cli_workspace={default_cli_workspace()}",
        f"- allowed_workspace_roots={', '.join(str(root) for root in configured_workspace_roots())}",
        f"- ollama_pid_file={pid_state}",
        f"- ollama_processes={process_summary('ollama')}",
        f"- configured_ollama_model_dir={dir_summary(configured_model_dir)}",
        f"- default_ollama_model_dir={dir_summary(pathlib.Path.home() / '.ollama' / 'models')}",
        "- local_ollama_policy=disabled for normal operation; not the messenger backend",
    ]
    return "\n".join(lines)


def format_cli_conversation(config: dict[str, Any], messages: list[dict[str, str]]) -> str:
    role_names = {
        "system": "System instructions",
        "user": "User",
        "assistant": "Assistant",
    }
    parts = [
        f"Answer as {agent_display_name(config)}. Use the full conversation context below and reply to the final user message.",
        "Keep the answer concise and useful. If the user writes in Korean, answer in Korean.",
    ]
    for message in messages:
        role = role_names.get(message.get("role", ""), message.get("role", "message").title())
        content = message.get("content", "")
        parts.append(f"\n{role}:\n{content}")
    return "\n".join(parts).strip()


def clean_cli_output(text: str) -> str:
    noisy_prefixes = (
        "Warning: Basic terminal detected",
        "Warning: 256-color support not detected",
        "Ripgrep is not available.",
    )
    lines = [line for line in text.splitlines() if not line.startswith(noisy_prefixes)]
    return "\n".join(lines).strip()


def run_cancellable_command(
    command: list[str],
    *,
    cwd: pathlib.Path,
    timeout: int,
    cancel_event: Any | None = None,
) -> tuple[int, str, str]:
    proc = subprocess.Popen(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    deadline = time.monotonic() + timeout
    while True:
        if cancel_event is not None and cancel_event.is_set():
            proc.terminate()
            try:
                stdout, stderr = proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate()
            return -15, stdout or "", stderr or "요청이 취소되었습니다."
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            proc.terminate()
            try:
                stdout, stderr = proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate()
            raise subprocess.TimeoutExpired(command, timeout, output=stdout, stderr=stderr)
        try:
            stdout, stderr = proc.communicate(timeout=min(0.25, remaining))
            return proc.returncode, stdout or "", stderr or ""
        except subprocess.TimeoutExpired:
            continue


def gemini_chat_once(config: dict[str, Any], messages: list[dict[str, str]], cancel_event: Any | None = None, workspace: pathlib.Path | None = None) -> str:
    cli = resolve_gemini_like_cli(str(config.get("gemini_cli") or "gemini"))
    prompt = format_cli_conversation(config, messages)
    if is_antigravity_cli(cli):
        command = [
            cli,
            "--prompt",
            prompt,
            "--print-timeout",
            f"{int(config['timeout_seconds'])}s",
        ]
        command.append("--sandbox")
    else:
        command = [
            cli,
            "--prompt",
            prompt,
            "--skip-trust",
            "--approval-mode",
            "plan",
            "--output-format",
            "text",
        ]
        model = os.getenv("NYANYA_GEMINI_MODEL", "").strip()
        if model:
            command.extend(["--model", model])

    try:
        returncode, raw_stdout, raw_stderr = run_cancellable_command(
            command,
            cwd=workspace if workspace is not None else default_cli_workspace(),
            timeout=int(config["timeout_seconds"]),
            cancel_event=cancel_event,
        )
    except subprocess.TimeoutExpired as exc:
        raise OutcomeSignal("timed_out", "Gemini/agy 실행 제한 시간을 초과했습니다.") from exc
    stdout = clean_cli_output(raw_stdout)
    stderr = clean_cli_output(raw_stderr)
    if returncode == -15:
        raise OutcomeSignal("cancelled", "요청이 취소되었습니다.")
    if returncode != 0:
        raise OutcomeSignal("failed", f"Gemini/agy 실행 실패 (exit={returncode}).")
    return stdout or stderr


def chat_once(config: dict[str, Any], messages: list[dict[str, str]], cancel_event: Any | None = None, workspace: pathlib.Path | None = None) -> str:
    provider = config["provider"]
    if provider == "ollama":
        payload = {
            "model": config["model"],
            "messages": messages,
            "stream": False,
            "options": {"temperature": config["temperature"]},
        }
        data = request_json(f"{config['base_url']}/api/chat", payload, config["timeout_seconds"])
        return data.get("message", {}).get("content", "")
    if provider == "openai_compatible":
        payload = {
            "model": config["model"],
            "messages": messages,
            "temperature": config["temperature"],
            "stream": False,
        }
        data = request_json(
            f"{config['base_url']}/v1/chat/completions",
            payload,
            config["timeout_seconds"],
            headers=openai_headers(),
        )
        return data["choices"][0]["message"]["content"]
    if provider == "gemini_cli":
        return gemini_chat_once(config, messages, cancel_event=cancel_event, workspace=workspace)
    raise ValueError(f"Unsupported provider: {provider}")


def guarded_chat_once(config, messages, cancel_event=None, workspace=None):
    from nyanya_agent.bridge_policy import classify_request_risk
    if workspace is None or not workspace.is_dir():
        raise OutcomeSignal("blocked", "유효한 작업공간을 설정하세요.")
    prompt = next((item["content"] for item in reversed(messages) if item.get("role") == "user"), "")
    risk = classify_request_risk(prompt, workdir=workspace)
    if risk["stop"] or risk["requires_approval"]:
        from nyanya_agent.bridge_policy import risk_plan_response
        raise OutcomeSignal("blocked" if risk["stop"] else "awaiting_approval",
                            risk_plan_response(prompt, risk, workdir=workspace))
    return chat_once(config, messages, cancel_event=cancel_event, workspace=workspace)


def save_session(config: dict[str, Any], messages: list[dict[str, str]]) -> pathlib.Path | None:
    if not config.get("save_transcripts", True):
        return None
    sessions_dir = pathlib.Path(config.get("sessions_dir", "sessions"))
    if not sessions_dir.is_absolute():
        sessions_dir = STATE_ROOT / sessions_dir
    sessions_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = sessions_dir / f"nyanya-{stamp}.json"
    payload = {
        "agent_name": agent_display_name(config),
        "provider": config["provider"],
        "model": config["model"],
        "base_url": config["base_url"],
        "created_at": dt.datetime.now().isoformat(timespec="seconds"),
        "messages": messages,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def build_messages(config: dict[str, Any]) -> list[dict[str, str]]:
    return [{"role": "system", "content": build_system_context(config)}]


def run_single_prompt(config: dict[str, Any], prompt: str) -> int:
    from nyanya_agent.bridge_policy import default_codex_workdir
    from nyanya_agent.operation_service import OperationService
    service = OperationService()
    owner = 'operator'
    try:
        control = service.control(prompt, owner)
        if control is not None:
            print(control)
            return 0
        task = service.submit(prompt, default_codex_workdir(), owner)
        answer = service.wait(task['id'], owner)
        print(answer.text)
        return 0 if answer.status == 'succeeded' else 1
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"작업 접수/실행 실패: {type(exc).__name__}", file=sys.stderr)
        return 1
    finally:
        service.close()


def run_repl(config: dict[str, Any]) -> int:
    from nyanya_agent.bridge_policy import default_codex_workdir
    from nyanya_agent.operation_service import OperationService
    service = OperationService()
    messages: list[dict[str, str]] = []
    print(f"{agent_display_name(config)} — /exit, /reset, /save, /config, /settings, /dashboard")
    print("recovery 미완료 목록 · why 작업ID 원인 · plan 변경안ID · approve 변경안ID hash")
    try:
        while True:
            try:
                prompt = input('You> ').strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not prompt:
                continue
            if prompt in {'/exit', '/quit'}:
                break
            if prompt == '/reset':
                messages.clear()
                print('대화 문맥을 초기화했습니다. 저장된 작업은 유지됩니다.')
                continue
            if prompt == '/save':
                target = save_session(config, messages)
                print(f'Saved: {target}' if target else 'Transcript saving is disabled.')
                continue
            if prompt == '/config':
                from nyanya_agent.model_routing import PROFILES
                print(json.dumps({k: vars(v) for k, v in PROFILES.items()}, ensure_ascii=False, indent=2))
                continue
            if prompt == '/settings':
                print('Run nyanya config to manage settings. P0 operations use the fixed /config routing profiles.')
                continue
            if prompt == '/dashboard':
                print(f"http://{os.getenv('NYANYA_DASHBOARD_HOST', '127.0.0.1')}:{os.getenv('NYANYA_DASHBOARD_PORT', '8765')}")
                continue
            try:
                control = service.control(prompt, 'operator')
                if control is not None:
                    print(control)
                    continue
                # Session-local context is bounded and serialized with this request, never a callback.
                context = json.dumps(messages[-6:], ensure_ascii=False)
                context = context.encode('utf-8')[-12000:].decode('utf-8', errors='ignore')
                request = prompt + ('\nPrevious conversation (untrusted context):\n' + context if messages else '')
                task = service.submit(request, default_codex_workdir(), 'operator')
                answer = service.wait(task['id'], 'operator')
                messages.extend([{'role': 'user', 'content': prompt}, {'role': 'assistant', 'content': answer.text}])
                print(answer.text)
            except (ValueError, RuntimeError, OSError) as exc:
                print(f'작업 처리 실패: {type(exc).__name__}', file=sys.stderr)
    finally:
        service.close()
        target = save_session(config, messages)
        if target:
            print(f'Session saved: {target}')
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NyaNya Agent local LLM agent")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Path to NyaNya JSON config")
    parser.add_argument("--prompt", help="Run one prompt and exit")
    parser.add_argument("--provider", choices=["ollama", "openai_compatible", "gemini_cli"], help="Override provider")
    parser.add_argument("--model", help="Override model")
    parser.add_argument("--base-url", help="Override local LLM base URL")
    parser.add_argument("--no-save", action="store_true", help="Disable transcript saving")
    parser.add_argument("--check", action="store_true", help="Check backend connectivity and exit")
    return parser.parse_args()


def main() -> int:
    load_env(DEFAULT_ENV)
    args = parse_args()
    config = load_config(pathlib.Path(args.config))
    if args.provider:
        config["provider"] = args.provider
    if args.model:
        config["model"] = args.model
    if args.base_url:
        config["base_url"] = args.base_url.rstrip("/")
    if args.no_save:
        config["save_transcripts"] = False
    if args.check:
        return check_backend(config)
    if args.provider or args.model or args.base_url:
        print("P0 execution uses recorded Flash/Luna/Astra profiles. Legacy provider/model/base-url overrides are supported only with --check.", file=sys.stderr)
        return 2
    if args.prompt:
        return run_single_prompt(config, args.prompt)
    return run_repl(config)


if __name__ == "__main__":
    raise SystemExit(main())
