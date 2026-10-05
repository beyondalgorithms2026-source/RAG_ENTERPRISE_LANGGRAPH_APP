"use strict";
// Component inspector for the "How it works" blueprint.
(() => {
  const G = "https://github.com/beyondalgorithms2026-source/";
  const APP = G + "RAG_ENTERPRISE_LANGGRAPH_APP/blob/main/src/rag_enterprise_langgraph/";
  const ST = G + "RAG_ENTERPRISE_STARTER/blob/main/backend/app/";
  const MCP = G + "RAG_Langgraph_MCP_server/blob/main/src/rag_enterprise_mcp/";
  const NODES = {
    visitor: { kind: "Browser", name: "Visitor and demo UI", short: "Ask · Documents",
      summary: "Server-rendered pages with plain JavaScript. The browser holds no model keys and cannot choose a model or a retrieval setting.",
      owns: ["Company switch (Northline or Northwind)", "Cited answers with open-the-source links", "Read-only Audit, Approvals, Quality and Security pages"],
      files: [["ui.py", APP + "ui.py"], ["app.js", APP + "static/app.js"]], meta: ["public demo", "no login"] },
    app: { kind: "Service · Python", name: "APP · orchestration layer", short: "288 tests",
      summary: "Decides whether an answer may be released. It runs a fixed plan instead of letting a model call tools freely.",
      owns: ["Input screening for prompt injection", "Hybrid first pass, then at most three narrower steps", "Evidence verdict and answer-shape review", "Approval gate for HR, legal, finance, medical, security and compliance", "Hash-chained audit log, eval runner, red-team map"],
      files: [["orchestrator.py", APP + "orchestrator.py"], ["evidence.py", APP + "evidence.py"], ["approval.py", APP + "approval.py"], ["audit.py", APP + "audit.py"]],
      meta: ["288 tests", "no DB access"] },
    mcp: { kind: "Child process · stdio", name: "MCP · tool boundary", short: "42 tests",
      summary: "The only path from the orchestration layer to the data. Three read-only tools with closed schemas, written with the Python standard library only.",
      owns: ["ask_grounded · search_documents · get_document_excerpt", "Drops unknown arguments, forwards an optional company scope", "Forwards the caller's identity; cannot widen it"],
      files: [["server.py", MCP + "server.py"], ["schemas/backend.py", MCP + "schemas/backend.py"]], meta: ["42 tests", "no dependencies"] },
    starter: { kind: "Service · FastAPI", name: "STARTER · data layer", short: "148 tests",
      summary: "Owns retrieval, access control and citations. Who may see a document is part of the search query, so a restricted text is never selected.",
      owns: ["Hybrid keyword + vector search", "Five access strategies composed into SQL", "Company scope ANDed onto access control", "Citations required, else \"Not found in provided sources.\"", "Ingest for seven document formats"],
      files: [["access_strategy.py", ST + "auth/access_strategy.py"], ["repo_search.py", ST + "db/repo_search.py"], ["corpus_scope.py", ST + "core_rag/corpus_scope.py"], ["answering.py", ST + "core_rag/answering.py"]],
      meta: ["148 tests", "rate-limited"] },
    db: { kind: "Managed database", name: "PostgreSQL + pgvector", short: "Supabase",
      summary: "Sources, chunks, 384-dimension embeddings and the access-control tables, hosted on Supabase.",
      owns: ["Executes the access clause with every search", "42 synthetic documents across two companies", "No public access; reached only by the data layer"],
      files: [["schema.sql", ST + "db/schema.sql"]], meta: ["Supabase", "Singapore"] },
    openai: { kind: "External API", name: "OpenAI", short: "pinned",
      summary: "Called only by the data layer, with pinned model versions and a hard monthly spend limit on the project.",
      owns: ["text-embedding-3-small at 384 dimensions", "gpt-4o-mini-2024-07-18, max 600 output tokens", "USD 1/month project limit; a full eval run costs about $0.03"],
      files: [], meta: ["pinned", "$1/month cap"] },
  };
  const els = { kind: i("i-kind"), name: i("i-name"), summary: i("i-summary"), owns: i("i-owns"), files: i("i-files"), meta: i("i-meta") };
  function i(id) { return document.getElementById(id); }
  const picker = i("picker");
  picker.innerHTML = Object.entries(NODES).map(([key, node]) => `<button type="button" data-pick="${key}">${node.name.split(" · ")[0]}<small>${node.short}</small></button>`).join("");
  function select(key) {
    const node = NODES[key];
    els.kind.textContent = node.kind; els.name.textContent = node.name; els.summary.textContent = node.summary;
    els.owns.innerHTML = node.owns.map((item) => `<li>${item}</li>`).join("");
    els.files.innerHTML = node.files.map(([label, href]) => `<a href="${href}" target="_blank" rel="noopener noreferrer">${label}</a>`).join("");
    els.meta.innerHTML = node.meta.map((item) => `<span>${item}</span>`).join("");
    document.querySelectorAll(".node").forEach((n) => n.classList.toggle("on", n.dataset.node === key));
    picker.querySelectorAll("button").forEach((b) => b.classList.toggle("on", b.dataset.pick === key));
  }
  document.querySelectorAll(".node").forEach((node) => {
    node.addEventListener("click", () => select(node.dataset.node));
    node.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); select(node.dataset.node); } });
  });
  picker.addEventListener("click", (event) => { const b = event.target.closest("button"); if (b) select(b.dataset.pick); });
  select("starter");
})();
