from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse, Response


STATIC_DIR = Path(__file__).parent / "static"

NAV_ITEMS = (
    ("/app", "Dashboard"),
    ("/app/demo", "Before/After Demo"),
    ("/app/approvals", "Approvals"),
    ("/app/audit", "Audit Log"),
    ("/app/evals", "Evals"),
    ("/app/red-team", "Red Team"),
)


def _shell(*, title: str, page: str, active: str, lede: str, body: str) -> str:
    nav = "".join(
        f'<a href="{href}"{" class=\"active\"" if href == active else ""}>{label}</a>'
        for href, label in NAV_ITEMS
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{title} — RAG Orchestration</title>
<link rel="stylesheet" href="/app/static/app.css" />
</head>
<body data-page="{page}">
<header class="topbar">
  <div class="brand">LangGraph/MCP RAG Orchestration</div>
  <nav>{nav}</nav>
</header>
<main>
<h1>{title}</h1>
<p class="lede">{lede}</p>
{body}
</main>
<script src="/app/static/app.js"></script>
</body>
</html>"""


def build_ui_router() -> APIRouter:
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
        return _shell(
            title="Reasoning Workflow Dashboard",
            page="dashboard",
            active="/app",
            lede="LangGraph/MCP reasoning workflow with human approval and a full audit log — automation you can inspect.",
            body="""
<div class="tiles" id="dashboard-tiles"></div>
<div class="card">
  <h2>Ask the governed workflow</h2>
  <form id="ask-form">
    <label for="ask-question">Question</label>
    <input type="text" id="ask-question" placeholder="e.g. What does the employee handbook say about VPN access?" />
    <div class="row">
      <span class="checkbox"><input type="checkbox" id="ask-require-approval" /> <label for="ask-require-approval" style="margin:0;font-weight:500">Require approval for high-risk answers</label></span>
      <button type="submit">Run</button>
    </div>
  </form>
</div>
<div class="card">
  <h2>Result</h2>
  <div id="ask-result"><div class="empty">No run yet. Ask a question above — the answer, evidence, decision trail, and tool timeline will appear here.</div></div>
</div>
""",
        )

    @router.get("/app/approvals", response_class=HTMLResponse)
    async def approvals_page():
        return _shell(
            title="Approval Queue",
            page="approvals",
            active="/app/approvals",
            lede="High-risk answers are held at pending_approval until a named reviewer approves or rejects them. Decisions are persisted and written to the audit log.",
            body='<div id="approval-list"></div>',
        )

    @router.get("/app/audit", response_class=HTMLResponse)
    async def audit_page():
        return _shell(
            title="Audit Log",
            page="audit",
            active="/app/audit",
            lede="Every orchestrated run has a stable run_id and a sanitized, hash-chained event timeline. Click a run to inspect its events.",
            body="""
<div class="card"><div id="audit-runs"></div></div>
<div class="card"><div id="audit-detail"><div class="empty">Select a run above to see its event timeline and hash chain.</div></div></div>
""",
        )

    @router.get("/app/evals", response_class=HTMLResponse)
    async def evals_page():
        return _shell(
            title="Eval Dashboard",
            page="evals",
            active="/app/evals",
            lede="Accuracy, faithfulness/grounding, latency, and estimated cost per query from saved eval runs. Cost figures are configurable estimates, not billing data.",
            body="""
<div class="tiles" id="eval-tiles"></div>
<div class="card"><div id="eval-table"><div class="spinner">Loading…</div></div></div>
<div class="card"><div id="eval-runs"></div></div>
""",
        )

    @router.get("/app/red-team", response_class=HTMLResponse)
    async def red_team_page():
        return _shell(
            title="Red-Team Findings",
            page="red-team",
            active="/app/red-team",
            lede="Failure modes tested before deployment. Deterministic checks run the real validation code paths offline; backend-dependent scenarios are honestly labeled requires_backend.",
            body="""
<div class="row" style="margin-bottom:14px"><button id="red-team-run">Run red-team checks</button></div>
<div class="tiles" id="red-team-tiles"></div>
<div class="card"><div id="red-team-table"><div class="spinner">Loading…</div></div></div>
""",
        )

    @router.get("/app/demo", response_class=HTMLResponse)
    async def demo_page():
        return _shell(
            title="Before/After Automation Demo",
            page="demo",
            active="/app/demo",
            lede="Left: the actual raw first-pass answer from ask_grounded. Right: the governed orchestrated workflow with validation, recovery, approval gating, and audit events.",
            body="""
<div class="card">
  <form id="demo-form">
    <label for="demo-question">Question</label>
    <input type="text" id="demo-question" placeholder="Ask a question to compare the raw first pass with the governed workflow" />
    <div class="row">
      <span class="checkbox"><input type="checkbox" id="demo-require-approval" /> <label for="demo-require-approval" style="margin:0;font-weight:500">Require approval for high-risk answers</label></span>
      <button type="submit">Run before/after</button>
    </div>
  </form>
</div>
<div id="demo-result"><div class="empty">No comparison yet. Enter a question above to run both paths against the live backend.</div></div>
""",
        )

    return router
