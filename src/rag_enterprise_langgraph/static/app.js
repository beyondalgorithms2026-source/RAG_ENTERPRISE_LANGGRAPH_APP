"use strict";

function esc(value) {
  const div = document.createElement("div");
  div.textContent = value === null || value === undefined ? "" : String(value);
  return div.innerHTML;
}

async function fetchJSON(url, options) {
  const response = await fetch(url, options);
  let body = null;
  try {
    body = await response.json();
  } catch (err) {
    body = null;
  }
  if (!response.ok) {
    const detail = body && body.detail ? body.detail : `HTTP ${response.status}`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return body;
}

function pill(status) {
  const text = String(status || "unknown");
  const ok = ["verified", "grounded", "recovered", "approved", "defended", "pass", "completed", "ok", "candidate_evidence_found", "evidence_found"];
  const warn = ["partial", "needs_review", "manual_review", "pending_approval", "requires_backend", "not_found", "weak_answer", "candidate_evidence_present"];
  const bad = ["failed", "fail", "rejected", "error", "tool_error", "backend_timeout", "backend_auth_failed", "not_grounded", "unavailable"];
  let cls = "info";
  if (ok.includes(text)) cls = "ok";
  else if (warn.includes(text)) cls = "warn";
  else if (bad.includes(text)) cls = "bad";
  return `<span class="pill ${cls}">${esc(text)}</span>`;
}

function timelineTable(timeline) {
  if (!timeline || !timeline.length) return '<div class="empty">No tool calls recorded.</div>';
  const rows = timeline
    .map(
      (step) => `<tr>
        <td>${esc(step.step)}</td>
        <td class="mono">${esc(step.tool_name)}</td>
        <td>${esc(step.purpose || "-")}</td>
        <td>${pill(step.result_status)}</td>
        <td>${esc(step.recovery_reason || "-")}</td>
        <td>${step.latency_ms === null || step.latency_ms === undefined ? "-" : esc(step.latency_ms) + " ms"}</td>
      </tr>`
    )
    .join("");
  return `<table><thead><tr><th>#</th><th>Tool</th><th>Purpose</th><th>Status</th><th>Recovery reason</th><th>Latency</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function decisionTrail(trail) {
  if (!trail || !trail.length) return "";
  const items = trail.map((step) => `<li><strong>${esc(step.label)}:</strong> ${esc(step.summary)}</li>`).join("");
  return `<h2 style="margin-top:16px">Decision trail</h2><ul class="trail">${items}</ul>`;
}

/* ---------------- Dashboard (ask panel) ---------------- */

let approvalPollTimer = null;

function stopApprovalWatch() {
  if (approvalPollTimer) {
    clearInterval(approvalPollTimer);
    approvalPollTimer = null;
  }
}

function decisionLine(record) {
  const comment = record.comment ? ` — “${esc(record.comment)}”` : "";
  return `${pill(record.status)} by ${esc(record.reviewer || "-")} at ${esc((record.decided_at || "").slice(0, 19))}${comment}`;
}

function watchApproval(approvalId, runId, output) {
  const check = async () => {
    try {
      const record = await fetchJSON(`/approval/${approvalId}`);
      if (record.status !== "approved" && record.status !== "rejected") return;
      stopApprovalWatch();
      if (runId && output) {
        try {
          const view = await fetchJSON(`/runs/${runId}`);
          renderRunResult(view, output);
          loadRunHistory();
          return;
        } catch (err) {
          /* run store unavailable — fall back to inline release below */
        }
      }
      const container = document.getElementById("approval-release");
      if (!container) return;
      if (record.status === "approved") {
        container.innerHTML = `
          <h2 style="margin-top:16px">Released answer</h2>
          <div class="answer-box">${esc(record.full_answer || record.answer_preview || "")}</div>
          <p class="small muted">${decisionLine(record)}</p>`;
      } else {
        container.innerHTML = `<p class="small" style="margin-top:12px">${decisionLine(record)}. The answer was not released.</p>`;
      }
    } catch (err) {
      /* keep polling; transient errors are fine */
    }
  };
  stopApprovalWatch();
  approvalPollTimer = setInterval(check, 5000);
  const button = document.getElementById("check-approval");
  if (button) button.addEventListener("click", check);
}

function renderRunResult(result, output) {
  const citations = (result.citations || []).concat(result.evidence || []);
  const citationList = citations.length
    ? `<ul class="trail">${citations
        .slice(0, 5)
        .map((c) => `<li class="small">${esc(c.file_name || c.source_id || "source")}${c.locator ? " — " + esc(c.locator) : ""}</li>`)
        .join("")}</ul>`
    : '<div class="muted small">No citations returned.</div>';
  const releasedInfo =
    result.answer_released && result.approved_by
      ? `<p class="small muted">${pill("approved")} by ${esc(result.approved_by)} at ${esc((result.approved_at || "").slice(0, 19))}${result.approval_comment ? " — “" + esc(result.approval_comment) + "”" : ""} — released answer shown above.</p>`
      : "";
  const rejectedInfo =
    result.approval_status === "rejected" && result.decided_by
      ? `<p class="small muted">${pill("rejected")} by ${esc(result.decided_by)} at ${esc((result.decided_at || "").slice(0, 19))}${result.approval_comment ? " — “" + esc(result.approval_comment) + "”" : ""}</p>`
      : "";
  const pending = result.approval_status === "pending_approval" && result.approval_id;
  const answerLabel =
    result.synthesis_verified && result.synthesized_answer
      ? '<span class="pill ok" style="margin-left:8px">synthesized · verified against source</span>'
      : "";
  output.innerHTML = `
    <h2 style="margin:0 0 4px">Question</h2>
    <p style="margin:0 0 14px">${esc(result.question || "-")}</p>
    <div class="row" style="margin-bottom:10px">
      ${pill(result.grounding_status)} ${pill(result.approval_status)}
      ${result.recovery_attempted ? '<span class="pill info">recovery attempted</span>' : ""}
      <span class="muted small mono">run_id: ${esc(result.run_id || "-")}</span>
      <span class="muted small">${esc(result.audit_event_count || 0)} audit events</span>
    </div>
    <h2 style="margin:0 0 6px">Answer${answerLabel}</h2>
    <div class="answer-box">${esc(result.answer || "[no answer]")}</div>
    ${result.review_guidance ? `<p class="small muted" style="margin-top:8px"><strong>Review guidance:</strong> ${esc(result.review_guidance)}</p>` : ""}
    ${releasedInfo}
    ${rejectedInfo}
    ${pending ? `<p class="small muted">Approval pending: <a href="/app/approvals">review it in the approval queue</a> (id <span class="mono">${esc(result.approval_id)}</span>). This panel updates automatically once a reviewer decides. <button id="check-approval" class="secondary" style="padding:4px 10px;font-size:12px">Check approval status</button></p><div id="approval-release"></div>` : ""}
    ${sourceEvidenceSection(result)}
    <h2 style="margin-top:16px">Citations / evidence (${citations.length})</h2>
    ${citationList}
    ${decisionTrail(result.decision_trail)}
    <h2 style="margin-top:16px">Workflow timeline</h2>
    ${timelineTable(result.execution_timeline)}
  `;
  if (pending) watchApproval(result.approval_id, result.run_id, output);
}

function sourceEvidenceSection(result) {
  const spans = result.source_evidence || [];
  if (!spans.length) return "";
  const proofNote = result.synthesis_verified && result.synthesized_answer
    ? "The answer above was composed from these exact source passages and verified against them — nothing was added."
    : "The answer above quotes these exact source passages.";
  const items = spans
    .map((span) => {
      const loc = span.locator ? ` <span class="muted small">(${esc(span.locator)})</span>` : "";
      return `<div style="margin-bottom:10px">
        <div class="small mono" style="margin-bottom:2px">${esc(span.file_name || "source")}${loc}</div>
        <blockquote class="answer-box small" style="margin:0">${esc(span.quote)}</blockquote>
      </div>`;
    })
    .join("");
  return `
    <h2 style="margin-top:16px">Source evidence (verbatim)</h2>
    <p class="small muted" style="margin:0 0 10px">${proofNote}</p>
    ${items}
  `;
}

async function loadRunHistory() {
  const target = document.getElementById("run-history");
  if (!target) return;
  try {
    const data = await fetchJSON("/runs");
    const runs = data.runs || [];
    if (!runs.length) {
      target.innerHTML = '<div class="empty">No runs yet. Every orchestrated question will appear here.</div>';
      return;
    }
    const rows = runs
      .slice(0, 30)
      .map(
        (run) => `<tr class="clickable" data-run="${esc(run.run_id)}">
          <td>${esc(run.question || "-")}</td>
          <td>${pill(run.grounding_status || "unknown")}</td>
          <td>${pill(run.approval_status || "approval_not_required")}</td>
          <td class="muted small">${esc((run.created_at || "").slice(0, 19))}</td>
        </tr>`
      )
      .join("");
    target.innerHTML = `<table><thead><tr><th>Question</th><th>Status</th><th>Approval</th><th>When</th></tr></thead><tbody>${rows}</tbody></table>`;
    target.querySelectorAll("tr.clickable").forEach((row) => {
      row.addEventListener("click", () => openHistoryRun(row.dataset.run));
    });
  } catch (err) {
    target.innerHTML = `<div class="error-box">${esc(err.message)}</div>`;
  }
}

async function openHistoryRun(runId) {
  const output = document.getElementById("ask-result");
  if (!output) return;
  stopApprovalWatch();
  output.innerHTML = '<div class="spinner">Loading run…</div>';
  try {
    const view = await fetchJSON(`/runs/${runId}`);
    const questionInput = document.getElementById("ask-question");
    if (questionInput && view.question) questionInput.value = view.question;
    renderRunResult(view, output);
    const card = output.closest(".card");
    if (card) card.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    output.innerHTML = `<div class="error-box">${esc(err.message)}</div>`;
  }
}

function initDashboard() {
  const form = document.getElementById("ask-form");
  const output = document.getElementById("ask-result");
  loadDashboardCounts();
  loadRunHistory();
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const question = document.getElementById("ask-question").value.trim();
    const requireApproval = document.getElementById("ask-require-approval").checked;
    if (!question) return;
    stopApprovalWatch();
    output.innerHTML = '<div class="spinner">Running orchestrated workflow…</div>';
    try {
      const result = await fetchJSON("/ask-orchestrated", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, require_approval: requireApproval }),
      });
      renderRunResult(result, output);
      loadRunHistory();
      loadDashboardCounts();
    } catch (err) {
      output.innerHTML = `<div class="error-box">Run failed: ${esc(err.message)}. If the MCP backend is not running, this is expected — no fabricated answer is shown.</div>`;
    }
  });
}

async function loadDashboardCounts() {
  const target = document.getElementById("dashboard-tiles");
  if (!target) return;
  try {
    const [pending, runs] = await Promise.all([
      fetchJSON("/approval/pending"),
      fetchJSON("/audit/runs"),
    ]);
    const pendingCount = (pending.pending || []).length;
    const runCount = (runs.runs || []).length;
    target.innerHTML = `
      <div class="tile"><div class="label">Pending approvals</div><div class="value">${esc(pendingCount)}</div><div class="note"><a href="/app/approvals">Open queue</a></div></div>
      <div class="tile"><div class="label">Audited runs</div><div class="value">${esc(runCount)}</div><div class="note"><a href="/app/audit">View audit log</a></div></div>
    `;
  } catch (err) {
    target.innerHTML = "";
  }
}

/* ---------------- Approvals ---------------- */

function initApprovals() {
  loadApprovals();
  loadDecisions();
}

async function loadDecisions() {
  const target = document.getElementById("decision-list");
  if (!target) return;
  try {
    const data = await fetchJSON("/approval");
    const decided = (data.approvals || []).filter(
      (record) => record.status === "approved" || record.status === "rejected"
    );
    decided.sort((a, b) => String(b.decided_at || "").localeCompare(String(a.decided_at || "")));
    if (!decided.length) {
      target.innerHTML = '<div class="empty">No decisions yet. Approved answers will be released here.</div>';
      return;
    }
    target.innerHTML = decided
      .slice(0, 20)
      .map(
        (item) => `<div class="approval-item">
          <div class="q">${esc(item.question)}</div>
          <div class="row" style="margin:0 0 8px">
            ${pill(item.status)} ${pill(item.grounding_status || "unknown")}
            <span class="muted small mono">run_id: ${esc(item.run_id || "-")}</span>
            <span class="muted small">decided ${esc((item.decided_at || "").slice(0, 19))} by ${esc(item.reviewer || "-")}</span>
          </div>
          ${item.comment ? `<div class="small muted">Comment: ${esc(item.comment)}</div>` : ""}
          ${
            item.status === "approved"
              ? `<div class="answer-box small" style="margin-top:8px">${esc(item.released_answer || item.answer_preview || "")}</div>`
              : `<div class="small muted" style="margin-top:8px">Answer not released (rejected).</div>`
          }
        </div>`
      )
      .join("");
  } catch (err) {
    target.innerHTML = `<div class="error-box">${esc(err.message)}</div>`;
  }
}

async function loadApprovals() {
  const target = document.getElementById("approval-list");
  target.innerHTML = '<div class="spinner">Loading…</div>';
  try {
    const data = await fetchJSON("/approval/pending");
    const pending = data.pending || [];
    if (!pending.length) {
      target.innerHTML = '<div class="empty">No pending approvals. Run a high-risk question with "Require approval" enabled to create one.</div>';
      return;
    }
    target.innerHTML = pending
      .map(
        (item) => `<div class="approval-item" data-id="${esc(item.approval_id)}">
          <div class="q">${esc(item.question)}</div>
          <div class="row" style="margin:0 0 8px">
            ${pill(item.status)} ${pill(item.grounding_status || "unknown")}
            <span class="muted small mono">run_id: ${esc(item.run_id || "-")}</span>
            <span class="muted small">requested ${esc((item.requested_at || "").slice(0, 19))}</span>
          </div>
          <div class="small muted">Risk reasons: ${esc((item.risk_reasons || []).join(", ") || "-")} · Evidence: ${esc(item.evidence_status || "unknown")}</div>
          <div class="answer-box small" style="margin-top:8px">${esc(item.full_answer || item.answer_preview || "")}</div>
          <div class="row">
            <input type="text" class="reviewer" placeholder="Reviewer name" style="max-width:200px" />
            <input type="text" class="comment" placeholder="Comment (optional)" style="max-width:320px" />
            <button class="approve" data-action="approve">Approve</button>
            <button class="danger" data-action="reject">Reject</button>
          </div>
          <div class="decision-msg small" style="margin-top:6px"></div>
        </div>`
      )
      .join("");
    target.querySelectorAll("button[data-action]").forEach((button) => {
      button.addEventListener("click", () => decideApproval(button));
    });
  } catch (err) {
    target.innerHTML = `<div class="error-box">${esc(err.message)}</div>`;
  }
}

async function decideApproval(button) {
  const item = button.closest(".approval-item");
  const approvalId = item.dataset.id;
  const reviewer = item.querySelector(".reviewer").value.trim();
  const comment = item.querySelector(".comment").value.trim();
  const message = item.querySelector(".decision-msg");
  if (!reviewer) {
    message.innerHTML = '<span class="pill bad">Reviewer name is required.</span>';
    return;
  }
  try {
    const record = await fetchJSON(`/approval/${approvalId}/${button.dataset.action}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reviewer, comment }),
    });
    message.innerHTML = `${pill(record.status)} <span class="muted">by ${esc(record.reviewer)} at ${esc((record.decided_at || "").slice(0, 19))}</span>`;
    item.querySelectorAll("button").forEach((b) => (b.disabled = true));
    setTimeout(() => {
      loadApprovals();
      loadDecisions();
    }, 1200);
  } catch (err) {
    message.innerHTML = `<span class="pill bad">${esc(err.message)}</span>`;
  }
}

