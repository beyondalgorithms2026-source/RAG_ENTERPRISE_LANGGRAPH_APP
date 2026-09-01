from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from rag_enterprise_langgraph.agent import AgentRunResult
from rag_enterprise_langgraph.demo_proof import (
    DEFAULT_DEMO_QUESTIONS,
    build_demo_proof,
    redact_for_sharing,
    render_markdown_report,
    resolve_demo_questions,
    summarize_result,
)
from rag_enterprise_langgraph.orchestrator import OrchestratedRunResult, overall_status
from rag_enterprise_langgraph.server import create_app


class _FakeAgent:
    async def check_configuration(self):
        return {
            "app_name": "rag-enterprise-agent",
            "model_provider": "openai",
            "model_name": "gpt-4.1-mini",
            "backend_base_url": "http://127.0.0.1:8000",
            "backend_bearer_token_present": True,
            "backend_dev_login_email_present": True,
            "backend_dev_login_password_present": True,
            "mcp_tool_names": ["ask_grounded", "search_documents", "get_document_excerpt"],
        }

    async def run(self, question: str):
        return AgentRunResult(
            question=question,
            answer="Use VPN for remote access. [S1]",
            tool_outputs=[
                {
                    "tool_name": "ask_grounded",
                    "tool_call_id": "call-1",
                    "content": {
                        "answer": "Use VPN for remote access. [S1]",
                        "citations": [
                            {
                                "citation_id": "S1",
                                "source_id": 10,
                                "source_part_id": 11,
                                "chunk_id": 12,
                                "file_name": "handbook.pdf",
                                "source_type": "pdf",
                                "heading": "Remote Access",
                                "locator": "Page 3",
                                "snippet": "Employees must use VPN for remote access.",
                            }
                        ],
                        "used_chunks_count": 1,
                        "latency_ms": 25,
                        "mode": "hybrid",
                    },
                }
            ],
            message_count=3,
        )


class _FailingAgent(_FakeAgent):
    async def check_configuration(self):
        raise RuntimeError("MCP unavailable")

    async def run(self, question: str):
        return AgentRunResult(
            question=question,
            answer="",
            tool_outputs=[
                {
                    "tool_name": "agent",
                    "tool_call_id": None,
                    "content": {"is_error": True, "error": "MCP unavailable"},
                }
            ],
            message_count=0,
            error="MCP unavailable",
        )


class _FakeOrchestrator:
    async def check_configuration(self):
        return await _FakeAgent().check_configuration()

    async def run(  # noqa: ARG002
        self,
        question: str,
        *,
        max_recovery_steps: int = 3,
        max_attempts: int | None = None,
        validation_mode: str = "balanced",
        journal_path: str | None = None,
    ):
        return OrchestratedRunResult(
            question=question,
            answer="Recovered answer from excerpt evidence.",
            grounding_status="recovered",
            tools_used=["ask_grounded", "search_documents", "get_document_excerpt"],
            execution_timeline=[
                {
                    "step": 1,
                    "tool_name": "ask_grounded",
                    "purpose": "initial_grounded_answer",
                    "result_status": "not_found",
                    "recovery_reason": "not_found_with_candidate_evidence",
                },
                {
                    "step": 2,
                    "tool_name": "search_documents",
                    "purpose": "keyword_evidence_search",
                    "result_status": "candidate_evidence_found",
                },
                {
                    "step": 3,
                    "tool_name": "get_document_excerpt",
                    "purpose": "raw_excerpt_lookup",
                    "result_status": "evidence_found",
                },
            ],
            evidence=[
                {
                    "source_id": 3,
                    "source_part_id": 654,
                    "chunk_id": 15316,
                    "file_name": "walmart.txt",
                    "snippet": "They grew 77% their first year after IPO.",
                    "evidence_type": "excerpt",
                }
            ],
            evidence_count=1,
            recovery_attempted=True,
            recovery_successful=True,
            portfolio_safe=True,
            validation_summary={
                "final_status": "recovered",
                "evidence_support": "complete",
                "reason": "answer_shape_and_citations_supported",
                "review_recommended": False,
            },
            decision_trail=[
                {
                    "step": 1,
                    "label": "Question classified",
                    "summary": "open_ended_analysis",
                    "safe": True,
                },
                {
                    "step": 2,
                    "label": "Final status",
                    "summary": "recovered",
                    "safe": True,
                },
            ],
            review_guidance="Evidence appears sufficient for informational use. Human review is still recommended for high-impact decisions.",
            review_note="Generated from retrieved enterprise sources. Review cited evidence before making business, legal, financial, medical, HR, security, or compliance decisions.",
        )


def test_default_demo_questions_are_present():
    assert len(DEFAULT_DEMO_QUESTIONS) >= 3
    assert resolve_demo_questions() == list(DEFAULT_DEMO_QUESTIONS)


