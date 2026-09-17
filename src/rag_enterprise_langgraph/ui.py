from __future__ import annotations

from html import escape
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from rag_enterprise_langgraph.config import Settings

STATIC_DIR = Path(__file__).parent / "static"


def _icon(name: str) -> str:
    return f'<span class="ms" aria-hidden="true">{name}</span>'


ICONS = {
    "search_spark": _icon("search_spark"), "library_books": _icon("library_books"),
    "fact_check": _icon("fact_check"), "approval": _icon("approval"),
    "target": _icon("target"), "security": _icon("security"),
    "compare_arrows": _icon("compare_arrows"), "arrow": _icon("arrow_forward"),
    "eye": _icon("visibility"),
}

NAV_ITEMS = (
    ("/app", "Ask", "search_spark"),
    ("/app/documents", "Documents", "library_books"),
    ("/app/audit", "Audit", "fact_check"),
    ("/app/approvals", "Approvals", "approval"),
    ("/app/quality", "Quality", "target"),
    ("/app/security", "Security", "security"),
    ("/app/compare", "Compare", "compare_arrows"),
)


def _shell(*, title: str, page: str, active: str, body: str, settings: Settings) -> str:
    nav = "".join(
        '<a class="rail-item{active}" href="{href}" title="{label}">{icon}<span>{label}</span></a>'.format(
            href=href, active=" active" if href == active else "", icon=ICONS[icon], label=label
        )
        for href, label, icon in NAV_ITEMS
    )
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1" />
<meta name="rag-backend-url" content="{escape(settings.public_backend_url, quote=True)}" /><title>{title} — Governed RAG</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=IBM+Plex+Mono:wght@400;500;600&family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,400,0,0&display=swap" rel="stylesheet" />
<link rel="stylesheet" href="/app/static/app.css" /></head>
<body data-page="{page}" data-public-demo="{str(settings.public_demo).lower()}"><!-- LangGraph/MCP RAG Orchestration --><div class="app-layout">
<nav class="app-rail" aria-label="Application navigation"><div class="rail-brand"><div class="rail-brand-name">Governed RAG</div><div class="rail-brand-sub">Public demo</div></div>
<div class="rail-nav">{nav}</div><div class="rail-run" id="rail-run" hidden></div>
<div class="rail-footer"><div class="rail-role-pill"><span class="rail-dot"></span>Public visitor</div><p class="rail-disclaimer">Inspect-only. You can run questions. You cannot approve, edit, or export.</p><button class="rail-drawer-toggle" type="button" aria-expanded="false">How it's built <span>›</span></button></div></nav>
<main class="app-main">{body}</main></div><script src="/app/static/app.js"></script></body></html>"""


def build_ui_router(settings: Settings | None = None) -> APIRouter:
    runtime_settings = settings or Settings()
    router = APIRouter(tags=["ui"])

    @router.get("/", include_in_schema=False)
    async def root_redirect():
        return RedirectResponse(url="/app")

    @router.get("/app/static/app.css", include_in_schema=False)
    async def app_css():
        return Response((STATIC_DIR / "app.css").read_text(encoding="utf-8"), media_type="text/css")

    @router.get("/app/static/app.js", include_in_schema=False)
    async def app_js():
        return Response((STATIC_DIR / "app.js").read_text(encoding="utf-8"), media_type="application/javascript")

    @router.get("/app", response_class=HTMLResponse)
    async def dashboard_page():
        return _shell(settings=runtime_settings, title="Ask the policy corpus", page="dashboard", active="/app", body=f"""
