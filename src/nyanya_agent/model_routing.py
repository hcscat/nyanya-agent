"""Bounded routing with explicit model/effort identities; no silent fallback."""

from nyanya_agent.task_outcomes import SafeOperationError
from dataclasses import dataclass
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from nyanya_agent.task_outcomes import OutcomeSignal
from nyanya_agent.codex_cli import resolve_codex_cli


@dataclass(frozen=True)
class ModelProfile:
    runtime: str
    model: str
    effort: str


PROFILES = {
    "flash": ModelProfile("agy", "gemini-3.8-flash-medium", "medium"),
    "luna": ModelProfile("codex", "gpt-5.6-luna", "xhigh"),
    "astra": ModelProfile("codex", "gpt-6-astra", "low"),
}


def parse_object(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    value = json.loads(text)
    if not isinstance(value, dict):
        raise SafeOperationError("Expected JSON object")
    return value


def route(assessment):
    if assessment.get("task_kind", "work") not in {"work", "analysis", "code", "document", "data"}:
        raise SafeOperationError("Invalid task kind")
    for key in ("importance", "impact", "complexity"):
        if type(assessment.get(key)) is not int or not 1 <= assessment[key] <= 5:
            raise SafeOperationError("Invalid routing score")
    if not isinstance(assessment.get("reason"), str) or len(assessment["reason"]) > 2000:
        raise SafeOperationError("Invalid routing reason")
    if assessment["impact"] >= 4 or assessment["importance"] >= 4 or assessment["complexity"] >= 5:
        return "astra"
    return "luna" if assessment["complexity"] >= 3 else "flash"


def invoke(profile_key, prompt, workspace, timeout, cancel_event):
    from nyanya_agent.process_runner import run_command

    if len(prompt.encode("utf-8")) > 100_000:
        raise SafeOperationError("Model input exceeds the bounded CLI payload; narrow the request or file scope")
    profile = PROFILES[profile_key]
    if profile.runtime == "agy":
        configured = os.getenv("NYANYA_AGY_CLI", "agy")
        binary = shutil.which(configured)
        if not binary:
            raise OutcomeSignal("blocked", "agy 실행 파일을 찾지 못했습니다. 모델을 대체하지 않았습니다.")
        command = [
            binary,
            "--prompt",
            prompt,
            "--model",
            profile.model,
            "--effort",
            profile.effort,
            "--mode",
            "plan",
            "--sandbox",
            "--disable-slash-commands",
            "--print-timeout",
            f"{timeout}s",
        ]
        rc, stdout, _ = run_command(command, cwd=workspace, timeout=timeout, cancel_event=cancel_event)
    else:
        binary = resolve_codex_cli()
        if not binary:
            raise OutcomeSignal("blocked", "Codex 실행 파일을 찾지 못했습니다. 모델을 대체하지 않았습니다.")
        with tempfile.TemporaryDirectory(prefix="nyanya-model-") as directory:
            output = Path(directory) / "result.txt"
            command = [
                binary,
                "exec",
                "--ignore-user-config",
                "--ephemeral",
                "--skip-git-repo-check",
                "-s",
                "read-only",
                "-m",
                profile.model,
                "-c",
                f'model_reasoning_effort="{profile.effort}"',
                "-o",
                str(output),
                prompt,
            ]
            rc, _, _ = run_command(command, cwd=workspace, timeout=timeout, cancel_event=cancel_event)
            stdout = output.read_text() if output.is_file() else ""
    if rc != 0:
        raise OutcomeSignal("blocked", f"{profile.model} 실행 실패(exit={rc}). 모델 접근·인증·CLI 지원을 확인하세요.")
    if not stdout.strip():
        raise OutcomeSignal("failed", "모델의 최종 응답이 비어 있습니다.")
    return stdout


def preflight():
    """Read-only local CLI capability check; never a model completion claim."""
    result = {}
    for name, binary in [("agy", shutil.which(os.getenv("NYANYA_AGY_CLI", "agy"))), ("codex", resolve_codex_cli())]:
        if not binary:
            result[name] = {"available": False}
            continue
        try:
            proc = subprocess.run([binary, "--help"], capture_output=True, text=True, timeout=10)
            result[name] = {"available": proc.returncode == 0}
        except (OSError, subprocess.TimeoutExpired):
            result[name] = {"available": False}
    return result
