from __future__ import annotations

import asyncio

from rag_enterprise_langgraph.orchestrator import (
    EnterpriseRagOrchestrator,
    OrchestrationStep,
    _answer_from_evidence,
    _content_dict,
    _select_evidence_candidate,
    classify_answer_quality,
    classify_failure,
    classify_transport_failure,
    exact_phrase_bias,
    extract_anchor_terms,
)
from rag_enterprise_langgraph.evidence import evaluate_expected_answer, validate_evidence


def test_classify_failure_detects_backend_auth_and_timeout():
    assert classify_failure({"error": "HTTP Error 401: Unauthorized"}) == "backend_auth_failed"
    assert classify_failure({"message": "timed out"}) == "backend_timeout"
    assert classify_failure({"message": "timed out", "traceback": "HTTP/1.1 401 Unauthorized"}) == "backend_timeout"
    assert classify_failure({"is_error": True, "error": "tool failed"}) == "tool_error"


def test_normal_not_found_debug_timeout_is_not_transport_failure():
    payload = {
        "answer": "Not found in provided sources.",
        "citations": [],
        "debug_info": {
            "answer_generation_path": "not_found",
            "fallback_reason": "no timeout happened; text appears only in diagnostics",
            "retrieval_trace": {"score_diagnostics": [{"chunk_id": 15317, "keyword_score": 1.0}]},
        },
    }

    quality = classify_answer_quality(payload, question="What seminar did Sam Walton attend?", anchors=["Walton", "seminar"])

    assert classify_transport_failure(payload) is None
    assert quality.status == "candidate_evidence_present"
    assert quality.needs_recovery is True


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


def test_orchestration_step_summarizes_nested_backend_errors_without_traceback():
    orchestrator = EnterpriseRagOrchestrator(quiet_mcp=False)
    content = {
        "is_error": True,
        "error": '{"message": "timed out", "traceback": "Traceback with HTTP/1.1 401 Unauthorized"}',
    }

    step = orchestrator._step_from_content(
        index=1,
        tool_name="ask_grounded",
        purpose="initial_grounded_answer",
        content=content,
    )

    assert isinstance(step, OrchestrationStep)
    assert step.result_status == "backend_timeout"
    assert step.failure_reason == "timed out"


def test_orchestrator_unwraps_mcp_text_blocks_before_classification():
    orchestrator = EnterpriseRagOrchestrator(quiet_mcp=False)
    calls: list[str] = []

    async def fake_tool_call(name, arguments):  # noqa: ANN001, ARG001
        calls.append(name)
        if name == "ask_grounded":
            raw = [
                {
                    "type": "text",
                    "text": '{"answer": "Not found in provided sources.", "citations": [], "debug_info": {"answer_generation_path": "not_found", "fallback_reason": "not a transport timeout", "retrieval_trace": {"score_diagnostics": [{"chunk_id": 15317, "keyword_score": 1.0}]}}}',
                }
            ]
            return _content_dict(raw), {"tool_name": name, "tool_call_id": None, "content": raw}
        return {
            "results": [
                {
                        "source_id": 3,
                        "source_part_id": 655,
                        "file_name": "walmart.txt",
                        "snippet": "He goes up to Poughkeepsie, New York for an IBM seminar on computing technology.",
                    }
                ]
            }, {"tool_name": name, "tool_call_id": None, "content": {}}

    orchestrator._call_tool = fake_tool_call  # type: ignore[method-assign]

    result = asyncio.run(orchestrator.run("What seminar did Sam Walton enroll himself in in Poughkeepsie New York?"))

    assert result.grounding_status == "recovered"
    assert result.recovery_attempted is True
    assert result.evidence_count == 1
    assert calls == ["ask_grounded", "ask_grounded", "search_documents", "get_document_excerpt"]


def test_orchestrator_returns_not_grounded_for_answer_without_evidence():
    orchestrator = EnterpriseRagOrchestrator(quiet_mcp=False)

    async def fake_tool_call(name, arguments):  # noqa: ANN001, ARG001
        if name == "ask_grounded":
            return {"answer": "This appears to be true.", "citations": []}, {
                "tool_name": name,
                "tool_call_id": None,
                "content": {},
            }
        if name == "search_documents":
            return {"results": []}, {"tool_name": name, "tool_call_id": None, "content": {}}
        return {"matched": False, "excerpt": None, "result": None}, {"tool_name": name, "tool_call_id": None, "content": {}}

    orchestrator._call_tool = fake_tool_call  # type: ignore[method-assign]

    result = asyncio.run(orchestrator.run("Who first headed AWS technically?"))

    assert result.grounding_status == "not_grounded"
    assert result.error == "answer_without_citations_or_evidence"


def test_evidence_gate_rejects_irrelevant_walmart_revenue_snippet():
    evidence, verdict, rejected = _select_evidence_candidate(
        question="What seminar did Sam Walton enroll himself in in Poughkeepsie New York?",
        anchors=["Sam", "Walton", "seminar", "Poughkeepsie"],
        rules=EnterpriseRagOrchestrator(quiet_mcp=False).rules,
        expected_answer=None,
        results=[
            {
                "source_id": 3,
                "source_part_id": 655,
                "file_name": "walmart.txt",
                "snippet": "from a $25 million revenue base. Ben: Those two decades propelled them and somehow still hold the crown for the highest revenue company in the world.",
            }
        ],
    )

    assert evidence is None
    assert verdict is None
    assert rejected[0]["verdict"]["reason"] == "missing_required_terms"


