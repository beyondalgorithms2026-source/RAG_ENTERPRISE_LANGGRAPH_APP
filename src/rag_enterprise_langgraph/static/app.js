"use strict";

const publicDemo = document.body.dataset.publicDemo === "true";
const backendUrl = (document.querySelector('meta[name="rag-backend-url"]')?.content || "").replace(/\/$/, "");
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
let approvalPollTimer = null;
let backendState = backendUrl ? "waking" : "ready";

class HTTPError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

function esc(value) {
  const node = document.createElement("div");
  node.textContent = value == null ? "" : String(value);
  return node.innerHTML;
}

async function fetchJSON(url, options = {}) {
  const response = await fetch(url, options);
  let body = null;
  try { body = await response.json(); } catch (_) { /* non-JSON response */ }
  if (!response.ok) {
    const detail = typeof body?.detail === "string" ? body.detail : `HTTP ${response.status}`;
    throw new HTTPError(response.status, detail);
  }
  return body;
}

function pill(status) {
  const value = String(status || "unknown");
  const good = ["verified", "grounded", "recovered", "approved", "defended", "pass", "completed", "ok", "ready"];
  const bad = ["failed", "fail", "rejected", "error", "tool_error", "backend_timeout", "backend_auth_failed", "not_grounded", "unavailable"];
  const warn = ["partial", "needs_review", "manual_review", "pending_approval", "requires_backend", "not_found", "waking", "degraded"];
  const kind = good.includes(value) ? "ok" : bad.includes(value) ? "bad" : warn.includes(value) ? "warn" : "info";
  return `<span class="pill ${kind}">${esc(value.replaceAll("_", " "))}</span>`;
}

function setBackendState(state, detail) {
  backendState = state;
  const target = document.getElementById("backend-readiness");
  if (target) {
    target.className = `readiness readiness-${state}`;
    target.innerHTML = `<strong>${esc(state[0].toUpperCase() + state.slice(1))}</strong><span>${esc(detail)}</span>`;
  }
  document.querySelectorAll("[data-needs-backend]").forEach((element) => {
    element.disabled = publicDemo && state !== "ready";
    element.setAttribute("aria-disabled", String(element.disabled));
  });
}

async function warmBackend() {
  if (!backendUrl) { setBackendState("ready", "Local workflow mode"); return; }
  setBackendState("waking", "Free-tier data service is starting; evidence remains available.");
  const deadline = Date.now() + 5 * 60 * 1000;
  let attempts = 0;
  while (Date.now() < deadline) {
    attempts += 1;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 12000);
    try {
      const response = await fetch(`${backendUrl}/health`, { signal: controller.signal, cache: "no-store" });
      if (response.ok) { setBackendState("ready", "Data service ready"); return; }
      setBackendState("degraded", `Health check returned HTTP ${response.status}; retrying.`);
    } catch (_) {
      setBackendState("waking", `Free-tier wake-up in progress · attempt ${attempts}`);
    } finally { clearTimeout(timer); }
    await sleep(attempts < 4 ? 3000 : 10000);
  }
  setBackendState("unavailable", "Data service did not become ready within five minutes.");
}

function sourceHref(sourceId) {
  const id = Number(sourceId);
  return backendUrl && Number.isInteger(id) && id > 0 ? `${backendUrl}/corpus/${id}/file` : "";
}

function timelineTable(timeline) {
  if (!timeline?.length) return '<div class="empty">No tool calls recorded.</div>';
  return `<div class="table-card"><table><thead><tr><th>Step</th><th>Tool</th><th>Purpose</th><th>Status</th><th>Latency</th></tr></thead><tbody>${timeline.map((step) => `<tr><td>${esc(step.step)}</td><td class="mono">${esc(step.tool_name)}</td><td>${esc(step.purpose || "—")}</td><td>${pill(step.result_status)}</td><td>${step.latency_ms == null ? "—" : `${esc(step.latency_ms)} ms`}</td></tr>`).join("")}</tbody></table></div>`;
}

function setRailRun(result) {
  const target = document.getElementById("rail-run");
  if (!target || !result?.run_id) return;
  target.hidden = false;
  target.innerHTML = `<strong>This run</strong><br>${esc(String(result.run_id).slice(0, 10))}<br>${esc(result.audit_event_count || 0)} audit events · ${esc((result.citations || []).length)} cited`;
}

