from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi.testclient import TestClient

from rag_enterprise_langgraph.approval import ApprovalStore, released_view
from rag_enterprise_langgraph.audit import AuditLog
from rag_enterprise_langgraph.config import Settings
from rag_enterprise_langgraph.corpus_tags import LEGACY_CORPUS, corpus_of
from rag_enterprise_langgraph.orchestrator import EnterpriseRagOrchestrator
from rag_enterprise_langgraph.run_store import RunStore
from rag_enterprise_langgraph.server import create_app


def _not_found_orchestrator(audit_log: AuditLog) -> EnterpriseRagOrchestrator:
    orchestrator = EnterpriseRagOrchestrator(quiet_mcp=False, audit_log=audit_log)

    async def fake_tool_call(name, arguments):
        return {"answer": "Not found in provided sources.", "citations": []}, {}

    orchestrator._call_tool = fake_tool_call  # type: ignore[method-assign]
    return orchestrator


def test_legacy_records_belong_to_the_original_demo_company():
    assert corpus_of(None) == LEGACY_CORPUS
    assert corpus_of("  ") == LEGACY_CORPUS
    assert corpus_of("western_northline") == "western_northline"


def test_runs_record_their_corpus_in_the_audit_chain(tmp_path):
    audit = AuditLog(tmp_path / "audit.jsonl")
    audit.append(
        event_type="run_started",
        run_id="legacy-run",
        actor="orchestrator",
        summary="Orchestrated run started",
        payload={"question_preview": "Recorded before corpus scoping"},
    )
    orchestrator = _not_found_orchestrator(audit)

    asyncio.run(
        orchestrator.run("London hotel cap?", max_recovery_steps=0, corpus="western_northline")
    )

    by_run = {run["run_id"]: run for run in audit.runs()}
    assert by_run["legacy-run"]["corpus"] == LEGACY_CORPUS
    scoped = [run for run in by_run.values() if run["run_id"] != "legacy-run"]
    assert [run["corpus"] for run in scoped] == ["western_northline"]
    assert audit.verify_chain()["valid"] is True


def test_approvals_and_saved_runs_carry_corpus(tmp_path):
    store = ApprovalStore(tmp_path / "approvals.jsonl")
    scoped = store.create(question="Q", answer="A", run_id="r1", corpus="western_northline")
    legacy = store.create(question="Q", answer="A", run_id="r2")
    assert released_view(scoped)["corpus"] == "western_northline"
    assert released_view(legacy)["corpus"] == LEGACY_CORPUS

    runs = RunStore(tmp_path / "runs")
    runs.save({"run_id": "r1", "question": "Q"}, corpus="western_northline")
    runs.save({"run_id": "r2", "question": "Q"})
    listed = {item["run_id"]: item["corpus"] for item in runs.list()}
    assert listed == {"r1": "western_northline", "r2": LEGACY_CORPUS}


def _client(tmp_path, *, default_corpus="western_northline", scorecard=None):
    path = tmp_path / "northline-scorecard.json"
    if scorecard is not None:
        path.write_text(json.dumps(scorecard), encoding="utf-8")
    settings = Settings(
        mcp_server_repo=tmp_path,
        public_demo=True,
        public_backend_url="https://backend.example.test",
        default_corpus=default_corpus,
        audit_log_path=str(tmp_path / "audit.jsonl"),
        approvals_path=str(tmp_path / "approvals.jsonl"),
        run_results_dir=str(tmp_path / "run-results"),
        northline_scorecard_path=str(path),
    )
    return TestClient(create_app(settings))


def test_northline_scorecard_endpoint(tmp_path):
    assert _client(tmp_path).get("/evidence/northline").status_code == 503
    card = {"title": "Northline", "by_split": {"refuse": {"passed": 5, "total": 5}}}
    assert _client(tmp_path, scorecard=card).get("/evidence/northline").json() == card


def test_committed_northline_scorecard_is_well_formed():
    card = json.loads(Path("docs/evaluation/northline-scorecard.json").read_text(encoding="utf-8"))
    assert card["corpus"] == "western_northline"
    assert set(card["by_split"]) == {"exact_fact", "open", "refuse", "adversarial"}
    assert card["links"]["scorecard"].startswith("https://github.com/")


def test_evidence_pages_offer_the_company_switch_and_banners(tmp_path):
    client = _client(tmp_path)
    for path in ("/app/audit", "/app/approvals", "/app/quality"):
        page = client.get(path).text
        assert 'name="company"' in page, path
        assert " checked /><strong>Northline Analytics</strong>" in page, path

    quality = client.get("/app/quality").text
    assert (
        'class="inspect-banner evidence-banner" data-corpus="northwind-public-demo" hidden'
        in quality
    )
    assert 'class="inspect-banner evidence-banner" data-corpus="western_northline">' in quality

    security = client.get("/app/security").text
    assert "Recorded evidence." in security
    assert "apply to both companies" in security
    assert 'name="company"' not in security

    script = client.get("/app/static/app.js").text
    assert ".filter(inSelectedCompany)" in script
    assert 'fetchJSON("/evidence/northline"' in script


def test_every_page_carries_the_brand_and_favicon(tmp_path):
    client = _client(tmp_path)
    for path in ("/app", "/app/documents", "/app/audit", "/app/quality", "/app/security"):
        page = client.get(path).text
        assert 'class="topbar-brand"' in page, path
        assert page.count('class="brand-mark"') == 2, path  # sidebar and mobile top bar
        assert '<link rel="icon" href="data:image/svg+xml,' in page, path
        assert "Cited answers or an honest refusal" in page, path


def test_northwind_misses_are_typed_from_the_committed_report(tmp_path):
    settings = Settings(mcp_server_repo=tmp_path, public_demo=True)
    status = TestClient(create_app(settings)).get("/evidence/status").json()
    outcomes = {item["case_id"]: item["outcome"] for item in status["miss_details"]}
    assert set(outcomes) == set(status["limitations"]["failed_case_ids"]) | set(
        status["limitations"]["manual_review_case_ids"]
    )
    assert outcomes["OM-041"] == "held for human review"
    assert "none invented" not in json.dumps(status)


def test_northline_card_reports_overall_and_typed_misses():
    card = json.loads(Path("docs/evaluation/northline-scorecard.json").read_text(encoding="utf-8"))
    assert (card["passed"], card["total"]) == (15, 20)
    assert (card["refusal_passed"], card["refusal_total"]) == (5, 5)
    assert {miss["qid"]: miss["outcome"] for miss in card["misses"]}["WQ-20"] == "partial answer"


def test_quality_and_security_scripts_use_shared_cards_and_short_proof(tmp_path):
    script = _client(tmp_path).get("/app/static/app.js").text
    assert 'const TRUST_STAGES = ["Demo run", "Candidate", "Approved baseline"]' in script
    assert script.count("${qualityCard({") == 3  # two Northwind cards, one Northline card
    assert "Proof: automated test" in script and "recorded CI run" in script
    assert "finding.verification_reference || finding.linked_test ||" not in script


def test_document_preview_renders_every_section_for_its_outline(tmp_path):
    script = _client(tmp_path).get("/app/static/app.js").text
    assert "function documentSections(text)" in script
    assert "function bindOutline(outline, select)" in script
    assert 'class="reader-section" id="reader-section-${index}"' in script
    assert "headings.slice(0, 12)" not in script and "paragraphs.slice(0, 8)" not in script
