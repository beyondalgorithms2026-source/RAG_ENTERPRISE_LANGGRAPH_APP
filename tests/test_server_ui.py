from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rag_enterprise_langgraph.audit import AuditLog
from rag_enterprise_langgraph.config import Settings
from rag_enterprise_langgraph.eval_store import EvalStore, build_eval_run_summary
from rag_enterprise_langgraph.server import create_app

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def app_env(tmp_path):
    settings = Settings(
        audit_log_path=str(tmp_path / "audit-log.jsonl"),
        approvals_path=str(tmp_path / "approvals.jsonl"),
        eval_runs_dir=str(tmp_path / "eval-runs"),
        red_team_latest_path=str(tmp_path / "red-team-latest.json"),
        evidence_status_path=str(tmp_path / "evidence-status.json"),
        run_results_dir=str(tmp_path / "run-results"),
    )
    app = create_app(settings)
    return TestClient(app), settings


def test_ui_routes_return_200(app_env):
    client, _ = app_env
    for path in (
        "/app",
        "/app/documents",
        "/app/audit",
        "/app/approvals",
        "/app/quality",
        "/app/security",
        "/app/compare",
        "/app/evals",
        "/app/red-team",
        "/app/demo",
    ):
        response = client.get(path)
        assert response.status_code == 200, path
        assert "LangGraph/MCP RAG Orchestration" in response.text
    assert client.get("/", follow_redirects=False).status_code in (302, 307)
    assert client.get("/app/static/app.css").status_code == 200
    script = client.get("/app/static/app.js")
    assert script.status_code == 200
    assert "Free-tier data service is starting" in script.text
    assert 'fetchJSON("/evidence/status"' in script.text
    assert "canonicalDocuments" in script.text
    assert client.get("/healthz").json() == {"status": "ok"}


def test_evidence_status_serves_only_committed_artifact(app_env):
    client, settings = app_env
    path = settings.evidence_status_path
    assert client.get("/evidence/status").status_code == 503

    with open(path, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "schema_version": "2.0",
                "evidence_status": "candidate",
                "approval_statement": "Candidate, not approved baseline.",
            },
            handle,
        )

    response = client.get("/evidence/status")
    assert response.status_code == 200
    assert response.json()["evidence_status"] == "candidate"


def test_public_demo_is_read_only_and_hides_pending_answer(tmp_path):
    settings = Settings(
        public_demo=True,
        public_backend_url="https://backend.example.test",
        audit_log_path=str(tmp_path / "audit-log.jsonl"),
        approvals_path=str(tmp_path / "approvals.jsonl"),
        eval_runs_dir=str(tmp_path / "eval-runs"),
        red_team_latest_path=str(tmp_path / "red-team-latest.json"),
        run_results_dir=str(tmp_path / "run-results"),
    )
    client = TestClient(create_app(settings))

    from rag_enterprise_langgraph.approval import ApprovalStore

    record = ApprovalStore(settings.approvals_path).create(
        question="Sensitive HR question?",
        answer="Withheld answer text.",
        run_id="public-run",
        risk_reasons=["high_risk_category:hr"],
    )

    page = client.get("/app")
    assert page.status_code == 200
    assert 'data-public-demo="true"' in page.text
    assert 'content="https://backend.example.test"' in page.text
    assert page.text.count('class="starter-card"') == 4
    assert "Ask a governed policy question with evidence you can inspect." in page.text
    assert "Public-demo corpus" in page.text
    assert "Unsupported fact is not invented" in page.text
    assert "High-risk answer requires approval" in page.text
    assert "Restricted data remains unavailable" in page.text
    assert 'data-recovery="0"' in page.text
    assert "ask-require-approval" in page.text

    quality = client.get("/app/quality")
    assert quality.status_code == 200
    script = client.get("/app/static/app.js").text
    assert 'fetchJSON("/evidence/status"' in script
    assert "Candidate evidence only; no baseline promotion." in script

    pending = client.get("/approval/pending").json()["pending"]
    fetched = client.get(f"/approval/{record['approval_id']}").json()
    assert "full_answer" not in pending[0]
    assert "answer_preview" not in pending[0]
    assert "Withheld answer text" not in str(fetched)

    assert (
        client.post("/approval/request", json={"question": "Q", "answer": "A"}).status_code == 403
    )
    assert (
        client.post(
            f"/approval/{record['approval_id']}/approve", json={"reviewer": "visitor"}
        ).status_code
        == 403
    )
    assert client.post("/eval/run", json={"xlsx_path": "config/eval-set.xlsx"}).status_code == 403
    assert client.post("/red-team/run").status_code == 403
    assert client.post("/ask", json={"question": "Q"}).status_code == 403
    assert client.get("/demo-proof").status_code == 403