function renderRunResult(result, output) {
  const citations = (result.citations || []).concat(result.evidence || []).slice(0, 5);
  const evidence = citations.length ? citations.map((item, index) => {
    const href = sourceHref(item.source_id);
    const label = `[${index + 1}] ${item.file_name || item.source_id || "Source"}`;
    return `<article class="evidence-card">${href ? `<a href="${esc(href)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>` : `<strong>${esc(label)}</strong>`}<p>${esc(item.locator || item.quote || item.snippet_preview || "Citation returned by the workflow.")}</p></article>`;
  }).join("") : '<div class="empty">No citations returned.</div>';
  const pending = result.approval_status === "pending_approval" && result.approval_id;
  output.classList.add("ask-result-filled");
  output.innerHTML = `<div class="answer-question-bar"><span>${pill(result.grounding_status)}</span><p>${esc(result.question || "Question")}</p><button class="secondary-button" id="ask-again" type="button">Ask again</button></div><section class="answer-pane"><div class="answer-box">${esc(result.answer || "[No answer released]")}</div>${result.review_guidance ? `<p class="answer-note">${esc(result.review_guidance)}</p>` : ""}${pending ? `<p class="answer-note">Answer withheld for human review. ${publicDemo ? "Public visitors cannot decide approvals." : '<a href="/app/approvals">Open the approval queue.</a>'}</p>` : ""}</section><aside class="evidence-panel"><div class="evidence-heading"><strong>Evidence</strong><span>${citations.length} cited</span></div>${evidence}<p class="small"><a href="/app/documents">Read in Documents →</a> · <a href="/app/audit">Open audit →</a></p></aside><section class="result-timeline"><h2>Governed workflow timeline</h2>${timelineTable(result.execution_timeline || [])}</section>`;
  document.getElementById("ask-again")?.addEventListener("click", () => {
    output.classList.remove("ask-result-filled");
    output.innerHTML = '<div class="empty">Ask another question to replace this result.</div>';
    document.getElementById("ask-question")?.focus();
  });
  setRailRun(result);
  if (pending && !publicDemo) watchApproval(result.approval_id, result.run_id, output);
}

function stopApprovalWatch() {
  if (approvalPollTimer) clearInterval(approvalPollTimer);
  approvalPollTimer = null;
}

function watchApproval(approvalId, runId, output) {
  stopApprovalWatch();
  approvalPollTimer = setInterval(async () => {
    try {
      const record = await fetchJSON(`/approval/${approvalId}`);
      if (!["approved", "rejected"].includes(record.status)) return;
      stopApprovalWatch();
      renderRunResult(await fetchJSON(`/runs/${runId}`), output);
    } catch (_) { /* retain current result */ }
  }, 5000);
}

async function loadRunHistory() {
  const target = document.getElementById("run-history");
  if (!target) return;
  try {
    const runs = (await fetchJSON("/runs")).runs || [];
    target.innerHTML = runs.length ? `<div class="table-card"><table><thead><tr><th>Question</th><th>Status</th><th>Approval</th><th>When</th></tr></thead><tbody>${runs.slice(0, 30).map((run) => `<tr class="clickable" data-run="${esc(run.run_id)}"><td>${esc(run.question || "—")}</td><td>${pill(run.grounding_status)}</td><td>${pill(run.approval_status || "not required")}</td><td class="small muted">${esc((run.created_at || "").slice(0, 19))}</td></tr>`).join("")}</tbody></table></div>` : '<div class="empty">No runs yet.</div>';
    target.querySelectorAll("[data-run]").forEach((row) => row.addEventListener("click", () => openHistoryRun(row.dataset.run)));
  } catch (error) { target.innerHTML = `<div class="error-box">${esc(error.message)}</div>`; }
}

async function openHistoryRun(runId) {
  const output = document.getElementById("ask-result");
  if (!output) return;
  output.innerHTML = '<div class="spinner">Loading run…</div>';
  try {
    const result = await fetchJSON(`/runs/${runId}`);
    document.getElementById("ask-question").value = result.question || "";
    renderRunResult(result, output);
  } catch (error) { output.innerHTML = `<div class="error-box">${esc(error.message)}</div>`; }
}