<header class="page-header ask-header"><p class="eyebrow">Grounded answers · explicit refusal</p><div class="hero-grid"><div><h1>Ask a governed policy question with evidence you can inspect.</h1><p class="page-summary">Answers cite accessible sources. When evidence is insufficient or outside your grant, the workflow refuses rather than inventing an answer. SQL access control, citations, and an audit record remain visible.</p></div><aside class="corpus-card"><div class="card-title"><strong>Governance evidence</strong><span>public demo</span></div><dl><div><dt>Cited answers</dt><dd>required</dd></div><div><dt>Evidence gaps</dt><dd>refused</dd></div><div><dt>Source access</dt><dd>SQL ACL</dd></div><div><dt>Every run</dt><dd>audited</dd></div></dl><p>Synthetic portfolio corpus only. Restricted content is never shown to this visitor grant.</p></aside></div></header>
<section class="ask-workspace"><form id="ask-form" class="search-form"><input type="hidden" id="ask-max-recovery" value="3" /><label class="sr-only" for="ask-question">Question</label><div class="search-bar">{ICONS['search_spark']}<input type="text" id="ask-question" placeholder="Ask about leave, gifts, payments, or access controls…" autocomplete="off" /><kbd>⌘↵</kbd><button type="submit">Run {ICONS['arrow']}</button></div><div class="search-meta"><span>Governed workflow</span><span>Public visitor grant</span><span>SQL ACL enforced</span><span>Shared demo rate limit applies</span></div></form>
<div class="section-heading"><div><p class="eyebrow">Starter questions</p><h2>Try a governed scenario</h2></div><span class="small muted">Runs render here. No page change.</span></div><div class="starter-grid" aria-label="Starter questions">
<button type="button" class="starter-card" data-question="How many days of annual leave do full-time employees receive?" data-recovery="3"><span class="chip chip-grounded">Grounded</span><strong>How many annual leave days do full-time employees receive?</strong><small>Cited policy answer with source links.</small></button>
<button type="button" class="starter-card" data-question="What is the maximum value of a gift that may be accepted under company policy?" data-recovery="3"><span class="chip chip-grounded">Grounded</span><strong>What is the cap on gifts I may accept from a supplier?</strong><small>Threshold and procedure with evidence.</small></button>
<button type="button" class="starter-card" data-question="Is there ever an exception for a facilitation payment?" data-recovery="3"><span class="chip chip-grounded">Grounded</span><strong>Is there ever an exception for a facilitation payment?</strong><small>Explicit exception and its limits.</small></button>
<button type="button" class="starter-card" data-question="What was Northwind Logistics' revenue last year?" data-recovery="0"><span class="chip chip-withheld">Withheld</span><strong>What was revenue last year?</strong><small>Demonstrates an access-controlled refusal.</small></button></div>
<section id="ask-result" class="ask-result" aria-live="polite"><div class="result-empty"><div class="skeleton-lines"><i></i><i></i><i></i></div><div><strong>Your governed result will appear here</strong><p>Answer, citations that open the source, and the decision trail render in place.</p><div class="chip-legend"><span><i class="dot grounded"></i>Grounded</span><span><i class="dot refused"></i>Refused</span><span><i class="dot withheld"></i>Withheld</span><span><i class="dot defended"></i>Defended</span><span><i class="dot calibration"></i>Calibration</span><span><i class="dot error"></i>Error</span></div></div></div></section>
<section class="run-history-section"><div class="section-heading"><div><p class="eyebrow">Recent activity</p><h2>Run history</h2></div></div><div id="run-history"><div class="spinner">Loading runs…</div></div></section></section>""")

    @router.get("/app/documents", response_class=HTMLResponse)
    async def documents_page():
        return _shell(settings=runtime_settings, title="Documents", page="documents", active="/app/documents", body="""
<div class="documents-layout"><aside class="document-browser"><div class="browser-title"><strong>Corpus</strong><span>8 documents</span></div><label class="sr-only" for="document-filter">Filter documents</label><input id="document-filter" type="text" placeholder="Filter documents" /><div id="document-list" class="document-list"><div class="spinner">Loading corpus…</div></div></aside><section id="document-reader" class="document-reader"><div class="empty">Choose a document to inspect its public corpus preview.</div></section></div>""")

    @router.get("/app/approvals", response_class=HTMLResponse)
    async def approvals_page():
        return _shell(settings=runtime_settings, title="Approvals queue", page="approvals", active="/app/approvals", body=f"""
