from __future__ import annotations

from html import escape
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from rag_enterprise_langgraph.config import Settings

STATIC_DIR = Path(__file__).parent / "static"


def _icon(name: str) -> str:
    return f'<span class="ms" aria-hidden="true">{name}</span>'


ICONS = {
    "search_spark": _icon("search"),
    "library_books": _icon("library_books"),
    "fact_check": _icon("fact_check"),
    "approval": _icon("approval"),
    "target": _icon("target"),
    "security": _icon("security"),
    "compare_arrows": _icon("compare_arrows"),
    "arrow": _icon("arrow_forward"),
    "eye": _icon("visibility"),
}

# Brand mark: a document with a check inside a shield ("verified source"); inline, no assets.
BRAND_NAME = "Governed RAG"
BRAND_TAGLINE = "Cited answers or an honest refusal"
BRAND_MARK = (
    '<svg class="brand-mark" viewBox="0 0 24 24" aria-hidden="true" focusable="false">'
    '<path d="M12 2.5 4.5 5.4v5.8c0 4.6 3.1 8.8 7.5 10.3 4.4-1.5 7.5-5.7 7.5-10.3V5.4Z" fill="#0d9488"/>'
    '<path d="M9 7.2h4.4L15.2 9v7.6H9Z" fill="#fff"/>'
    '<path d="m10.5 12.4 1.3 1.3 2.3-2.5" fill="none" stroke="#0d9488" stroke-width="1.5"'
    ' stroke-linecap="round" stroke-linejoin="round"/></svg>'
)
BRAND_FAVICON = "data:image/svg+xml," + quote(
    BRAND_MARK.replace(' class="brand-mark"', ' xmlns="http://www.w3.org/2000/svg"')
)

NAV_ITEMS = (
    ("/app", "Ask", "search_spark"),
    ("/app/documents", "Documents", "library_books"),
    ("/app/audit", "Audit", "fact_check"),
    ("/app/approvals", "Approvals", "approval"),
    ("/app/quality", "Quality", "target"),
    ("/app/security", "Security", "security"),
    ("/app/compare", "Compare", "compare_arrows"),
)


def _demo_only_banner(detail: str) -> str:
    return (
        f'<div class="inspect-banner demo-only-banner">{ICONS["eye"]}<span><strong>Demo only.'
        f"</strong> {detail} In a live deployment, what you can see here follows your access."
        "</span></div>"
    )


# Two fictional companies share one governed system. Each request is scoped to one of them
# (STARTER `filters.corpus`), so an answer never mixes their policies. Counts are static
# and come from the corpus manifests; anonymous visitors cannot list non-public sources.
COMPANIES: dict[str, dict] = {
    "western_northline": {
        "label": "Northline Analytics",
        "region": "US / EU",
        "about": "UK-registered SaaS company with offices in Manchester, Austin and Amsterdam.",
        "facts": (
            ("Public sources", "13"),
            ("Restricted", "1"),
            ("Offices", "UK · US · NL"),
            ("Data", "synthetic"),
        ),
        "hidden_note": "+1 restricted Northline document (incident SOP) exists; the public grant cannot list or retrieve it.",
        "starters": (
            (
                "chip-grounded",
                "Grounded",
                "What is the nightly hotel room-rate cap for London?",
                "What is the London hotel cap?",
                "Cited policy answer",
                "false",
                "3",
            ),
            (
                "chip-refused",
                "Refusal",
                "What is Northline's India Provident Fund (PF/EPF) employer contribution rate?",
                "What is the India PF contribution rate?",
                "Unsupported fact is not invented",
                "false",
                "0",
            ),
            (
                "chip-withheld",
                "Withheld",
                "How much enhanced maternity pay does a UK employee receive, and for how many weeks?",
                "Enhanced maternity pay in the UK?",
                "High-risk answer requires approval",
                "true",
                "3",
            ),
            (
                "chip-refused",
                "Denied",
                "What should the team do first when a Sev1 production outage is declared?",
                "First steps in a Sev1 outage?",
                "Restricted data remains unavailable",
                "false",
                "3",
            ),
        ),
    },
    "northwind-public-demo": {
        "label": "Northwind Logistics",
        "region": "Original demo",
        "about": "European logistics company used by the original demo and its recorded evidence.",
        "facts": (
            ("Canonical sources", "28"),
            ("Anonymous-visible", "14"),
            ("Data", "synthetic"),
            ("Database", "pgvector"),
        ),
        "hidden_note": "+14 internal and restricted Northwind documents exist; the public grant cannot list or retrieve them.",
        "starters": (
            (
                "chip-grounded",
                "Grounded",
                "What is the maximum value of a gift that may be accepted under company policy?",
                "What is the cap on gifts I may accept?",
                "Cited policy answer",
                "false",
                "3",
            ),
            (
                "chip-refused",
                "Refusal",
                "What is the company's pension contribution rate?",
                "What is the pension contribution rate?",
                "Unsupported fact is not invented",
                "false",
                "0",
            ),
            (
                "chip-withheld",
                "Withheld",
                "What is the termination policy for employees on medical leave?",
                "Termination during medical leave?",
                "High-risk answer requires approval",
                "true",
                "3",
            ),
            (
                "chip-refused",
                "Denied",
                "What is the Band 6 salary range for 2026?",
                "What is the Band 6 salary range?",
                "Restricted data remains unavailable",
                "false",
                "3",
            ),
        ),
    },
}
SECURITY_EVIDENCE_NOTE = (
    "These checks test the governance layer, so they apply to both companies. The two live"
    " access-control checks (RT-06, RT-16) were recorded on Northwind's restricted salary"
    " document; Northline's equivalents are the WQ-12 access denial and the WQ-19"
    " poison-document test in its {scorecard}. Running checks is disabled in this public demo."
)
NORTHLINE_SCORECARD_URL = (
    "https://github.com/beyondalgorithms2026-source/RAG_ENTERPRISE_STARTER/blob/main/"
    "docs/evaluation/western/scorecard.md"
)


