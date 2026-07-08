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