<header class="page-header"><p class="eyebrow">Human oversight</p><h1>Approvals queue</h1><p class="page-summary">High-risk answers remain withheld until a named reviewer decides.</p></header><section class="page-content"><div class="inspect-banner">{ICONS['eye']}<span><strong>Inspect-only grant.</strong> Approve and reject are disabled for the public-demo grant.</span></div><div class="table-card"><div id="approval-list"><div class="spinner">Loading approvals…</div></div></div><section class="approval-stats"><div><strong id="pending-count">—</strong><span>awaiting decision</span></div><div><strong>—</strong><span>median time to decision</span></div><div><strong>0</strong><span>unapproved writes</span></div></section><div id="decision-list" class="visually-secondary"></div></section>""")

    @router.get("/app/audit", response_class=HTMLResponse)
    async def audit_page():
        return _shell(settings=runtime_settings, title="Audit", page="audit", active="/app/audit", body="""
<header class="page-header"><p class="eyebrow">Tamper-evident record</p><h1>Audit trail</h1><p class="page-summary">Every orchestrated run has a sanitized, hash-chained event timeline.</p></header><section class="page-content audit-page"><div id="audit-runs" class="audit-run-list"><div class="spinner">Loading audited runs…</div></div><section id="audit-detail" class="audit-detail"><div class="empty">Select a run to inspect its event chain.</div></section></section>""")

    @router.get("/app/quality", response_class=HTMLResponse)
    async def quality_page():
        return _shell(settings=runtime_settings, title="Quality gates", page="quality", active="/app/quality", body="""
<header class="page-header"><p class="eyebrow">Evidence quality</p><h1>Quality evidence</h1><p class="page-summary">Approved v1 evidence is separate from provisional candidate work. No transient local run is presented as a release claim.</p></header><section class="page-content"><div id="quality-content"><div class="spinner">Loading approved evidence…</div></div><div id="eval-runs" class="visually-secondary"></div></section>""")

    @router.get("/app/security", response_class=HTMLResponse)
    async def security_page():
        run_button_state = "disabled" if runtime_settings.public_demo else ""
        return _shell(settings=runtime_settings, title="Security", page="security", active="/app/security", body=f"""
<header class="page-header security-header"><div><p class="eyebrow">Adversarial evaluation</p><h1>Red-team check map</h1><p class="page-summary">Known attack patterns are checked against the same governance controls that protect live runs.</p></div><button id="red-team-run" class="secondary-button" {run_button_state}>Run checks</button></header><section class="page-content"><div id="security-summary"></div><div id="security-content"><div class="spinner">Loading check map…</div></div></section>""")

    @router.get("/app/compare", response_class=HTMLResponse)
    async def compare_page():
        return _shell(settings=runtime_settings, title="Compare", page="compare", active="/app/compare", body=f"""
<header class="page-header"><p class="eyebrow">Side-by-side evidence</p><h1>Same question, same model, two paths</h1><p class="page-summary">Compare a raw first pass with a governed workflow that validates evidence, applies approval gates, and records an audit trail.</p></header><section class="page-content"><form id="demo-form" class="compare-form"><label class="sr-only" for="demo-question">Question to compare</label><input type="text" id="demo-question" placeholder="Ask a policy question" /><label class="approval-toggle"><input type="checkbox" id="demo-require-approval" /> Require approval</label><button type="submit">Compare {ICONS['arrow']}</button></form><div class="presets-inline"><button type="button" data-demo-question="What is the maximum value of a gift that may be accepted under company policy?">Gift cap</button><button type="button" data-demo-question="Who approves a €20,000 purchase?">€20k approver</button><button type="button" data-demo-question="Is there ever an exception for a facilitation payment?">Facilitation payment</button></div><div id="demo-result" class="compare-empty"><div class="empty">Run a comparison to inspect both paths.</div></div></section>""")

    @router.get("/app/evals", include_in_schema=False)
    async def evals_redirect():
        return RedirectResponse(url="/app/quality", status_code=301)

    @router.get("/app/red-team", include_in_schema=False)
    async def red_team_redirect():
        return RedirectResponse(url="/app/security", status_code=301)

    @router.get("/app/demo", include_in_schema=False)
    async def demo_redirect():
        return RedirectResponse(url="/app/compare", status_code=301)

    return router