def _security_evidence_banner() -> str:
    link = (
        f'<a href="{escape(NORTHLINE_SCORECARD_URL, quote=True)}" target="_blank"'
        ' rel="noopener noreferrer">scorecard</a>'
    )
    return _recorded_evidence_banner(SECURITY_EVIDENCE_NOTE.format(scorecard=link))


def _default_company(settings: Settings) -> str:
    configured = (settings.default_corpus or "").strip()
    return configured if configured in COMPANIES else "northwind-public-demo"


def _company_switch(*, settings: Settings, label: str) -> str:
    selected = _default_company(settings)
    options = "".join(
        '<label class="company-option{active}"><input type="radio" name="company" value="{key}"'
        ' data-hidden-note="{note}"{checked} /><strong>{name}</strong><small>{region}</small></label>'.format(
            key=escape(key, quote=True),
            note=escape(company["hidden_note"], quote=True),
            checked=" checked" if key == selected else "",
            active=" active" if key == selected else "",
            name=escape(company["label"]),
            region=escape(company["region"]),
        )
        for key, company in COMPANIES.items()
    )
    return (
        f'<fieldset class="company-switch" data-default-company="{escape(selected, quote=True)}">'
        f"<legend>{escape(label)}</legend>{options}</fieldset>"
    )


def _corpus_cards(settings: Settings) -> str:
    selected = _default_company(settings)
    cards = []
    for key, company in COMPANIES.items():
        facts = "".join(
            f"<div><dt>{escape(name)}</dt><dd>{escape(value)}</dd></div>"
            for name, value in company["facts"]
        )
        cards.append(
            f'<aside class="corpus-card" data-corpus="{escape(key, quote=True)}"'
            f'{"" if key == selected else " hidden"}><div class="card-title"><strong>'
            f"{escape(company['label'])}</strong><span>{escape(company['region'])}</span></div>"
            f"<dl>{facts}</dl><p>{escape(company['about'])} Internal and restricted sources are"
            " excluded by the backend grant before retrieval.</p></aside>"
        )
    return "".join(cards)


def _starter_cards(settings: Settings) -> str:
    selected = _default_company(settings)
    return "".join(
        f'<button type="button" class="starter-card" data-corpus="{escape(key, quote=True)}"'
        f'{"" if key == selected else " hidden"} data-needs-backend data-question="{escape(question, quote=True)}"'
        f' data-approval="{approval}" data-recovery="{recovery}"><span class="chip {chip}">{escape(tag)}</span>'
        f"<strong>{escape(title)}</strong><small>{escape(hint)}</small></button>"
        for key, company in COMPANIES.items()
        for chip, tag, question, title, hint, approval, recovery in company["starters"]
    )