/* ---------------- Audit ---------------- */

function initAudit() {
  loadAuditRuns();
}

async function loadAuditRuns() {
  const target = document.getElementById("audit-runs");
  const detail = document.getElementById("audit-detail");
  target.innerHTML = '<div class="spinner">Loading…</div>';
  try {
    const data = await fetchJSON("/audit/runs");
    const runs = data.runs || [];
    if (!runs.length) {
      target.innerHTML = '<div class="empty">No audited runs yet. Run a question from the dashboard to create audit events.</div>';
      return;
    }
    const rows = runs
      .map(
        (run) => `<tr class="clickable" data-run="${esc(run.run_id)}">
          <td class="mono">${esc(run.run_id.slice(0, 12))}…</td>
          <td>${esc(run.question_preview || "-")}</td>
          <td>${pill(run.final_status || "in_progress")}</td>
          <td>${pill(run.approval_status || "approval_not_required")}</td>
          <td>${esc(run.event_count)}</td>
          <td class="muted small">${esc((run.started_at || "").slice(0, 19))}</td>
        </tr>`
      )
      .join("");
    target.innerHTML = `<table><thead><tr><th>Run</th><th>Question</th><th>Status</th><th>Approval</th><th>Events</th><th>Started</th></tr></thead><tbody>${rows}</tbody></table>`;
    target.querySelectorAll("tr.clickable").forEach((row) => {
      row.addEventListener("click", () => loadAuditEvents(row.dataset.run, detail));
    });
  } catch (err) {
    target.innerHTML = `<div class="error-box">${esc(err.message)}</div>`;
  }
}

