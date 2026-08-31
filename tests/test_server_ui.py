from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from rag_enterprise_langgraph.audit import AuditLog
from rag_enterprise_langgraph.config import Settings
from rag_enterprise_langgraph.eval_store import EvalStore, build_eval_run_summary
from rag_enterprise_langgraph.server import create_app


@pytest.fixture()
def app_env(tmp_path):
    settings = Settings(
        audit_log_path=str(tmp_path / "audit-log.jsonl"),
        approvals_path=str(tmp_path / "approvals.jsonl"),
        eval_runs_dir=str(tmp_path / "eval-runs"),
        red_team_latest_path=str(tmp_path / "red-team-latest.json"),
        run_results_dir=str(tmp_path / "run-results"),
    )
    app = create_app(settings)
    return TestClient(app), settings


def test_ui_routes_return_200(app_env):
    client, _ = app_env
    for path in ("/app", "/app/audit", "/app/approvals", "/app/evals", "/app/red-team", "/app/demo"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert "LangGraph/MCP RAG Orchestration" in response.text
    assert client.get("/", follow_redirects=False).status_code in (302, 307)
    assert client.get("/app/static/app.css").status_code == 200
    assert client.get("/app/static/app.js").status_code == 200
    assert client.get("/healthz").json() == {"status": "ok"}


def test_approval_api_round_trip_writes_audit_events(app_env):
    client, settings = app_env

    created = client.post(
        "/approval/request",
        json={"question": "What is the severance policy?", "answer": "Answer text.", "run_id": "run-x", "risk_reasons": ["high_risk_category:hr"]},
    ).json()
    approval_id = created["approval_id"]
    assert created["status"] == "pending_approval"

    pending = client.get("/approval/pending").json()["pending"]
    assert [item["approval_id"] for item in pending] == [approval_id]

    missing_reviewer = client.post(f"/approval/{approval_id}/approve", json={"reviewer": ""})
    assert missing_reviewer.status_code == 409

    approved = client.post(f"/approval/{approval_id}/approve", json={"reviewer": "Alice", "comment": "ok"})
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    fetched = client.get(f"/approval/{approval_id}").json()
    assert fetched["status"] == "approved"
    assert fetched["reviewer"] == "Alice"

    double = client.post(f"/approval/{approval_id}/reject", json={"reviewer": "Bob"})
    assert double.status_code == 409

    assert client.get("/approval/does-not-exist").status_code == 404

    events = AuditLog(settings.audit_log_path).events(run_id="run-x")
    event_types = [event["event_type"] for event in events]
    assert "approval_requested" in event_types
    assert "approval_approved" in event_types


def test_approval_list_endpoint_releases_answers_only_when_approved(app_env):
    client, _ = app_env
    approved = client.post(
        "/approval/request",
        json={"question": "Approved Q?", "answer": "Released answer text.", "run_id": "run-approved"},
    ).json()
    rejected = client.post(
        "/approval/request",
        json={"question": "Rejected Q?", "answer": "Hidden answer text.", "run_id": "run-rejected"},
    ).json()
    client.post(f"/approval/{approved['approval_id']}/approve", json={"reviewer": "Alice", "comment": "good"})
    client.post(f"/approval/{rejected['approval_id']}/reject", json={"reviewer": "Bob", "comment": "bad source"})

    all_records = client.get("/approval").json()["approvals"]
    assert len(all_records) == 2

    approved_only = client.get("/approval", params={"status": "approved"}).json()["approvals"]
    assert len(approved_only) == 1
    assert approved_only[0]["released_answer"] == "Released answer text."
    assert "full_answer" not in approved_only[0]

    rejected_only = client.get("/approval", params={"status": "rejected"}).json()["approvals"]
    assert len(rejected_only) == 1
    assert "released_answer" not in rejected_only[0]
    assert "Hidden answer text" not in str(rejected_only)


def test_audit_run_detail_includes_released_approval(app_env):
    client, _ = app_env
    approved = client.post(
        "/approval/request",
        json={"question": "Approved Q?", "answer": "Released via audit.", "run_id": "run-aud-1", "grounding_status": "needs_review"},
    ).json()
    rejected = client.post(
        "/approval/request",
        json={"question": "Rejected Q?", "answer": "Never released.", "run_id": "run-aud-2"},
    ).json()
    client.post(f"/approval/{approved['approval_id']}/approve", json={"reviewer": "Alice"})
    client.post(f"/approval/{rejected['approval_id']}/reject", json={"reviewer": "Bob"})

    detail = client.get("/audit/runs/run-aud-1").json()
    assert detail["run_summary"] is not None
    assert detail["approval"]["status"] == "approved"
    assert detail["approval"]["released_answer"] == "Released via audit."

    rejected_detail = client.get("/audit/runs/run-aud-2").json()
    assert rejected_detail["approval"]["status"] == "rejected"
    assert "released_answer" not in rejected_detail["approval"]
    assert "Never released" not in str(rejected_detail["approval"])


def test_audit_api_endpoints(app_env):
    client, settings = app_env
    audit = AuditLog(settings.audit_log_path)
    audit.append(event_type="run_started", run_id="run-1", actor="orchestrator", summary="start", payload={"question_preview": "Q?"})
    audit.append(event_type="run_completed", run_id="run-1", actor="orchestrator", summary="done", payload={"grounding_status": "verified"})

    runs = client.get("/audit/runs").json()["runs"]
    assert runs[0]["run_id"] == "run-1"

    detail = client.get("/audit/runs/run-1").json()
    assert detail["event_count"] == 2

    events = client.get("/audit/events").json()["events"]
    assert len(events) == 2

    export = client.get("/audit/export/run-1").json()
    assert export["chain_verification"]["valid"] is True
    assert client.get("/audit/runs/missing").status_code == 404
    assert client.get("/audit/export/missing").status_code == 404


def test_eval_api_endpoints(app_env):
    client, settings = app_env
    empty = client.get("/eval/latest").json()
    assert empty["eval_run"] is None
    assert "No saved eval runs" in empty["message"]

    report = {
        "xlsx_path": "sample.xlsx",
        "total": 1,
        "passed": 1,
        "failed": 0,
        "manual_review": 0,
        "status": "pass",
        "rows": [{"question": "Q?", "eval_status": "pass", "grounding_status": "verified", "latency_ms": 50}],
    }
    summary = build_eval_run_summary(report, settings=settings)
    EvalStore(settings.eval_runs_dir).save(summary)

    latest = client.get("/eval/latest").json()["eval_run"]
    assert latest["eval_run_id"] == summary["eval_run_id"]
    assert latest["accuracy"] == 1.0
    assert latest["cost_basis"] == "estimated"

    listing = client.get("/eval/runs").json()["eval_runs"]
    assert len(listing) == 1

    fetched = client.get(f"/eval/runs/{summary['eval_run_id']}").json()
    assert fetched["total"] == 1
    assert client.get("/eval/runs/missing").status_code == 404

    bad_path = client.post("/eval/run", json={"xlsx_path": "/etc/passwd"})
    assert bad_path.status_code == 400


def test_runs_api_applies_release_policy(app_env):
    client, settings = app_env
    from rag_enterprise_langgraph.run_store import RunStore

    empty = client.get("/runs").json()
    assert empty["runs"] == []
    assert client.get("/runs/missing").status_code == 404

    created = client.post(
        "/approval/request",
        json={"question": "Gated Q?", "answer": "The gated real answer.", "run_id": "run-gated"},
    ).json()
    RunStore(settings.run_results_dir).save(
        {
            "run_id": "run-gated",
            "question": "Gated Q?",
            "answer": "The gated real answer.",
            "grounding_status": "needs_review",
            "citations": [],
            "evidence": [{"file_name": "doc.md", "snippet": "evidence"}],
            "citation_count": 0,
            "evidence_count": 1,
            "decision_trail": [{"step": 1, "label": "Finalized", "summary": "needs_review"}],
            "execution_timeline": [{"step": 1, "tool_name": "ask_grounded", "result_status": "grounded"}],
            "approval_status": "pending_approval",
            "approval_id": created["approval_id"],
        }
    )

    pending_view = client.get("/runs/run-gated").json()
    assert pending_view["answer_released"] is False
    assert "withheld pending human approval" in pending_view["answer"]
    assert pending_view["execution_timeline"]

    listing = client.get("/runs").json()["runs"]
    assert listing[0]["run_id"] == "run-gated"
    assert listing[0]["approval_status"] == "pending_approval"

    client.post(f"/approval/{created['approval_id']}/approve", json={"reviewer": "Alice", "comment": "ok"})

    released_view = client.get("/runs/run-gated").json()
    assert released_view["answer_released"] is True
    assert released_view["answer"] == "The gated real answer."
    assert released_view["approved_by"] == "Alice"
    assert client.get("/runs").json()["runs"][0]["approval_status"] == "approved"


def test_red_team_api_endpoints(app_env):
    client, _ = app_env
    empty = client.get("/red-team/latest").json()
    assert empty["report"] is None

    findings = client.get("/red-team/findings").json()["findings"]
    assert len(findings) == 10

    report = client.post("/red-team/run").json()
    assert report["total"] == 10
    assert report["failed"] == 0

    latest = client.get("/red-team/latest").json()["report"]
    assert latest["total"] == 10
