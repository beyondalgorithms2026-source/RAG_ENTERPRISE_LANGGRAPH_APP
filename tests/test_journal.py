from __future__ import annotations

import json

from rag_enterprise_langgraph.journal import sanitize_for_journal, write_journal_entry


def test_journal_sanitizes_debug_paths_and_secrets(tmp_path):
    journal = tmp_path / "runs" / "journal.jsonl"

    write_journal_entry(
        journal,
        {
            "question": "Q",
            "backend_bearer_token": "secret",
            "debug_info": {"system_prompt": "hidden"},
            "trace": 'File "/Users/Work/private.py"',
            "nested": {"api_key": "hidden", "kept": "ok"},
        },
    )

    payload = json.loads(journal.read_text(encoding="utf-8").strip())

    assert "backend_bearer_token" not in payload
    assert "debug_info" not in payload
    assert "api_key" not in payload["nested"]
    assert payload["nested"]["kept"] == "ok"
    assert "[path-redacted]" in payload["trace"]


def test_sanitize_for_journal_removes_prompt_like_fields():
    payload = sanitize_for_journal({"user_prompt": "raw", "answer": "safe"})

    assert payload == {"answer": "safe"}