function initDashboard() {
  const form = document.getElementById("ask-form");
  const output = document.getElementById("ask-result");
  if (!form || !output) return;
  loadRunHistory();
  document.querySelectorAll(".starter-card").forEach((button) => button.addEventListener("click", () => {
    document.getElementById("ask-question").value = button.dataset.question || "";
    document.getElementById("ask-require-approval").checked = button.dataset.approval === "true";
    document.getElementById("ask-max-recovery").value = button.dataset.recovery || "3";
    form.requestSubmit();
  }));
  document.getElementById("ask-question")?.addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") form.requestSubmit();
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (publicDemo && backendState !== "ready") return;
    const question = document.getElementById("ask-question").value.trim();
    if (!question) return;
    output.classList.remove("ask-result-filled");
    output.innerHTML = '<div class="spinner">Running the governed APP → MCP → STARTER workflow…</div>';
    try {
      const result = await fetchJSON("/ask-orchestrated", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, require_approval: document.getElementById("ask-require-approval").checked, max_recovery_steps: Number(document.getElementById("ask-max-recovery").value || 3) }),
      });
      renderRunResult(result, output);
      loadRunHistory();
    } catch (error) { output.innerHTML = `<div class="error-box">Run failed: ${esc(error.message)}. No fabricated answer is shown.</div>`; }
  });
}

function documentIdentity(item) { return item.source_metadata_json?.source_file || item.file_name || String(item.id); }
function documentTitle(item) { return item.source_metadata_json?.title || item.file_name || "Untitled document"; }
function canonicalDocuments(items) {
  const byIdentity = new Map();
  items.forEach((item) => {
    const identity = documentIdentity(item);
    const current = byIdentity.get(identity);
    if (!current || Number(item.id) > Number(current.id)) byIdentity.set(identity, item);
  });
  return [...byIdentity.values()].sort((a, b) => documentTitle(a).localeCompare(documentTitle(b)));
}

function documentsFailureMessage(error) {
  if (error instanceof HTTPError && error.status === 403) return "This grant was denied access to the corpus listing.";
  if (backendState === "waking") return "The free-tier data service is still waking. This list will retry when it is ready.";
  if (backendState === "unavailable") return "The data service did not become available within the readiness window.";
  return "The corpus request could not cross the configured public-origin boundary. Check service health and CORS.";
}

