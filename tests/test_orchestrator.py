from __future__ import annotations

import asyncio

from rag_enterprise_langgraph.orchestrator import (
    EnterpriseRagOrchestrator,
    classify_failure,
    exact_phrase_bias,
    extract_anchor_terms,
)


def test_classify_failure_detects_backend_auth_and_timeout():
    assert classify_failure({"error": "HTTP Error 401: Unauthorized"}) == "backend_auth_failed"
    assert classify_failure({"message": "timed out"}) == "backend_timeout"
    assert classify_failure({"is_error": True, "error": "tool failed"}) == "tool_error"


def test_anchor_terms_and_phrase_bias_extract_distinctive_query_terms():
    question = "What Percentage of Rent to Sales did Sam Walton's first Ben Franklin cost?"

    anchors = extract_anchor_terms(question)

    assert "Percentage" in anchors
    assert "Rent" in anchors
    assert "Walton" in anchors
    assert exact_phrase_bias(question, anchors) == "Ben Franklin"


def test_orchestrator_returns_structured_tool_error_when_tool_call_raises():
    orchestrator = EnterpriseRagOrchestrator(quiet_mcp=False)

    async def fail_tool_call(name, arguments):  # noqa: ANN001, ARG001
        raise OSError("backend unavailable")

    orchestrator._call_tool = fail_tool_call  # type: ignore[method-assign]

    result = asyncio.run(orchestrator.run("What did the source say?"))

    assert result.grounding_status == "tool_error"
    assert result.portfolio_safe is False
    assert result.tools_used == ["ask_grounded"]
    assert result.execution_timeline[0]["result_status"] == "tool_error"
    assert "backend unavailable" in result.error
