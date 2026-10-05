from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from rag_enterprise_langgraph.config import Settings
from rag_enterprise_langgraph.server import create_app

STATIC = Path("src/rag_enterprise_langgraph/static")
REPOS = (
    "https://github.com/beyondalgorithms2026-source/RAG_ENTERPRISE_LANGGRAPH_APP",
    "https://github.com/beyondalgorithms2026-source/RAG_ENTERPRISE_STARTER",
    "https://github.com/beyondalgorithms2026-source/RAG_Langgraph_MCP_server",
)


def _client(tmp_path) -> TestClient:
    settings = Settings(
        mcp_server_repo=tmp_path,
        public_demo=True,
        public_backend_url="https://backend.example.test",
        audit_log_path=str(tmp_path / "audit.jsonl"),
        approvals_path=str(tmp_path / "approvals.jsonl"),
        run_results_dir=str(tmp_path / "run-results"),
    )
    return TestClient(create_app(settings))


def test_how_it_works_page_renders_inside_the_shell(tmp_path):
    client = _client(tmp_path)
    page = client.get("/app/how-it-works")
    assert page.status_code == 200
    text = page.text
    assert 'data-page="how-it-works"' in text
    assert "Every claim on this page links to its proof." in text
    assert text.count('class="exhibit"') == 6
    assert text.count('class="node"') == 6
    assert "How the pieces fit" in text and "What we deliberately don" in text
    assert '<link rel="stylesheet" href="/app/static/how-it-works.css" />' in text
    assert '<script src="/app/static/how-it-works.js" defer></script>' in text
    assert 'class="app-bar-how active" href="/app/how-it-works"' in text
    assert client.get("/app/static/how-it-works.css").status_code == 200
    assert client.get("/app/static/how-it-works.js").status_code == 200


def test_every_page_links_to_how_it_works(tmp_path):
    client = _client(tmp_path)
    for path in ("/app", "/app/documents", "/app/quality", "/app/security"):
        text = client.get(path).text
        assert 'class="app-bar-how" href="/app/how-it-works"' in text, path


def test_links_are_internal_or_point_at_the_three_repositories(tmp_path):
    text = (STATIC / "how-it-works.html").read_text(encoding="utf-8")
    hrefs = re.findall(r'href="([^"]+)"', text)
    assert hrefs
    for href in hrefs:
        if href.startswith(("#", "/app")):
            continue
        assert href.startswith(REPOS), href
    for path in {h.split("?")[0] for h in hrefs if h.startswith("/app")}:
        assert _client(tmp_path).get(path).status_code == 200, path


def test_page_styles_cannot_leak_into_other_pages():
    css = (STATIC / "how-it-works.css").read_text(encoding="utf-8")
    body = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    selectors = [
        selector.strip()
        for block in re.findall(r"([^{}]+)\{[^{}]*\}", body)
        for selector in block.split(",")
        if selector.strip() and not selector.strip().startswith("@media")
    ]
    assert selectors
    assert all(
        selector.startswith(".hiw") or selector.split("{")[-1].strip().startswith(".hiw")
        for selector in selectors
    ), [s for s in selectors if not s.startswith(".hiw")][:5]


def test_ask_page_invites_new_visitors_to_how_it_works(tmp_path):
    text = _client(tmp_path).get("/app").text
    assert '<a class="howit-card" href="/app/how-it-works"><strong>New here?</strong>' in text


def test_shell_has_no_fixed_canvas_that_unpins_the_sidebar():
    css = (STATIC / "app.css").read_text(encoding="utf-8")
    # A fixed-width canvas with overflow:hidden made the sidebar scroll away on wide screens.
    assert "width:1440px" not in css
    assert "@media (min-width:769px) { .app-rail { top:var(--bar-h);" in css