def test_evidence_gate_accepts_ibm_poughkeepsie_seminar_snippet():
    evidence, verdict, rejected = _select_evidence_candidate(
        question="What seminar did Sam Walton enroll himself in in Poughkeepsie New York?",
        anchors=["Sam", "Walton", "seminar", "Poughkeepsie"],
        rules=EnterpriseRagOrchestrator(quiet_mcp=False).rules,
        expected_answer=None,
        results=[
            {
                "source_id": 3,
                "source_part_id": 655,
                "file_name": "walmart.txt",
                "snippet": "Sam Walton went up to Poughkeepsie, New York for an IBM seminar on how to use computing technology in business.",
            }
        ],
    )

    assert evidence is not None
    assert verdict is not None
    assert verdict.status == "supports"
    assert rejected == []


def test_orchestrator_does_not_recover_from_irrelevant_excerpt():
    orchestrator = EnterpriseRagOrchestrator(quiet_mcp=False)
    calls: list[str] = []

    async def fake_tool_call(name, arguments):  # noqa: ANN001, ARG001
        calls.append(name)
        if name == "ask_grounded":
            return {
                "answer": "Not found in provided sources.",
                "citations": [],
                "debug_info": {"retrieval_trace": {"score_diagnostics": [{"chunk_id": 15317, "keyword_score": 1.0}]}},
            }, {"tool_name": name, "tool_call_id": None, "content": {}}
        if name == "search_documents":
            return {
                "results": [
                    {
                        "source_id": 3,
                        "source_part_id": 655,
                        "file_name": "walmart.txt",
                        "snippet": "from a $25 million revenue base. Ben: Those two decades propelled them and somehow still hold the crown.",
                    }
                ]
            }, {"tool_name": name, "tool_call_id": None, "content": {}}
        return {
            "matched": True,
            "excerpt": "from a $25 million revenue base. Ben: Those two decades propelled them and somehow still hold the crown.",
            "result": {"source_id": 3, "source_part_id": 655, "file_name": "walmart.txt"},
        }, {"tool_name": name, "tool_call_id": None, "content": {}}

    orchestrator._call_tool = fake_tool_call  # type: ignore[method-assign]

    result = asyncio.run(orchestrator.run("What seminar did Sam Walton enroll himself in in Poughkeepsie New York?"))

    assert result.grounding_status == "needs_review"
    assert result.error is None
    assert result.failure_reason == "human_review_required"
    assert "Nearest relevant evidence requires human review" in result.answer
    assert result.evidence_count == 1
    assert result.rejected_evidence
    assert "get_document_excerpt" not in calls


def test_numeric_expected_answer_equivalence_for_eval_terms():
    rules = EnterpriseRagOrchestrator(quiet_mcp=False).rules

    rent_eval = evaluate_expected_answer(
        question="What Percentage of Rent to Sales did Sam Waltons first Ben Franklin cost",
        expected_answer="0.05",
        answer="The rent cost 5% of sales.",
        evidence=[],
        rules=rules,
    )
    revenue_eval = evaluate_expected_answer(
        question="How much top line revenue % did walmart see a year after their IPO 1972",
        expected_answer="0.77",
        answer="Walmart grew top-line revenue 77%.",
        evidence=[],
        rules=rules,
    )

    assert rent_eval["status"] == "pass"
    assert revenue_eval["status"] == "pass"


def test_cutoff_relevant_snippet_requests_neighbor_expansion():
    verdict = validate_evidence(
        question="What seminar did Sam Walton enroll himself in in Poughkeepsie New York?",
        anchors=["Walton", "seminar", "Poughkeepsie"],
        rules=EnterpriseRagOrchestrator(quiet_mcp=False).rules,
        evidence=[
            {
                "snippet": "Sam Walton went to Poughkeepsie for an IBM seminar on computing technolo",
            }
        ],
    )

    assert verdict.status in {"supports", "partial"}
    assert verdict.needs_neighbor_expansion is True


def test_recovered_answer_focuses_relevant_span_in_long_transcript_excerpt():
    rules = EnterpriseRagOrchestrator(quiet_mcp=False).rules
    answer = _answer_from_evidence(
        "What seminar did Sam Walton enroll himself in in Poughkeepsie New York?",
        [
            {
                "file_name": "walmart.txt",
                "snippet": (
                    "from a $25 million revenue base. Ben: Those two decades propelled them. "
                    "David: He goes up to Poughkeepsie, New York and enrolls himself as "
                    "Chairman/CEO of Walmart in a seminar at IBM on how to use computing "
                    "technology in business. There's a great quote from Abe Marks."
                ),
            }
        ],
        anchors=["seminar", "Walton", "enroll", "himself", "Poughkeepsie", "York"],
        rules=rules,
    )

    assert "seminar at IBM on how to use computing technology in business" in answer
    assert not answer.startswith("Recovered answer from walmart.txt: from a $25 million")
