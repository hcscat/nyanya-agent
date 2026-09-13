"""Load the human-maintained Markdown policy supplements."""

from __future__ import annotations

from pathlib import Path


POLICY_FILES = (
    "policy.md",
    "policy_technical.md",
    "policy_governance.md",
)


def policy_directory() -> Path:
    return Path(__file__).resolve().parents[2] / "prompts"


def load_policy_documents() -> dict[str, str]:
    documents: dict[str, str] = {}
    for filename in POLICY_FILES:
        path = policy_directory() / filename
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if text:
            documents[filename] = text
    return documents


def policy_document_text() -> str:
    return "\n\n".join(load_policy_documents().values())