function auditRunSummary(data) {
  const summary = data.run_summary || {};
  const approval = data.approval;
  const approvalStatus = (approval && approval.status) || summary.approval_status || "approval_not_required";
  let html = `
    <div class="row" style="margin:0 0 6px">${pill(summary.final_status || "in_progress")} ${pill(approvalStatus)}</div>
    <p style="margin:4px 0 12px"><strong>${esc(summary.question_preview || "(question preview unavailable)")}</strong></p>`;
  if (approval) {
    if (approval.released_answer) {
      html += `
        <h2>Released answer</h2>
        <div class="answer-box">${esc(approval.released_answer)}</div>
        <p class="small muted">${decisionLine(approval)}</p>`;
    } else if (approval.status === "rejected") {
      html += `<p class="small">${decisionLine(approval)}. The answer was not released.</p>`;
    } else if (approval.status === "pending_approval") {
      html += `<p class="small">Awaiting review — the answer stays withheld until decided. <a href="/app/approvals">Open the approval queue</a>.</p>`;
    }
  }
  return html;
}

async function loadAuditEvents(runId, detail) {
  detail.innerHTML = '<div class="spinner">Loading events…</div>';
  try {
    const data = await fetchJSON(`/audit/runs/${runId}`);
    const rows = (data.events || [])
      .map(
        (event) => `<tr>
          <td class="muted small">${esc((event.timestamp || "").slice(11, 19))}</td>
          <td>${pill(event.event_type)}</td>
          <td>${esc(event.summary)}</td>
          <td class="mono">${esc((event.event_hash || "").slice(0, 12))}…</td>
        </tr>`
      )
      .join("");
    detail.innerHTML = `
      <h2>Run <span class="mono">${esc(runId.slice(0, 12))}…</span></h2>
      ${auditRunSummary(data)}
      <h2 style="margin-top:16px">Events</h2>
      <p class="small muted">Tamper-evident hash chain — each event hash covers the previous one. <a href="/audit/export/${esc(runId)}" target="_blank">Export JSON</a></p>
      <table><thead><tr><th>Time</th><th>Event</th><th>Summary</th><th>Hash</th></tr></thead><tbody>${rows}</tbody></table>
    `;
  } catch (err) {
    detail.innerHTML = `<div class="error-box">${esc(err.message)}</div>`;
  }
}