def _recorded_evidence_banner(
    detail: str, *, corpus: str | None = None, hidden: bool = False
) -> str:
    scope = f' data-corpus="{escape(corpus, quote=True)}"' if corpus else ""
    return (
        f'<div class="inspect-banner evidence-banner"{scope}{" hidden" if hidden else ""}>'
        f"{ICONS['eye']}<span><strong>Recorded evidence.</strong> {detail}</span></div>"
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
<link rel="icon" href="{BRAND_FAVICON}" /><link rel="stylesheet" href="/app/static/app.css" /></head>
<body data-page="{page}" data-public-demo="{str(settings.public_demo).lower()}"><!-- LangGraph/MCP RAG Orchestration --><div class="app-layout">
<nav class="app-rail" aria-label="Application navigation"><a class="rail-brand" href="/app"><div class="rail-brand-name">{BRAND_MARK}<span>{BRAND_NAME}</span></div><div class="rail-brand-sub">Public demo · {BRAND_TAGLINE}</div></a>
<div class="rail-nav">{nav}</div><div class="rail-run" id="rail-run" hidden></div>
<div class="rail-footer"><div class="rail-role-pill"><span class="rail-dot"></span>Public visitor</div><p class="rail-disclaimer">Inspect-only. You can run questions. You cannot approve, edit, or export.</p><button class="rail-drawer-toggle" type="button" aria-expanded="false">How it's built <span>›</span></button></div></nav>
<main class="app-main"><div class="app-topbar"><a class="topbar-brand" href="/app">{BRAND_MARK}<span>{BRAND_NAME}</span><em>Public demo</em></a><div id="backend-readiness" class="readiness readiness-waking" role="status" aria-live="polite"><strong>Waking</strong><span>Checking the free-tier data service…</span></div></div>{body}</main></div><script src="/app/static/app.js"></script></body></html>"""


def build_ui_router(settings: Settings | None = None) -> APIRouter:
    runtime_settings = settings or Settings()
    router = APIRouter(tags=["ui"])

    @router.get("/", include_in_schema=False)
    async def root_redirect():
        return RedirectResponse(url="/app")

    @router.get("/app/static/app.css", include_in_schema=False)
    async def app_css():
        return Response(
            (STATIC_DIR / "app.css").read_text(encoding="utf-8"), media_type="text/css"
        )

    @router.get("/app/static/app.js", include_in_schema=False)
    async def app_js():
        return Response(
            (STATIC_DIR / "app.js").read_text(encoding="utf-8"),
            media_type="application/javascript",
        )

    @router.get("/app", response_class=HTMLResponse)
    async def dashboard_page():
        return _shell(
            settings=runtime_settings,
            title="Ask the policy corpus",
            page="dashboard",
            active="/app",
            body=f"""
<header class="page-header ask-header"><p class="eyebrow">Synthetic corpora · answer or explicit refusal</p><div class="hero-grid"><div><h1>Ask a governed policy question with evidence you can inspect.</h1><p class="page-summary">This agent can only use passages available to the anonymous public grant. It checks evidence before releasing an answer and records every decision.</p><div class="inspect-banner company-banner">{ICONS["eye"]}<span><strong>Two fictional companies, one governed system.</strong> Pick <strong>Northline Analytics</strong> (US/EU policies) or <strong>Northwind Logistics</strong> (the original demo). Answers only use the company you pick.</span></div></div>{_corpus_cards(runtime_settings)}</div></header>
<section class="ask-workspace">{_company_switch(settings=runtime_settings, label="Company")}<form id="ask-form" class="search-form"><input type="hidden" id="ask-max-recovery" value="3" /><label class="sr-only" for="ask-question">Question</label><div class="search-bar">{ICONS["search_spark"]}<input type="text" id="ask-question" placeholder="Ask a question about the policy corpus" autocomplete="off" /><kbd>⌘↵</kbd><button type="submit" data-needs-backend>Run {ICONS["arrow"]}</button></div><div class="search-meta"><span>Path: APP → MCP → STARTER</span><span>Grant: anonymous public</span><span>SQL ACL enforced</span><span>Shared demo rate limit applies</span><label class="approval-toggle"><input type="checkbox" id="ask-require-approval" /> Require approval</label></div></form>
<div class="section-heading"><div><p class="eyebrow">Starter questions</p><h2>Try a governed scenario</h2></div><span class="small muted">Runs render here. No page change.</span></div><div class="starter-grid" aria-label="Starter questions">
{_starter_cards(runtime_settings)}</div><!-- 1 · Answerable -->
<section id="ask-result" class="ask-result" aria-live="polite"><div class="result-empty"><div class="skeleton-lines"><i></i><i></i><i></i></div><div><strong>Your governed result will appear here</strong><p>Answer, citations that open the source, and the decision trail render in place.</p><div class="chip-legend"><span><i class="dot grounded"></i>Grounded</span><span><i class="dot refused"></i>Refused</span><span><i class="dot withheld"></i>Withheld</span><span><i class="dot defended"></i>Defended</span><span><i class="dot calibration"></i>Calibration</span><span><i class="dot error"></i>Error</span></div></div></div></section>
<section class="run-history-section"><div class="section-heading"><div><p class="eyebrow">Recent activity</p><h2>Run history</h2></div></div><div id="run-history"><div class="spinner">Loading runs…</div></div></section></section>""",
        )

    @router.get("/app/documents", response_class=HTMLResponse)
    async def documents_page():
        return _shell(
            settings=runtime_settings,
            title="Documents",
            page="documents",
            active="/app/documents",
            body=f"""
<div class="documents-layout"><aside class="document-browser">{_company_switch(settings=runtime_settings, label="Company")}<div class="browser-title"><strong>Anonymous-visible documents</strong><span id="document-count">Loading…</span></div><p id="document-hidden-note" class="hidden-note"></p><label class="sr-only" for="document-filter">Filter documents</label><input id="document-filter" type="text" placeholder="Filter documents" /><div id="document-list" class="document-list"><div class="spinner">Loading corpus…</div></div></aside><section id="document-reader" class="document-reader"><div class="empty">Choose a document to inspect its public corpus preview.</div></section></div>""",
        )

    @router.get("/app/approvals", response_class=HTMLResponse)
    async def approvals_page():
        return _shell(
            settings=runtime_settings,
            title="Approvals queue",
            page="approvals",
            active="/app/approvals",
            body=f"""
<header class="page-header"><p class="eyebrow">Human oversight</p><h1>Approvals queue</h1><p class="page-summary">High-risk answers remain withheld until a named reviewer decides. The queue shows the selected company's requests.</p>{_company_switch(settings=runtime_settings, label="Company")}</header><section class="page-content"><div class="inspect-banner">{ICONS["eye"]}<span><strong>Inspect-only grant.</strong> Approve and reject are disabled for the public-demo grant.</span></div><div class="table-card"><div id="approval-list"><div class="spinner">Loading approvals…</div></div></div><section class="approval-stats"><div><strong id="pending-count">—</strong><span>awaiting decision</span></div><div><strong>—</strong><span>median time to decision</span></div><div><strong>0</strong><span>unapproved writes</span></div></section><div id="decision-list" class="visually-secondary"></div></section>""",
        )

    @router.get("/app/audit", response_class=HTMLResponse)
    async def audit_page():
        banner = (
            _demo_only_banner(
                "Recorded runs for both companies plus runs started by any visitor to this"
                " shared demo, all on synthetic data."
            )
            if runtime_settings.public_demo
            else ""
        )
        return _shell(
            settings=runtime_settings,
            title="Audit",
            page="audit",
            active="/app/audit",
            body=f"""
<header class="page-header"><p class="eyebrow">Tamper-evident record</p><h1>Audit trail</h1><p class="page-summary">Every orchestrated run has a sanitized, hash-chained event timeline. The list shows the selected company's runs.</p>{banner}{_company_switch(settings=runtime_settings, label="Company")}</header><section class="page-content audit-page"><div id="audit-runs" class="audit-run-list"><div class="spinner">Loading audited runs…</div></div><section id="audit-detail" class="audit-detail"><div class="empty">Select a run to inspect its event chain.</div></section></section>""",
        )

    @router.get("/app/quality", response_class=HTMLResponse)
    async def quality_page():
        return _shell(
            settings=runtime_settings,
            title="Quality gates",
            page="quality",
            active="/app/quality",
            body=f"""
<header class="page-header"><p class="eyebrow">Evidence quality</p><h1>Quality gates</h1><p class="page-summary">Recorded evaluation evidence for each company: what was measured, on which questions, and what passed. Pick a company to see its evidence; the full Northline scorecard is <a href="{NORTHLINE_SCORECARD_URL}" target="_blank" rel="noopener noreferrer">published in the data-layer repository</a>.</p>{_recorded_evidence_banner("These suites ran on the synthetic Northwind corpus (the original demo company). Baselines change only through a reviewed release.", corpus="northwind-public-demo", hidden=_default_company(runtime_settings) != "northwind-public-demo")}{_recorded_evidence_banner("A single run of the 20-question Northline demo set on the hosted stack. Demo evidence on synthetic data, not a benchmark.", corpus="western_northline", hidden=_default_company(runtime_settings) != "western_northline")}{_company_switch(settings=runtime_settings, label="Company")}</header><section class="page-content"><div id="quality-content"><div class="spinner">Loading quality results…</div></div><div id="eval-runs" class="visually-secondary"></div></section>""",
        )

    @router.get("/app/security", response_class=HTMLResponse)
    async def security_page():
        run_button_state = "disabled" if runtime_settings.public_demo else ""
        security_banner = _security_evidence_banner()
        return _shell(
            settings=runtime_settings,
            title="Security",
            page="security",
            active="/app/security",
            body=f"""
<header class="page-header security-header"><div><p class="eyebrow">Adversarial evaluation</p><h1>Red-team check map</h1><p class="page-summary">Known attack patterns are checked against the same governance controls that protect live runs.</p>{security_banner}</div><button id="red-team-run" class="secondary-button" {run_button_state}>Run checks</button></header><section class="page-content"><div id="security-summary"></div><div id="security-content"><div class="spinner">Loading check map…</div></div></section>""",
        )

    @router.get("/app/compare", response_class=HTMLResponse)
    async def compare_page():
        if runtime_settings.public_demo:
            banner = _demo_only_banner(
                "Recorded comparisons on the synthetic Northwind corpus (the original demo"
                " company). Running new comparisons is disabled in this public demo."
            )
            return _shell(
                settings=runtime_settings,
                title="Compare",
                page="compare",
                active="/app/compare",
                body=f"""
<header class="page-header"><p class="eyebrow">Recorded comparison evidence</p><h1>Same question, same model, two paths</h1><p class="page-summary">Recorded side-by-side runs: a raw first pass next to the governed workflow that validates evidence, applies approval gates, and records an audit trail.</p>{banner}</header><section class="page-content"><div id="demo-result" class="compare-empty"><div class="spinner">Loading recorded comparisons…</div></div></section>""",
            )
        return _shell(
            settings=runtime_settings,
            title="Compare",
            page="compare",
            active="/app/compare",
            body=f"""
<header class="page-header"><p class="eyebrow">Side-by-side evidence</p><h1>Same question, same model, two paths</h1><p class="page-summary">Compare a raw first pass with a governed workflow that validates evidence, applies approval gates, and records an audit trail.</p></header><section class="page-content"><form id="demo-form" class="compare-form"><label class="sr-only" for="demo-question">Question to compare</label><input type="text" id="demo-question" placeholder="Ask a policy question" /><label class="approval-toggle"><input type="checkbox" id="demo-require-approval" /> Require approval</label><button type="submit">Compare {ICONS["arrow"]}</button></form><div class="presets-inline"><button type="button" data-demo-question="What is the maximum value of a gift that may be accepted under company policy?">Gift cap</button><button type="button" data-demo-question="Who approves a €20,000 purchase?">€20k approver</button><button type="button" data-demo-question="Is there ever an exception for a facilitation payment?">Facilitation payment</button></div><div id="demo-result" class="compare-empty"><div class="empty">Run a comparison to inspect both paths.</div></div></section>""",
        )

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
