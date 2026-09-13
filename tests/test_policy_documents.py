from __future__ import annotations

from nyanya_agent.bridge_policy import task_operating_protocol_text
from nyanya_agent.policy_documents import POLICY_FILES, load_policy_documents


def test_markdown_policy_set_is_loaded_into_operating_protocol():
    documents = load_policy_documents()

    assert set(documents) == set(POLICY_FILES)
    protocol = task_operating_protocol_text()
    assert "Canonical Markdown policy:" in protocol
    assert "SQLite execution records are the authority" in protocol
    assert "Tailscale" in protocol
    assert "Review gates" in protocol