/* ---------------- Evals ---------------- */

function initEvals() {
  loadEvals();
}

async function loadEvals() {
  const tiles = document.getElementById("eval-tiles");
  const tableTarget = document.getElementById("eval-table");
  const runsTarget = document.getElementById("eval-runs");
  try {
    const data = await fetchJSON("/eval/latest");
    const run = data.eval_run;
    if (!run) {
      tiles.innerHTML = "";
      tableTarget.innerHTML = `<div class="empty">${esc(data.message || "No saved eval runs yet.")}</div>`;
      runsTarget.innerHTML = "";
      return;
    }
    tiles.innerHTML = `
      <div class="tile"><div class="label">Accuracy</div><div class="value">${(run.accuracy * 100).toFixed(1)}%</div><div class="note">${esc(run.passed)}/${esc(run.total)} passed</div></div>
      <div class="tile"><div class="label">Faithfulness</div><div class="value">${(run.grounding_rate * 100).toFixed(1)}%</div><div class="note">grounded / verified / recovered</div></div>
      <div class="tile"><div class="label">Avg latency</div><div class="value">${run.avg_latency_ms === null || run.avg_latency_ms === undefined ? "n/a" : esc(run.avg_latency_ms) + " ms"}</div><div class="note">backend-reported</div></div>
      <div class="tile"><div class="label">Cost / query</div><div class="value">$${esc(run.estimated_cost_per_query)}</div><div class="note">estimated, not billing</div></div>
      <div class="tile"><div class="label">Eval rows</div><div class="value">${esc(run.total)}</div><div class="note">${esc(run.manual_review)} manual review</div></div>
    `;
    const rows = (run.rows || [])
      .map(
        (row, index) => `<tr>
          <td>${index + 1}</td>
          <td>${esc(row.question)}</td>
          <td>${pill(row.eval_status)}</td>
          <td>${pill(row.grounding_status)}</td>
          <td>${row.latency_ms === null || row.latency_ms === undefined ? "-" : esc(row.latency_ms) + " ms"}</td>
        </tr>`
      )
      .join("");
    tableTarget.innerHTML = `
      <h2>Latest eval run <span class="mono small muted">${esc(run.eval_run_id)}</span></h2>
      <table><thead><tr><th>#</th><th>Question</th><th>Result</th><th>Grounding</th><th>Latency</th></tr></thead><tbody>${rows}</tbody></table>
    `;
    const listing = await fetchJSON("/eval/runs");
    const items = (listing.eval_runs || [])
      .map(
        (item) => `<tr>
          <td class="mono small">${esc(item.eval_run_id)}</td>
          <td class="muted small">${esc((item.created_at || "").slice(0, 19))}</td>
          <td>${(item.accuracy * 100).toFixed(1)}%</td>
          <td>${(item.grounding_rate * 100).toFixed(1)}%</td>
          <td>${esc(item.total)}</td>
        </tr>`
      )
      .join("");
    runsTarget.innerHTML = items
      ? `<h2>Saved eval runs</h2><table><thead><tr><th>Run</th><th>Created</th><th>Accuracy</th><th>Faithfulness</th><th>Rows</th></tr></thead><tbody>${items}</tbody></table>`
      : "";
  } catch (err) {
    tableTarget.innerHTML = `<div class="error-box">${esc(err.message)}</div>`;
  }
}

