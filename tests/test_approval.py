from __future__ import annotations

import asyncio

import pytest

from rag_enterprise_langgraph.approval import (
    APPROVED,
    PENDING_APPROVAL,
    REJECTED,
    ApprovalStore,
    approval_required,
    assess_risk,
    released_view,
)
from rag_enterprise_langgraph.audit import AuditLog
from rag_enterprise_langgraph.orchestrator import EnterpriseRagOrchestrator


def test_approval_request_creation(tmp_path):
    store = ApprovalStore(tmp_path / "approvals.jsonl")
    record = store.create(
        question="What is the termination policy?",
        answer="The policy says X.",
        run_id="run-123",
        evidence_status="supports",
        grounding_status="verified",
        risk_reasons=["high_risk_category:hr"],
    )
    assert record["status"] == PENDING_APPROVAL
    assert record["approval_id"]
    assert record["run_id"] == "run-123"
    assert record["question"] == "What is the termination policy?"
    assert record["answer_preview"].startswith("The policy says")
    assert record["evidence_status"] == "supports"
    assert record["grounding_status"] == "verified"
    assert record["risk_reasons"] == ["high_risk_category:hr"]
    assert record["requested_at"]
    assert record["reviewer"] is None
    assert store.pending()[0]["approval_id"] == record["approval_id"]


def test_approve_and_reject_are_explicit_and_persisted(tmp_path):
    path = tmp_path / "approvals.jsonl"
    store = ApprovalStore(path)
    first = store.create(question="Q1?", answer="A1", run_id="run-1")
    second = store.create(question="Q2?", answer="A2", run_id="run-2")

    approved = store.approve(first["approval_id"], reviewer="Alice", comment="Looks correct")
    rejected = store.reject(second["approval_id"], reviewer="Bob", comment="Wrong source")

    assert approved["status"] == APPROVED
    assert approved["reviewer"] == "Alice"
    assert approved["comment"] == "Looks correct"
    assert approved["decided_at"]
    assert rejected["status"] == REJECTED

    # Persistence across a fresh store instance (process restart).
    reloaded = ApprovalStore(path)
    assert reloaded.get(first["approval_id"])["status"] == APPROVED
    assert reloaded.get(second["approval_id"])["status"] == REJECTED
    assert reloaded.pending() == []


def test_double_decision_and_missing_reviewer_are_rejected(tmp_path):
    store = ApprovalStore(tmp_path / "approvals.jsonl")
    record = store.create(question="Q?", answer="A")

    with pytest.raises(ValueError):
        store.approve(record["approval_id"], reviewer="")

    store.approve(record["approval_id"], reviewer="Alice")
    with pytest.raises(ValueError):
        store.reject(record["approval_id"], reviewer="Bob")

    with pytest.raises(KeyError):
        store.approve("does-not-exist", reviewer="Alice")


def test_released_view_releases_answer_only_when_approved(tmp_path):
    store = ApprovalStore(tmp_path / "approvals.jsonl")
    approved = store.create(question="Q1?", answer="Secret answer one.", run_id="run-1")
    rejected = store.create(question="Q2?", answer="Secret answer two.", run_id="run-2")
    pending = store.create(question="Q3?", answer="Secret answer three.", run_id="run-3")
    store.approve(approved["approval_id"], reviewer="Alice")
    store.reject(rejected["approval_id"], reviewer="Bob")

    approved_view = released_view(store.get(approved["approval_id"]))
    assert approved_view["released_answer"] == "Secret answer one."
    assert "full_answer" not in approved_view

    rejected_view = released_view(store.get(rejected["approval_id"]))
    assert "released_answer" not in rejected_view
    assert "full_answer" not in rejected_view

    pending_view = released_view(store.get(pending["approval_id"]))
    assert "released_answer" not in pending_view
    assert "full_answer" not in pending_view