def test_demo_questions_are_overrideable_from_flags_and_file(tmp_path):
    questions_file = tmp_path / "questions.txt"
    questions_file.write_text("# comment\nFrom file?\n\nSecond from file?\n", encoding="utf-8")

    questions = resolve_demo_questions(
        positional_question="From positional?",
        questions=["From flag?"],
        questions_file=questions_file,
    )

    assert questions == ["From positional?", "From flag?", "From file?", "Second from file?"]


def test_redaction_removes_secret_values_but_keeps_presence_flags():
    redacted = redact_for_sharing(
        {
            "backend_bearer_token": "secret-token",
            "backend_bearer_token_present": True,
            "nested": {"api_key": "sk-test"},
        }
    )

    assert redacted["backend_bearer_token"] == "[redacted]"
    assert redacted["backend_bearer_token_present"] is True
    assert redacted["nested"]["api_key"] == "[redacted]"


def test_redaction_removes_raw_prompts_and_tracebacks_even_with_debug_enabled():
    redacted = redact_for_sharing(
        {
            "debug_info": {
                "answer_generation_path": "not_found",
                "system_prompt": "secret prompt",
                "user_prompt": "raw source prompt",
                "traceback": "Traceback File \"/Users/example/private.py\"",
                "retrieval_trace": {"score_diagnostics": [{"chunk_id": 1}]},
            },
            "raw": "raw backend payload",
        },
        include_debug=True,
    )

    assert redacted["debug_info"]["answer_generation_path"] == "not_found"
    assert redacted["debug_info"]["retrieval_trace"]["score_diagnostics"] == [{"chunk_id": 1}]
    assert "system_prompt" not in redacted["debug_info"]
    assert "user_prompt" not in redacted["debug_info"]
    assert "traceback" not in redacted["debug_info"]
    assert "raw" not in redacted


def test_tool_outputs_are_summarized_for_portfolio_proof():
    result = asyncio.run(_FakeAgent().run("Q"))
    summary = summarize_result(result)

    assert summary["answer_status"] == "grounded"
    assert summary["tools_used"] == ["ask_grounded"]
    assert summary["citation_count"] == 1
    assert summary["used_chunks_count"] == 1
    assert summary["mode"] == "hybrid"
    assert summary["latency_ms"] == 25


def test_demo_proof_success_and_markdown_report():
    proof = asyncio.run(build_demo_proof(orchestrator=_FakeOrchestrator(), questions=["Q"]))
    markdown = render_markdown_report(proof)

    assert proof["status"] == "ok"
    assert proof["required_tool_status"]["ask_grounded"] is True
    assert proof["runs"][0]["grounding_status"] == "recovered"
    assert proof["runs"][0]["evidence_count"] == 1
    assert "Enterprise LangGraph + MCP RAG Demo Proof" in markdown
    assert "Security / Governance Boundary" in markdown
    assert "Execution Timeline" in markdown
    assert "Decision Trail" in markdown
    assert "Review guidance" in markdown
    assert "not_found_with_candidate_evidence" in markdown
    assert "walmart.txt" in markdown


def test_demo_proof_handles_backend_or_mcp_errors():
    proof = asyncio.run(build_demo_proof(agent=_FailingAgent(), questions=["Q"]))

    assert proof["status"] == "error"
    assert proof["diagnostics_error"] == "MCP unavailable"
    assert proof["runs"][0]["answer_status"] == "error"
    assert proof["errors"] == ["MCP unavailable", "MCP unavailable"]


def test_demo_proof_endpoint_returns_expected_shape(monkeypatch):
    async def fake_build_demo_proof(  # noqa: ANN001, ARG001
        *,
        orchestrator,
        questions,
        include_debug=False,
        max_recovery_steps=3,
        max_attempts=None,
        validation_mode="balanced",
        show_decision_trail=True,
        show_review_note=True,
        rules_path=None,
        journal_path=None,
    ):
        return {
            "status": "ok",
            "overall_status": "ok",
            "diagnostics": {},
            "mcp_tools": ["ask_grounded"],
            "required_tool_status": {"ask_grounded": True},
            "questions": questions,
            "runs": [],
            "security_boundary_summary": [],
            "errors": [],
        }

    monkeypatch.setattr("rag_enterprise_langgraph.server.build_demo_proof", fake_build_demo_proof)
    client = TestClient(create_app())

    response = client.get("/demo-proof", params=[("question", "Custom question?")])

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["questions"] == ["Custom question?"]


def test_overall_status_marks_mixed_runs_partial():
    assert overall_status([{"grounding_status": "grounded"}, {"grounding_status": "backend_timeout"}]) == "partial"
    assert overall_status([{"grounding_status": "backend_auth_failed"}]) == "error"
    assert overall_status([{"grounding_status": "needs_review"}]) == "partial"
    assert overall_status([{"grounding_status": "recovered"}]) == "ok"