/* ---------------- Red team ---------------- */

function initRedTeam() {
  document.getElementById("red-team-run").addEventListener("click", runRedTeam);
  loadRedTeam();
}

async function runRedTeam() {
  const button = document.getElementById("red-team-run");
  button.disabled = true;
  try {
    await fetchJSON("/red-team/run", { method: "POST" });
    await loadRedTeam();
  } catch (err) {
    document.getElementById("red-team-table").innerHTML = `<div class="error-box">${esc(err.message)}</div>`;
  } finally {
    button.disabled = false;
  }
}

async function loadRedTeam() {
  const tiles = document.getElementById("red-team-tiles");
  const target = document.getElementById("red-team-table");
  try {
    const data = await fetchJSON("/red-team/latest");
    const report = data.report;
    if (!report) {
      tiles.innerHTML = "";
      target.innerHTML = `<div class="empty">${esc(data.message || "No red-team run saved yet.")} Click "Run red-team checks" above.</div>`;
      return;
    }
    tiles.innerHTML = `
      <div class="tile"><div class="label">Scenarios</div><div class="value">${esc(report.total)}</div></div>
      <div class="tile"><div class="label">Defended</div><div class="value">${esc(report.defended)}</div></div>
      <div class="tile"><div class="label">Requires backend</div><div class="value">${esc(report.requires_backend)}</div><div class="note">not simulated offline</div></div>
      <div class="tile"><div class="label">Failed</div><div class="value">${esc(report.failed)}</div></div>
    `;
    const rows = (report.findings || [])
      .map(
        (finding) => `<tr>
          <td class="mono small">${esc(finding.finding_id)}</td>
          <td>${esc(finding.scenario)}</td>
          <td class="small">${esc(finding.expected_defense)}</td>
          <td class="small">${esc(finding.actual_result)}</td>
          <td>${pill(finding.status)}</td>
          <td class="mono small">${esc(finding.linked_test || "-")}</td>
        </tr>`
      )
      .join("");
    target.innerHTML = `
      <p class="small muted">Generated ${esc((report.generated_at || "").slice(0, 19))} — deterministic checks exercise the real validation code paths offline; backend-dependent scenarios are honestly labeled.</p>
      <table><thead><tr><th>#</th><th>Scenario</th><th>Expected defense</th><th>Actual result</th><th>Status</th><th>Linked test</th></tr></thead><tbody>${rows}</tbody></table>
    `;
  } catch (err) {
    target.innerHTML = `<div class="error-box">${esc(err.message)}</div>`;
  }
}