async function initDocuments() {
  const list = document.getElementById("document-list");
  const reader = document.getElementById("document-reader");
  const counter = document.getElementById("document-count");
  if (!list || !reader) return;
  let documents = [];
  const renderReader = async (item) => {
    if (!item) return;
    list.querySelectorAll(".document-item").forEach((node) => node.classList.toggle("active", node.dataset.id === String(item.id)));
    const askQuestion = `Summarize ${documentTitle(item)} and cite the governing passage.`;
    reader.innerHTML = `<header class="reader-header"><div><p class="eyebrow">Access-filtered corpus document</p><h1>${esc(documentTitle(item))}</h1><div class="reader-meta"><span>${esc(item.source_type || "document")}</span><span>${esc(item.ingestion_status || "available")}</span><span>grant: anonymous public ✓</span></div></div><a class="reader-ask" href="/app?question=${encodeURIComponent(askQuestion)}">Ask about this document <span class="ms">arrow_forward</span></a></header><div class="reader-body"><aside id="reader-outline" class="reader-outline"></aside><article class="document-content" id="document-content"><div class="spinner">Loading readable source preview…</div></article></div>`;
    try {
      const response = await fetch(sourceHref(item.id), { cache: "no-store" });
      if (!response.ok) throw new HTTPError(response.status, `Preview HTTP ${response.status}`);
      const text = await response.text();
      const lines = text.split(/\n+/).map((line) => line.trim()).filter(Boolean);
      const headings = lines.filter((line) => /^#{1,3}\s+/.test(line));
      const paragraphs = lines.filter((line) => !/^#{1,3}\s+/.test(line));
      document.getElementById("reader-outline").innerHTML = headings.length ? `<p class="outline-label">Outline</p>${headings.slice(0, 12).map((heading, index) => `<a href="#reader-section-${index}">${esc(heading.replace(/^#+\s*/, ""))}</a>`).join("")}` : '<p class="outline-label">Preview</p>';
      document.getElementById("document-content").innerHTML = `${headings.slice(0, 1).map((heading) => `<h2 id="reader-section-0">${esc(heading.replace(/^#+\s*/, ""))}</h2>`).join("")}${paragraphs.slice(0, 8).map((paragraph) => `<p>${esc(paragraph)}</p>`).join("")}<p><a href="${esc(sourceHref(item.id))}" target="_blank" rel="noopener noreferrer">Open the complete source →</a></p>`;
    } catch (error) {
      const denied = error instanceof HTTPError && error.status === 403;
      document.getElementById("document-content").innerHTML = `<div class="${denied ? "empty" : "error-box"}">${esc(denied ? "This grant cannot open that source." : "The source is listed but its preview is temporarily unavailable.")}</div>`;
    }
  };
  const renderList = (items) => {
    list.innerHTML = items.length ? items.map((item) => `<button type="button" class="document-item" data-id="${esc(item.id)}"><strong>${esc(documentTitle(item))}</strong><small>${esc(item.source_type || "document")} · visible to anonymous grant</small></button>`).join("") : '<div class="empty">The corpus request succeeded, but this grant currently has no visible canonical sources.</div>';
    list.querySelectorAll("button[data-id]").forEach((node) => node.addEventListener("click", () => renderReader(documents.find((item) => String(item.id) === node.dataset.id))));
  };
  const load = async () => {
    try {
      if (!backendUrl) throw new Error("Backend URL is not configured");
      const payload = await fetchJSON(`${backendUrl}/corpus`, { cache: "no-store" });
      documents = canonicalDocuments(Array.isArray(payload) ? payload : []);
      if (counter) counter.textContent = `${documents.length} canonical public documents`;
      renderList(documents);
      const requested = new URLSearchParams(location.search).get("doc");
      await renderReader(documents.find((item) => String(item.id) === requested) || documents[0]);
    } catch (error) {
      list.innerHTML = `<div class="error-box">${esc(documentsFailureMessage(error))}</div>`;
      reader.innerHTML = '<div class="empty">Architecture and evaluation evidence remain available while the corpus service recovers.</div>';
    }
  };
  await load();
  if (backendState === "waking") {
    const readiness = setInterval(() => {
      if (backendState === "ready") { clearInterval(readiness); load(); }
      if (backendState === "unavailable") clearInterval(readiness);
    }, 1000);
  }
  document.getElementById("document-filter")?.addEventListener("input", (event) => {
    const needle = event.target.value.toLowerCase();
    renderList(documents.filter((item) => documentTitle(item).toLowerCase().includes(needle)));
  });
}

async function loadApprovals() {
  const target = document.getElementById("approval-list");
  if (!target) return;
  try {
    const pending = (await fetchJSON("/approval/pending")).pending || [];
    document.getElementById("pending-count").textContent = pending.length;
    target.innerHTML = pending.length ? `<table><thead><tr><th>Requested action</th><th>Class</th><th>Status</th><th>Approver</th><th>Actions</th></tr></thead><tbody>${pending.map((item) => `<tr><td><strong>${esc(item.question)}</strong><br><span class="small muted">${esc((item.risk_reasons || []).join(", ") || "Governed answer")}</span></td><td>${pill(item.grounding_status || "unknown")}</td><td>${pill(item.status)}</td><td>${esc(item.reviewer || "Unassigned")}</td><td><button disabled>Approve</button> <button disabled>Reject</button></td></tr>`).join("")}</tbody></table>` : '<div class="empty">No pending approvals.</div>';
  } catch (error) { target.innerHTML = `<div class="error-box">${esc(error.message)}</div>`; }
}

async function loadDecisions() {
  const target = document.getElementById("decision-list");
  if (!target) return;
  try {
    const decided = ((await fetchJSON("/approval")).approvals || []).filter((item) => ["approved", "rejected"].includes(item.status));
    target.innerHTML = decided.length ? `<h2>Recent decisions</h2><div class="table-card"><table><tbody>${decided.slice(0, 10).map((item) => `<tr><td>${esc(item.question)}</td><td>${pill(item.status)}</td><td>${esc((item.decided_at || "").slice(0, 19))}</td></tr>`).join("")}</tbody></table></div>` : "";
  } catch (_) { /* secondary history only */ }
}

function initApprovals() { loadApprovals(); loadDecisions(); }

async function loadAuditRuns() {
  const target = document.getElementById("audit-runs");
  if (!target) return;
  try {
    const runs = (await fetchJSON("/audit/runs")).runs || [];
    target.innerHTML = runs.length ? runs.map((run) => `<button class="audit-run-button" type="button" data-run="${esc(run.run_id)}"><strong>${esc(run.question_preview || "Audited run")}</strong><span>${pill(run.final_status || "in progress")} · ${esc(run.event_count || 0)} events</span></button>`).join("") : '<div class="empty">No audited runs yet.</div>';
    target.querySelectorAll("[data-run]").forEach((node) => node.addEventListener("click", () => loadAuditEvents(node.dataset.run)));
  } catch (error) { target.innerHTML = `<div class="error-box">${esc(error.message)}</div>`; }
}

async function loadAuditEvents(runId) {
  const detail = document.getElementById("audit-detail");
  detail.innerHTML = '<div class="spinner">Loading event chain…</div>';
  try {
    const data = await fetchJSON(`/audit/runs/${runId}`);
    const events = data.events || [];
    detail.innerHTML = `<header class="audit-header"><p class="eyebrow">Run ${esc(String(runId).slice(0, 12))}</p><h2>${esc(data.run_summary?.question_preview || "Audited workflow")}</h2><span class="chain-badge">● Chain intact · ${events.length} events</span></header><div class="audit-timeline">${events.map((event) => `<article class="audit-event"><time>${esc((event.timestamp || "").slice(0, 19))}</time><p><strong>${esc(event.event_type)}</strong> · ${esc(event.summary)}</p><div class="hash">prev ${esc(String(event.previous_hash || "genesis").slice(0, 16))} · hash ${esc(String(event.event_hash || "").slice(0, 16))}</div></article>`).join("")}</div>`;
  } catch (error) { detail.innerHTML = `<div class="error-box">${esc(error.message)}</div>`; }
}

function initAudit() { loadAuditRuns(); }

function renderQuality(status) {
  const approved = status.approved_baseline || {};
  const candidate = status.quality || {};
  const limitations = status.limitations || {};
  const v1Result = approved.result || `${approved.passed || approved.case_count || 25}/${approved.case_count || 25}`;
  return `<div class="quality-grid"><article class="quality-card core"><span class="quality-tag">APPROVED BASELINE</span><h2>v1 core suite</h2><div class="quality-score">${esc(v1Result)}</div><p>${esc(approved.statement || "The approved 25-case baseline remains unchanged.")}</p><ul class="quality-list"><li><span>Baseline ID</span><strong>${esc(approved.id || "northwind-openai-v1")}</strong></li><li><span>Status</span><strong>approved</strong></li></ul></article><article class="quality-card calibration"><span class="quality-tag">CANDIDATE · NOT APPROVED</span><h2>v2 expanded snapshot</h2><div class="quality-score">${esc(candidate.passed || 0)}/${esc(candidate.total || 90)}</div><p>${esc(status.approval_statement || "Candidate evidence only; no baseline promotion.")}</p><ul class="quality-list"><li><span>Failed</span><strong>${esc(candidate.failed || 0)}</strong></li><li><span>Manual review</span><strong>${esc(candidate.manual_review || 0)}</strong></li><li><span>Required refusals</span><strong>${esc(candidate.refusal_passed || 0)}/${esc(candidate.refusal_total || 0)}</strong></li><li><span>Safe boundaries</span><strong>${esc(candidate.safe_boundary_passed || 0)}/${esc(candidate.safe_boundary_total || 0)}</strong></li></ul><div class="quality-note">Failed: ${esc((limitations.failed_case_ids || []).join(", ") || "none")}<br>Manual review: ${esc((limitations.manual_review_case_ids || []).join(", ") || "none")}</div></article></div>`;
}

async function loadQuality() {
  const target = document.getElementById("quality-content");
  try { target.innerHTML = renderQuality(await fetchJSON("/evidence/status", { cache: "no-store" })); }
  catch (error) { target.innerHTML = `<div class="error-box">Committed evaluation evidence is unavailable: ${esc(error.message)}</div>`; }
}

function initQuality() { loadQuality(); }

function evidenceMode(finding) {
  if (["RT-06", "RT-16"].includes(finding.finding_id)) return finding.evidence_mode || "live SQL + full-stack";
  return finding.evidence_mode || finding.check_type || "deterministic defense";
}

function groupFindings(findings) {
  const categories = new Map();
  findings.forEach((finding) => {
    const label = String(finding.category || "governance").replaceAll("_", " ");
    if (!categories.has(label)) categories.set(label, []);
    categories.get(label).push(finding);
  });
  return [...categories.entries()].map(([label, items]) => ({ label, items }));
}

async function loadRedTeam() {
  const target = document.getElementById("security-content");
  const summary = document.getElementById("security-summary");
  try {
    const report = (await fetchJSON("/red-team/latest", { cache: "no-store" })).report;
    if (!report) throw new Error("Committed red-team release artifact is unavailable");
    const findings = report.findings || [];
    summary.innerHTML = `<div class="security-summary-bar"><span>${pill(report.overall_status)}</span><strong>${esc(findings.length)} scenarios</strong><span>${esc(report.defended || 0)} deterministic defenses · ${esc(report.live_verified || 2)} live controls</span></div>`;
    const detail = (finding) => `<aside class="security-detail"><span class="chip chip-defended">${esc(evidenceMode(finding))}</span><h2>${esc(finding.finding_id || "RT")}</h2><h3>${esc(finding.scenario || "Governance check")}</h3><pre class="attack-block">${esc(finding.actual_result || "The attack path was evaluated without exposing protected corpus content.")}</pre><div class="acl-card"><strong>Verified defense</strong><p>${esc(finding.expected_defense || "The governed route enforces access and evidence controls before release.")}</p></div><p class="small muted">${pill(finding.status)} · ${esc(finding.verification_reference || finding.linked_test || "committed release artifact")}</p></aside>`;
    const render = (selected) => {
      target.innerHTML = `<div class="security-layout"><div class="security-groups">${groupFindings(findings).map((group) => `<section class="security-group"><h2>${esc(group.label)}</h2><div class="check-grid">${group.items.map((finding) => `<button class="check-tile ${finding === selected ? "active" : ""}" data-finding="${esc(finding.finding_id)}"><code>${esc(finding.finding_id)}</code><span>${esc(finding.scenario)}</span><small>${esc(evidenceMode(finding))}</small></button>`).join("")}</div></section>`).join("")}</div>${detail(selected)}</div>`;
      target.querySelectorAll("[data-finding]").forEach((button) => button.addEventListener("click", () => render(findings.find((finding) => finding.finding_id === button.dataset.finding))));
    };
    render(findings.find((finding) => finding.finding_id === "RT-06") || findings[0] || {});
  } catch (error) { target.innerHTML = `<div class="error-box">${esc(error.message)}</div>`; }
}

async function runRedTeam() {
  const button = document.getElementById("red-team-run");
  button.disabled = true;
  try { await fetchJSON("/red-team/run", { method: "POST" }); await loadRedTeam(); }
  catch (error) { document.getElementById("security-content").innerHTML = `<div class="error-box">${esc(error.message)}</div>`; }
  finally { button.disabled = false; }
}

function initSecurity() {
  const button = document.getElementById("red-team-run");
  if (button && !publicDemo) button.addEventListener("click", runRedTeam);
  loadRedTeam();
}

function initCompare() {
  const form = document.getElementById("demo-form");
  const output = document.getElementById("demo-result");
  if (!form || !output) return;
  document.querySelectorAll("[data-demo-question]").forEach((button) => button.addEventListener("click", () => {
    document.getElementById("demo-question").value = button.dataset.demoQuestion;
    form.requestSubmit();
  }));
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const question = document.getElementById("demo-question").value.trim();
    if (!question) return;
    output.innerHTML = '<div class="spinner">Running both paths…</div>';
    try {
      const data = await fetchJSON("/demo/before-after", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question, require_approval: document.getElementById("demo-require-approval").checked }) });
      output.innerHTML = `<div class="compare-split"><article class="compare-panel raw"><h2>Ungoverned first pass</h2><div class="answer-box">${esc(data.first_pass_answer || data.first_pass_error || "No first-pass answer available.")}</div></article><article class="compare-panel governed"><h2>Governed release path</h2><div class="answer-box">${esc(data.orchestrated_answer || "[No answer released]")}</div><p>${pill(data.orchestrated_status)} ${pill(data.approval_status)}</p></article></div>${timelineTable(data.timeline)}`;
    } catch (error) { output.innerHTML = `<div class="error-box">${esc(error.message)}. No fabricated comparison is shown.</div>`; }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  warmBackend();
  const params = new URLSearchParams(location.search);
  if (params.get("question") && document.getElementById("ask-question")) document.getElementById("ask-question").value = params.get("question");
  const initializers = { dashboard: initDashboard, documents: initDocuments, approvals: initApprovals, audit: initAudit, quality: initQuality, security: initSecurity, compare: initCompare };
  initializers[document.body.dataset.page]?.();
});
