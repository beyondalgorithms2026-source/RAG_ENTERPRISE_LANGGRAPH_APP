from __future__ import annotations

from rag_enterprise_langgraph.orchestrator import (
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