def test_by_run_id_finds_record(tmp_path):
    store = ApprovalStore(tmp_path / "approvals.jsonl")
    record = store.create(question="Q?", answer="A", run_id="run-77")
    assert store.by_run_id("run-77")["approval_id"] == record["approval_id"]
    assert store.by_run_id("missing") is None


def test_assess_risk_flags_high_risk_categories_and_statuses():
    assert any(r.startswith("high_risk_category:hr") for r in assess_risk("What is the employee termination policy?"))
    assert any(r.startswith("high_risk_category:legal") for r in assess_risk("Summarize the lawsuit exposure."))
    assert any(r.startswith("high_risk_category:medical") for r in assess_risk("What is the diagnosis protocol?"))
    assert assess_risk("What color is the sky in the story?") == []
    assert "grounding_status:needs_review" in assess_risk("What color is the sky?", {"grounding_status": "needs_review"})
    assert "grounding_status:partial" in assess_risk("What color is the sky?", {"grounding_status": "partial"})
    assert "review_recommended" in assess_risk(
        "What color is the sky?", {"grounding_status": "verified", "validation_summary": {"review_recommended": True}}
    )


def test_approval_required_modes():
    assert approval_required(mode="off", risk_reasons=["high_risk_category:hr"]) is False
    assert approval_required(mode="high-risk-only", risk_reasons=[]) is False
    assert approval_required(mode="high-risk-only", risk_reasons=["high_risk_category:hr"]) is True
    assert approval_required(mode="always", risk_reasons=[]) is True


def _stub_orchestrator() -> EnterpriseRagOrchestrator:
    orchestrator = EnterpriseRagOrchestrator(quiet_mcp=False)

    async def stub_call_tool(name, arguments):  # noqa: ANN001, ARG001
        if name == "ask_grounded":
            content = {"answer": "Not found in provided sources.", "citations": []}
        else:
            content = {"results": []}
        return content, {"tool_name": name, "tool_call_id": None, "content": content}

    orchestrator._call_tool = stub_call_tool  # type: ignore[method-assign]
    return orchestrator


def test_high_risk_run_stops_at_pending_approval_when_required(tmp_path):
    store = ApprovalStore(tmp_path / "approvals.jsonl")
    audit = AuditLog(tmp_path / "audit.jsonl")
    orchestrator = _stub_orchestrator()

    result = asyncio.run(
        orchestrator.run(
            "What is the employee termination policy?",
            require_approval=True,
            audit_log=audit,
            approval_store=store,
        )
    )

    assert result.approval_status == PENDING_APPROVAL
    assert result.approval_id
    assert any(reason.startswith("high_risk_category:hr") for reason in result.risk_reasons)
    assert "withheld pending human approval" in result.answer
    assert result.run_id

    pending = store.pending()
    assert len(pending) == 1
    assert pending[0]["run_id"] == result.run_id

    event_types = [event["event_type"] for event in audit.events(run_id=result.run_id)]
    assert "approval_requested" in event_types
    assert "run_completed" in event_types


def test_low_risk_run_does_not_require_approval(tmp_path):
    store = ApprovalStore(tmp_path / "approvals.jsonl")
    orchestrator = _stub_orchestrator()

    result = asyncio.run(
        orchestrator.run(
            "What color is the sky in the story?",
            require_approval=True,
            approval_store=store,
        )
    )

    assert result.approval_status == "approval_not_required"
    assert result.approval_id is None
    assert store.pending() == []


def test_always_mode_gates_even_low_risk_runs(tmp_path):
    store = ApprovalStore(tmp_path / "approvals.jsonl")
    orchestrator = _stub_orchestrator()

    result = asyncio.run(
        orchestrator.run(
            "What color is the sky in the story?",
            approval_mode="always",
            approval_store=store,
        )
    )

    assert result.approval_status == PENDING_APPROVAL
    assert result.risk_reasons == ["approval_mode_always"]
    assert len(store.pending()) == 1
