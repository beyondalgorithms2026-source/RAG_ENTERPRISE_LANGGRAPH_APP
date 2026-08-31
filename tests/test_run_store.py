from __future__ import annotations

import asyncio

from rag_enterprise_langgraph.approval import ApprovalStore
from rag_enterprise_langgraph.orchestrator import EnterpriseRagOrchestrator
from rag_enterprise_langgraph.run_store import RunStore, public_view


SAMPLE_RESULT = {
    "run_id": "run-1",
    "question": "What is the policy?",
    "answer": "The real final answer.",
    "grounding_status": "verified",
    "citations": [{"file_name": "doc.md", "snippet": "policy text"}],
    "evidence": [],
    "citation_count": 1,
    "evidence_count": 0,
    "decision_trail": [{"step": 1, "label": "Finalized", "summary": "ok"}],
    "execution_timeline": [{"step": 1, "tool_name": "ask_grounded", "result_status": "grounded"}],
    "validation_summary": {"final_status": "verified"},
    "recovery_attempted": False,
    "recovery_successful": False,
    "approval_status": "approval_not_required",
    "approval_id": None,
    "risk_reasons": [],
    "audit_event_count": 5,
    "tool_outputs": [{"content": {"raw": "should not be stored"}}],
}


def test_run_store_save_get_list_drops_raw_payloads(tmp_path):
    store = RunStore(tmp_path / "run-results")
    store.save(dict(SAMPLE_RESULT))

    record = store.get("run-1")
    assert record["answer"] == "The real final answer."
    assert record["citation_count"] == 1
    assert "tool_outputs" not in record

    listing = store.list()
    assert len(listing) == 1
    assert listing[0]["run_id"] == "run-1"
    assert listing[0]["question"] == "What is the policy?"

    assert store.get("missing") is None
    assert store.get("../escape") is None


def test_run_store_keeps_real_answer_when_result_is_withheld(tmp_path):
    store = RunStore(tmp_path / "run-results")
    withheld = {**SAMPLE_RESULT, "answer": "Answer withheld pending human approval (approval_id=x).", "approval_status": "pending_approval", "approval_id": "ap-1"}
    store.save(withheld, real_answer="The real final answer.")
    assert store.get("run-1")["answer"] == "The real final answer."


def test_public_view_release_policy():
    record = {**SAMPLE_RESULT, "approval_status": "pending_approval", "approval_id": "ap-1"}

    pending = public_view(record, {"status": "pending_approval"})
    assert pending["answer_released"] is False
    assert "withheld pending human approval" in pending["answer"]
    assert "The real final answer" not in pending["answer"]

    rejected = public_view(record, {"status": "rejected", "reviewer": "Bob", "comment": "wrong source", "decided_at": "2026-07-13T10:00:00+00:00"})
    assert rejected["answer_released"] is False
    assert "rejected by Bob" in rejected["answer"]
    assert "The real final answer" not in rejected["answer"]

    approved = public_view(record, {"status": "approved", "reviewer": "Alice", "comment": "ok", "decided_at": "2026-07-13T10:00:00+00:00"})
    assert approved["answer_released"] is True
    assert approved["answer"] == "The real final answer."
    assert approved["approved_by"] == "Alice"
    assert approved["approval_comment"] == "ok"

    # Source-evidence proof reveals the answer content, so it is withheld until approved.
    gated = {**SAMPLE_RESULT, "approval_status": "pending_approval", "approval_id": "ap-1", "source_evidence": [{"file_name": "doc.md", "quote": "secret source text"}], "verbatim_answer": "The real final answer.", "synthesized_answer": "A synthesized answer."}
    pending_gated = public_view(gated, {"status": "pending_approval"})
    assert pending_gated["source_evidence"] == []
    assert pending_gated["verbatim_answer"] is None
    assert pending_gated["synthesized_answer"] is None
    assert "secret source text" not in str(pending_gated)

    approved_gated = public_view(gated, {"status": "approved", "reviewer": "Alice"})
    assert approved_gated["source_evidence"] and approved_gated["source_evidence"][0]["quote"] == "secret source text"

    ungated = public_view({**SAMPLE_RESULT})
    assert ungated["answer_released"] is True
    assert ungated["answer"] == "The real final answer."

    # Process stays inspectable in every state; content is withheld until released.
    assert pending["decision_trail"] and pending["execution_timeline"]
    assert pending["citations"] == [] and pending["evidence"] == []
    assert approved["citations"] == SAMPLE_RESULT["citations"]


def test_orchestrator_persists_full_result_with_real_answer(tmp_path):
    run_store = RunStore(tmp_path / "run-results")
    approval_store = ApprovalStore(tmp_path / "approvals.jsonl")
    orchestrator = EnterpriseRagOrchestrator(quiet_mcp=False, run_store=run_store, approval_store=approval_store)

    async def stub_call_tool(name, arguments):  # noqa: ANN001, ARG001
        content = {"answer": "Not found in provided sources.", "citations": []} if name == "ask_grounded" else {"results": []}
        return content, {"tool_name": name, "tool_call_id": None, "content": content}

    orchestrator._call_tool = stub_call_tool  # type: ignore[method-assign]

    result = asyncio.run(orchestrator.run("What is the employee termination policy?", require_approval=True))

    assert result.approval_status == "pending_approval"
    assert "withheld pending human approval" in result.answer

    stored = run_store.get(result.run_id)
    assert stored is not None
    assert "withheld pending human approval" not in stored["answer"]
    assert stored["approval_id"] == result.approval_id
    assert stored["execution_timeline"]
    assert stored["decision_trail"]

    # Once the reviewer approves, the public view releases the stored real answer.
    approval_store.approve(result.approval_id, reviewer="Alice", comment="ok")
    view = public_view(stored, approval_store.get(result.approval_id))
    assert view["answer_released"] is True
    assert view["answer"] == stored["answer"]
    assert view["approved_by"] == "Alice"