def test_approval_api_round_trip_writes_audit_events(app_env):
    client, settings = app_env

    created = client.post(
        "/approval/request",
        json={
            "question": "What is the severance policy?",
            "answer": "Answer text.",
            "run_id": "run-x",
            "risk_reasons": ["high_risk_category:hr"],
        },
    ).json()
    approval_id = created["approval_id"]
    assert created["status"] == "pending_approval"

    pending = client.get("/approval/pending").json()["pending"]
    assert [item["approval_id"] for item in pending] == [approval_id]

    missing_reviewer = client.post(f"/approval/{approval_id}/approve", json={"reviewer": ""})
    assert missing_reviewer.status_code == 409

    approved = client.post(
        f"/approval/{approval_id}/approve", json={"reviewer": "Alice", "comment": "ok"}
    )
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
        json={
            "question": "Approved Q?",
            "answer": "Released answer text.",
            "run_id": "run-approved",
        },
    ).json()
    rejected = client.post(
        "/approval/request",
        json={
            "question": "Rejected Q?",
            "answer": "Hidden answer text.",
            "run_id": "run-rejected",
        },
    ).json()
    client.post(
        f"/approval/{approved['approval_id']}/approve",
        json={"reviewer": "Alice", "comment": "good"},
    )
    client.post(
        f"/approval/{rejected['approval_id']}/reject",
        json={"reviewer": "Bob", "comment": "bad source"},
    )

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
        json={
            "question": "Approved Q?",
            "answer": "Released via audit.",
            "run_id": "run-aud-1",
            "grounding_status": "needs_review",
        },
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
    audit.append(
        event_type="run_started",
        run_id="run-1",
        actor="orchestrator",
        summary="start",
        payload={"question_preview": "Q?"},
    )
    audit.append(
        event_type="run_completed",
        run_id="run-1",
        actor="orchestrator",
        summary="done",
        payload={"grounding_status": "verified"},
    )

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
        "rows": [
            {
                "question": "Q?",
                "eval_status": "pass",
                "grounding_status": "verified",
                "latency_ms": 50,
            }
        ],
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
            "execution_timeline": [
                {"step": 1, "tool_name": "ask_grounded", "result_status": "grounded"}
            ],
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

    client.post(
        f"/approval/{created['approval_id']}/approve", json={"reviewer": "Alice", "comment": "ok"}
    )

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
    assert len(findings) == 20

    report = client.post("/red-team/run").json()
    assert report["total"] == 20
    assert report["failed"] == 0

    latest = client.get("/red-team/latest").json()["report"]
    assert latest["total"] == 20


def test_public_demo_serves_recorded_evidence_read_only(tmp_path):
    recorded_path = tmp_path / "before-after-recorded.json"
    settings = Settings(
        public_demo=True,
        audit_log_path=str(tmp_path / "audit-log.jsonl"),
        approvals_path=str(tmp_path / "approvals.jsonl"),
        eval_runs_dir=str(tmp_path / "eval-runs"),
        red_team_latest_path=str(tmp_path / "red-team-latest.json"),
        run_results_dir=str(tmp_path / "run-results"),
        recorded_comparisons_path=str(recorded_path),
    )
    client = TestClient(create_app(settings))

    assert client.get("/demo/before-after/recorded").status_code == 503

    recorded_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "comparisons": [
                    {
                        "question": "Q",
                        "first_pass_status": "verified",
                        "orchestrated_status": "verified",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    response = client.get("/demo/before-after/recorded")
    assert response.status_code == 200
    assert response.json()["comparisons"][0]["question"] == "Q"
    assert client.post("/demo/before-after", json={"question": "Q"}).status_code == 403

    compare = client.get("/app/compare").text
    assert "Demo only." in compare
    assert "follows your access" in compare
    assert 'id="demo-result"' in compare
    assert 'id="demo-form"' not in compare

    audit = client.get("/app/audit").text
    assert "Demo only." in audit
    assert 'id="audit-runs"' in audit

    script = client.get("/app/static/app.js").text
    assert 'fetchJSON("/demo/before-after/recorded"' in script
    assert "Chain intact" not in script
    assert "if (buttons.length) select(buttons[0]);" in script
    styles = client.get("/app/static/app.css").text
    assert ".audit-page .audit-run-list { display:flex;" in styles


def test_operator_mode_keeps_live_compare_without_demo_banner(app_env):
    client, _ = app_env
    compare = client.get("/app/compare").text
    assert 'id="demo-form"' in compare
    assert "Demo only." not in compare
    assert "Demo only." not in client.get("/app/audit").text


def test_committed_demo_evidence_is_consistent():
    audit = AuditLog(REPO_ROOT / "config" / "demo" / "audit-log.jsonl")
    chain = audit.verify_chain()
    assert chain["valid"] is True
    assert chain["checked"] > 0
    runs = audit.runs()
    assert len(runs) == 7

    recorded = json.loads(
        (REPO_ROOT / "config" / "demo" / "before-after-recorded.json").read_text(encoding="utf-8")
    )
    assert len(recorded["comparisons"]) == 2
    audited_run_ids = {run["run_id"] for run in runs}
    transport_failures = {"backend_timeout", "backend_auth_failed", "tool_error", "unavailable"}
    for comparison in recorded["comparisons"]:
        assert comparison["run_id"] in audited_run_ids
        assert comparison["first_pass_status"] not in transport_failures
        assert comparison["orchestrated_status"] not in transport_failures
