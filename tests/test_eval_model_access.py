from pathlib import Path

from scripts.check_eval_model_access import _candidate_ids


def test_candidate_ids_are_allowlisted_deduplicated_and_sorted():
    payload = {
        "data": [
            {"id": "gpt-5-mini-2025-08-07"},
            {"id": "text-embedding-3-small"},
            {"id": "gpt-4.1-mini-2025-04-14"},
            {"id": "gpt-4.1-mini-2025-04-14"},
            {"name": "missing-id"},
        ]
    }

    assert _candidate_ids(payload) == [
        "gpt-4.1-mini-2025-04-14",
        "gpt-5-mini-2025-08-07",
    ]


def test_full_eval_uses_provider_compatible_openai_base_urls():
    workflow = Path(".github/workflows/full-eval-reusable.yml").read_text(encoding="utf-8")

    assert "LLM_BASE_URL: https://api.openai.com\n" in workflow
    assert "EMBEDDING_BASE_URL: https://api.openai.com/v1\n" in workflow
    assert "LLM_BASE_URL: https://api.openai.com/v1\n" not in workflow
