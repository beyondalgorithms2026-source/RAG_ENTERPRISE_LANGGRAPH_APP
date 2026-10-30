"""Deploy guards: /healthz, ALLOWED_ORIGINS CORS, daily/monthly spend caps (model layer faked, no network)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from rag_enterprise_langgraph import deploy
from rag_enterprise_langgraph.config import Settings
from rag_enterprise_langgraph.server import EnterpriseRagOrchestrator, create_app

SITE = "https://spanfold.com"
PROVIDER_WORDS = ("openai", "deepseek", "anthropic", "claude", "gpt", "gemini", "llama", "mistral")


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("SPEND_DB_PATH", str(tmp_path / "spend.sqlite"))
    for name in ("ALLOWED_ORIGINS", "APP_ENV", "DAILY_SPEND_CAP_USD", "MONTHLY_SPEND_CAP_USD", "EST_COST_PER_CALL_USD"):
        monkeypatch.delenv(name, raising=False)


def make_client(tmp_path, **kw):
    settings = Settings(
        audit_log_path=str(tmp_path / "audit-log.jsonl"),
        approvals_path=str(tmp_path / "approvals.jsonl"),
        eval_runs_dir=str(tmp_path / "eval-runs"),
        red_team_latest_path=str(tmp_path / "red-team-latest.json"),
        run_results_dir=str(tmp_path / "run-results"),
        **kw,
    )
    return TestClient(create_app(settings))


@pytest.fixture()
def fake_model(monkeypatch):
    async def run(self, question, **kwargs):
        return SimpleNamespace(to_dict=lambda: {"answer": "stub", "question": question})

    monkeypatch.setattr(EnterpriseRagOrchestrator, "run", run)


def test_healthz_is_exact(tmp_path):
    r = make_client(tmp_path).get("/healthz")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_cors_allows_site_and_blocks_others(tmp_path):
    c = make_client(tmp_path)
    assert c.get("/healthz", headers={"Origin": SITE}).headers.get("access-control-allow-origin") == SITE
    assert "access-control-allow-origin" not in c.get("/healthz", headers={"Origin": "https://evil.example"}).headers
    assert "access-control-allow-origin" not in c.get("/healthz", headers={"Origin": "http://localhost:8080"}).headers


def test_cors_localhost_only_when_app_env_local(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    r = make_client(tmp_path).get("/healthz", headers={"Origin": "http://localhost:8080"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:8080"


def test_cors_origins_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://one.example,https://two.example")
    c = make_client(tmp_path)
    assert c.get("/healthz", headers={"Origin": "https://two.example"}).headers.get("access-control-allow-origin") == "https://two.example"
    assert "access-control-allow-origin" not in c.get("/healthz", headers={"Origin": SITE}).headers


def test_cors_preflight_is_get_only(tmp_path):
    c = make_client(tmp_path)
    assert c.options("/healthz", headers={"Origin": SITE, "Access-Control-Request-Method": "POST"}).status_code == 400
    assert c.options("/healthz", headers={"Origin": SITE, "Access-Control-Request-Method": "GET"}).status_code == 200


def test_question_is_counted_then_blocked_at_the_cap(tmp_path, monkeypatch, fake_model):
    monkeypatch.setenv("EST_COST_PER_CALL_USD", "0.30")
    monkeypatch.setenv("DAILY_SPEND_CAP_USD", "0.50")
    c = make_client(tmp_path)
    body = {"question": "What is the leave policy?"}
    assert c.post("/ask-orchestrated", json=body).status_code == 200  # 0.30 counted
    assert c.post("/ask-orchestrated", json=body).status_code == 200  # 0.60 counted, now over the cap
    r = c.post("/ask-orchestrated", json=body, headers={"Origin": SITE})
    assert r.status_code == 429
    assert r.json()["detail"] == "This demo has reached its daily limit. Please try again tomorrow."
    assert r.headers.get("access-control-allow-origin") == SITE
    assert not any(w in r.text.lower() for w in PROVIDER_WORDS)
    assert c.get("/healthz").status_code == 200
    assert c.get("/evidence/status").status_code in (200, 503)  # read-only pages are not gated


def test_monthly_cap(tmp_path, monkeypatch, fake_model):
    monkeypatch.setenv("DAILY_SPEND_CAP_USD", "100")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "1")
    deploy.record_spend(1.5, "test")
    r = make_client(tmp_path).post("/ask-orchestrated", json={"question": "hi"})
    assert r.status_code == 429 and "monthly limit" in r.json()["detail"]


def test_broken_ledger_fails_open(tmp_path, monkeypatch):
    (tmp_path / "afile").write_text("x")
    monkeypatch.setenv("SPEND_DB_PATH", str(tmp_path / "afile" / "spend.sqlite"))
    assert deploy.over_cap() is None
    assert deploy.record_spend(0.1) == 0.1


def test_public_backend_url_default_and_env(monkeypatch):
    assert Settings().public_backend_url == "https://ragapi.spanfold.com"
    monkeypatch.setenv("RAG_AGENT_PUBLIC_BACKEND_URL", "https://other.example")
    assert Settings().public_backend_url == "https://other.example"
