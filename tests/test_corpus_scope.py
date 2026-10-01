from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from rag_enterprise_langgraph.config import Settings
from rag_enterprise_langgraph.orchestrator import (
    EnterpriseRagOrchestrator,
    run_before_after,
    scope_tool_arguments,
)
from rag_enterprise_langgraph.tool_guard import normalize_tool_arguments


def _recording_orchestrator(settings: Settings | None = None):
    orchestrator = EnterpriseRagOrchestrator(settings=settings, quiet_mcp=False)
    calls: list[tuple[str, dict]] = []

    async def fake_tool_call(name, arguments):
        calls.append((name, arguments))
        if name == "ask_grounded":
            return {
                "answer": "Not found in provided sources.",
                "citations": [],
                "debug_info": {
                    "retrieval_trace": {"score_diagnostics": [{"chunk_id": 1, "keyword_score": 1.0}]}
                },
            }, {}
        if name == "search_documents":
            return {
                "results": [
                    {
                        "source_id": 3,
                        "source_part_id": 7,
                        "file_name": "NL-FIN-EXPENSE-2026.md",
                        "snippet": "Unrelated onboarding text.",
                    }
                ]
            }, {}
        return {
            "matched": True,
            "excerpt": "Unrelated onboarding text.",
            "result": {"source_id": 3, "file_name": "NL-FIN-EXPENSE-2026.md"},
        }, {}

    orchestrator._call_tool = fake_tool_call  # type: ignore[method-assign]
    return orchestrator, calls


def _scope_of(name: str, arguments: dict):
    if name == "get_document_excerpt":
        return arguments.get("corpus")
    return (arguments.get("filters") or {}).get("corpus")


def test_every_tool_call_in_a_run_carries_the_requested_corpus():
    orchestrator, calls = _recording_orchestrator()

    asyncio.run(orchestrator.run("What is the London hotel cap?", corpus="western_northline"))

    names = {name for name, _ in calls}
    assert {"ask_grounded", "search_documents", "get_document_excerpt"} <= names
    assert all(_scope_of(name, args) == ["western_northline"] for name, args in calls)


def test_default_corpus_applies_when_request_names_none():
    settings = Settings(default_corpus="western_northline")
    orchestrator, calls = _recording_orchestrator(settings)

    asyncio.run(orchestrator.run("What is the London hotel cap?", max_recovery_steps=0))

    assert calls and all(_scope_of(n, a) == ["western_northline"] for n, a in calls)


def test_unscoped_run_leaves_tool_arguments_unchanged():
    orchestrator, calls = _recording_orchestrator(Settings(default_corpus=""))

    asyncio.run(orchestrator.run("What is the London hotel cap?", max_recovery_steps=0))

    assert calls == [("ask_grounded", {"question": "What is the London hotel cap?", "k_chunks": 6, "mode": "hybrid"})]


def test_scope_merges_with_existing_filters_and_overrides_caller_corpus():
    scoped = scope_tool_arguments(
        "search_documents",
        {"question": "q", "filters": {"source_id": 4, "corpus": ["other"]}},
        "western_northline",
    )
    assert scoped["filters"] == {"source_id": 4, "corpus": ["western_northline"]}
    assert scope_tool_arguments("ask_grounded", {"question": "q"}, None) == {"question": "q"}


def test_tool_guard_keeps_excerpt_corpus_argument():
    normalized = normalize_tool_arguments(
        "get_document_excerpt", {"question": "q", "source_id": 3, "corpus": ["western_northline"]}
    )
    assert normalized["corpus"] == ["western_northline"]


def test_before_after_first_pass_is_scoped_too():
    orchestrator, calls = _recording_orchestrator()

    asyncio.run(
        run_before_after(orchestrator, "What is the London hotel cap?", corpus="western_northline")
    )

    assert calls and all(_scope_of(n, a) == ["western_northline"] for n, a in calls)


@pytest.mark.parametrize("corpus", ["western northline", "x" * 65, "a;DROP"])
def test_api_rejects_malformed_corpus_names(corpus, monkeypatch):
    from rag_enterprise_langgraph import server

    client = TestClient(server.create_app())
    response = client.post("/ask-orchestrated", json={"question": "q", "corpus": corpus})
    assert response.status_code == 422