/* ---------------- Before/after demo ---------------- */

function initDemo() {
  const form = document.getElementById("demo-form");
  const output = document.getElementById("demo-result");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const question = document.getElementById("demo-question").value.trim();
    const requireApproval = document.getElementById("demo-require-approval").checked;
    if (!question) return;
    output.innerHTML = '<div class="spinner">Running first-pass and orchestrated workflow…</div>';
    try {
      const data = await fetchJSON("/demo/before-after", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, require_approval: requireApproval }),
      });
      output.innerHTML = `
        <div class="grid">
          <div class="card">
            <h2>Before — raw first-pass answer</h2>
            <div class="row" style="margin:0 0 10px">${pill(data.first_pass_status)} <span class="muted small">${esc(data.first_pass_citation_count)} citations</span></div>
            ${data.first_pass_answer
              ? `<div class="answer-box">${esc(data.first_pass_answer)}</div>`
              : `<div class="empty">No first-pass answer available${data.first_pass_error ? ": " + esc(data.first_pass_error) : ""}.</div>`}
            <p class="small muted" style="margin-bottom:0">Single <span class="mono">ask_grounded</span> call — no validation, no recovery, no governance.</p>
          </div>
          <div class="card">
            <h2>After — governed workflow</h2>
            <div class="row" style="margin:0 0 10px">
              ${pill(data.orchestrated_status)} ${pill(data.approval_status)}
              ${data.recovery_used ? '<span class="pill info">recovery used</span>' : ""}
            </div>
            <div class="answer-box">${esc(data.orchestrated_answer || "[no answer]")}</div>
            <p class="small muted" style="margin-bottom:0">
              run_id <span class="mono">${esc((data.run_id || "").slice(0, 12))}…</span> ·
              ${esc(data.audit_event_count || 0)} audit events ·
              ${esc(data.citation_count)} citations · ${esc(data.evidence_count)} evidence items
            </p>
          </div>
        </div>
        <div class="card">
          <h2>Workflow timeline</h2>
          ${timelineTable(data.timeline)}
          ${decisionTrail(data.decision_trail)}
        </div>
      `;
    } catch (err) {
      output.innerHTML = `<div class="error-box">Backend unavailable or run failed: ${esc(err.message)}. No fabricated before/after output is shown.</div>`;
    }
  });
}

/* ---------------- Bootstrap ---------------- */

document.addEventListener("DOMContentLoaded", () => {
  const page = document.body.dataset.page;
  const initializers = {
    dashboard: initDashboard,
    approvals: initApprovals,
    audit: initAudit,
    evals: initEvals,
    "red-team": initRedTeam,
    demo: initDemo,
  };
  if (initializers[page]) initializers[page]();
});
