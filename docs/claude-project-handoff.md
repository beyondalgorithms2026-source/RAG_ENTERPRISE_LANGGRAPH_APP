# Project Handoff for Claude: Enterprise RAG LangGraph/MCP Orchestration

## How to use this document

Treat this as the self-contained context for a repository you cannot inspect. It describes what is implemented, where the security boundaries sit, how answers are checked and recovered, what the human approval gate actually does, and which claims would be an overstatement.

Snapshot verification: the repository's offline test suite currently has **109 passing tests**. The live enterprise backend and sibling MCP server are separate systems and are not exercised by those fake-driven unit tests.

## Executive summary

This project is an **enterprise RAG orchestration and governance application** built with Python, LangGraph/LangChain, FastAPI, and MCP. It sits between a user and an existing enterprise RAG backend.

Its central idea is that an LLM answer is not trustworthy merely because it contains citations. The application:

1. asks the backend for a grounded answer;
2. classifies the question and determines the expected answer shape;
3. checks whether the answer actually contains the requested number, percentage, date, list size, entity, location, quote, or policy response;
4. checks whether the cited snippets support those claims;
5. performs bounded, targeted retrieval recovery when the first answer is weak;
6. refuses, marks for review, or withholds the answer when the evidence is inadequate or the question is high-risk;
7. records a sanitized decision trail and a tamper-evident audit history.

The result is better described as an **inspectable evidence-gated RAG workflow** than as a generic chatbot.

## What belongs to this repository

This repository owns:

- the LangGraph agent wrapper and enterprise system prompt;
- MCP client setup over stdio;
- deterministic answer-quality and recovery orchestration;
- question classification and answer-shape validation;
- citation/evidence support validation;
- bounded recovery sequencing across three MCP tools;
- optional evidence-only answer synthesis with a second verification gate;
- human approval and answer-release control;
- sanitized run journaling and hash-chained audit events;
- an Excel-based evaluation harness;
- deterministic red-team checks;
- a CLI, FastAPI API, and local browser dashboard;
- screenshot-safe Markdown/JSON proof rendering.

It deliberately does **not** own:

- document ingestion or indexing;
- vector, keyword, hybrid, or graph retrieval implementation;
- reranking;
- citation creation;
- database access;
- authentication, authorization, ACL enforcement, or access trimming;
- backend governance or the backend answer model.

Those capabilities belong to the sibling MCP/backend projects. This application can request them and validate their outputs, but it must not claim to implement them.

## Three-system architecture

```text
User / CLI / API / Dashboard
            |
            v
This repository: LangGraph agent + deterministic governed orchestrator
            |
            | MCP over stdio
            v
rag-enterprise-mcp server
  - ask_grounded
  - search_documents
  - get_document_excerpt
            |
            v
Enterprise RAG backend
  - auth and ACL trimming
  - retrieval/reranking
  - answer generation and citations
  - Postgres/pgvector and source documents
```

The app launches the MCP server as a child process with `MultiServerMCPClient`. The transport is stdio, the MCP repository is the child working directory, and only selected backend environment variables are passed to it. The LangGraph application has no SQL or direct backend client.

This separation is a security and architecture feature: the model and orchestration layer cannot bypass the backend by querying the database directly.

## LangGraph, LangChain, and MCP: exact roles

### LangGraph

The free-form `/ask` path uses LangChain's `create_agent`, which is backed by LangGraph. The graph manages the message/tool loop and lets the model choose among the available MCP tools under a strict system prompt.

The prompt requires `ask_grounded(question, k_chunks=6, mode="hybrid")` first for enterprise facts, instructs keyword recovery for literal values, tells the model to expand neighboring chunks when snippets appear cut off, and treats retrieved text as untrusted evidence rather than instructions.

Important qualification: the highly governed `/ask-orchestrated` and proof paths are currently implemented as an explicit Python state machine in `EnterpriseRagOrchestrator.run()`. They are not custom `StateGraph` nodes, do not use a LangGraph checkpointer, and do not pause through a LangGraph `interrupt`. LangGraph supplies the agentic tool-loop path and an obvious future frame for graph-native persistence/HITL, while the strongest current guarantees come from deterministic custom orchestration.

### LangChain

LangChain supplies:

- chat-model initialization;
- message types and final-answer/tool-output extraction;
- tool abstractions (`BaseTool` and `StructuredTool`);
- the prebuilt agent factory;
- the MCP adapter integration.

There is no classic long `LLMChain` pipeline. The design is tool-oriented: LangChain components connect the model and tools; custom code supplies the validation policy.

### MCP

MCP is the only enterprise data/tool boundary. The three expected tools are:

| Tool | Purpose |
| --- | --- |
| `ask_grounded` | Backend retrieval, synthesis, and citations. Used first. |
| `search_documents` | Retrieval-only candidate exploration, especially exact/keyword recovery. |
| `get_document_excerpt` | Narrow raw excerpt lookup after a source or source part has been selected. |

MCP keeps the orchestration layer backend-agnostic and prevents business data access from leaking into the agent code. Tool arguments are normalized before invocation: missing questions are restored from the original user context, empty optional fields are removed, `search_documents.k` is constrained to 1–50 with default 8, and `ask_grounded.k_chunks` to 1–20 with default 6. Tool exceptions become structured error payloads rather than uncontrolled crashes.

## Two execution paths

### 1. Free-form agent path

`RagEnterpriseAgent` loads the MCP tools and invokes the LangGraph-backed agent. This is flexible and conversational. The model may decide when to search or inspect an excerpt, but its guarantees depend more heavily on prompt compliance.

Use it for ordinary interactive questions and demonstrations of model-directed tool use.

### 2. Governed orchestration path

`EnterpriseRagOrchestrator` controls the tool sequence in code. This is the proof, evaluation, approval, audit, and high-assurance path. It records every attempt and does not let the LLM decide whether weak evidence is acceptable.

Use it for reproducible evaluation, portfolio proof, risk-sensitive questions, and any workflow that needs a stable status and inspectable rationale.

## Governed answer workflow

### Stage 1: classify the question

The app derives a `QuestionProfile` and `AnswerShape`. Heuristic types include:

- exact numeric;
- percentage or ratio;
- date/time;
- person or organization;
- location;
- list with a requested count;
- definition;
- comparison;
- cause/reason;
- process/steps;
- summary;
- policy/compliance;
- yes/no;
- exact quote/wording;
- open-ended analysis.

The expected shape says, for example, that an answer must include a percentage, a four-digit year, exactly three supported list items, a named entity, or exact wording.

### Stage 2: fixed first pass

The first call is always:

```text
ask_grounded(question=<original question>, k_chunks=6, mode="hybrid")
```

Transport failures are classified separately as `backend_auth_failed`, `backend_timeout`, or `tool_error` and stop the run safely. Error-like text hidden inside backend debug metadata is deliberately not treated as a transport failure.

### Stage 3: answer and citation review

The response is not accepted simply because citations exist. The app checks:

- whether an answer exists;
- whether citations exist;
- whether the answer is generic, weak, or says the source does not contain the answer;
- whether an exact-value question actually contains the requested field;
- whether citation snippets contain meaningful anchors from the question;
- whether each requested list item is supported;
- whether answer numerics, percentages, dates, and named entities are present in the evidence;
- whether a citation looks cut off at a chunk boundary;
- whether the backend used a repair/fallback generation path.

A cited first-pass answer becomes `verified` only after these checks pass.

### Stage 4: bounded recovery

When the first pass is missing, uncited, incomplete, unsupported, or not found, recovery is bounded by `max_recovery_steps`/`max_attempts`:

1. Retry `ask_grounded` in `keyword` mode with anchor terms, an exact-phrase bias when available, and neighboring-chunk expansion when needed.
2. Call `search_documents` in keyword mode (`k=8`) and rank candidate snippets by backend score plus local evidence-validation score.
3. If necessary, broaden the keyword search with `expand_neighbors=true` and `force_rare_keyword_scan=true`, then call `get_document_excerpt` for the best validated source/source part.

The stage counter is a recovery-policy bound, not literally a cap on individual MCP calls: stage 3 can include both a broadened search and an excerpt lookup.

### Stage 5: evidence validation

Recovered evidence receives a verdict of `supports`, `partial`, or `irrelevant`.

The score is currently:

```text
0.35 * anchor coverage
+ 0.45 * rule/expected-term coverage
+ 0.20 * answer-type signal
```

`supports` requires a score of at least 0.65 and a positive answer-type signal. A result from the correct document that does not answer the question is not accepted as recovered. It becomes `needs_review` or `not_grounded`, and rejected evidence is recorded.

Rules can include aliases and required term groups. Built-in rules currently include several dataset-specific QA cases; `config/orchestration-rules.json` appends human-authored rules without allowing the application to auto-promote observations into policy.

### Stage 6: answer construction

The recovery path is extractive by default. It selects the focused supporting sentence/value and preserves a verbatim source-evidence span.

Optional synthesis is enabled with `RAG_AGENT_ENABLE_SYNTHESIS=true`. A model may rewrite evidence into one or two readable sentences, but the result is displayed only if:

- every number/percentage is found in the source;
- every capitalized entity is found in the source;
- lexical overlap is sufficient;
- the shared answer reviewer finds no unsupported item.

If any gate fails, the app falls back to the extractive/verbatim answer.

### Stage 7: final status

Important statuses are:

| Status | Meaning |
| --- | --- |
| `verified` | First-pass answer passed answer-shape and citation-support checks. |
| `recovered` | A later answer/evidence path passed the required checks. |
| `partial` | Some support exists, but the requested answer shape is incomplete. |
| `needs_review` | Nearest evidence exists but cannot be safely accepted automatically. |
| `not_grounded` | No adequately supported answer could be produced. |
| `not_found` | The indexed sources did not yield an answer after recovery. |
| `backend_auth_failed` | Backend rejected authentication/authorization at transport level. |
| `backend_timeout` | Backend/tool call timed out. |
| `tool_error` | Another MCP/tool failure occurred. |

The timeline, attempt records, evidence verdict, decision trail, and final status are designed to tell the same story.

## Security model

### Implemented in this repository

- **No direct data access:** all enterprise content flows through MCP tools.
- **Prompt-injection posture:** retrieved content is explicitly treated as untrusted evidence, not executable instruction. The deterministic path evaluates it without inserting it into the agent's system prompt.
- **Fail-closed grounding:** uncited, weak, irrelevant, or transport-failed answers are not labeled verified.
- **Argument guardrails:** malformed model tool arguments are cleaned and bounded.
- **Secret/path redaction:** debug data, prompts, messages, tracebacks, raw payload keys, credentials, cookies, tokens, passwords, API keys, and local user paths are dropped or scrubbed from shareable proof, journals, and audit events.
- **Safe diagnostics:** credential settings are reported only as `*_present` booleans.
- **Quiet proof mode:** MCP child stderr can be suppressed to prevent local tracebacks and paths leaking into screenshots.
- **Answer withholding:** pending or rejected approvals remove the answer, citations, evidence snippets, synthesis, verbatim answer, rejected evidence, and raw tool outputs from the live response.

### Enforced outside this repository

- user authentication;
- source permissions and ACL trimming;
- tenant isolation;
- database security;
- retrieval authorization;
- citation generation.

These are backend responsibilities. The offline suite cannot prove them.

## Human-in-the-loop approval matrix

Approval is an answer-release gate backed by an append-only JSONL store.

| Approval mode | Low-risk verified result | High-risk category | `partial` / `needs_review` / review recommended |
| --- | --- | --- | --- |
| `off` | Release | Release (with review note) | Release workflow result; no approval hold |
| `high-risk-only` | Release | Withhold pending approval | Withhold pending approval |
| `always` | Withhold pending approval | Withhold pending approval | Withhold pending approval |

High-risk keyword categories are HR, legal, finance, medical, security, and compliance/policy. `--require-approval` maps to `high-risk-only` unless another mode is specified.

A pending record contains a stable approval ID, run ID, risk reasons, evidence/grounding status, and a sanitized internal answer copy. A named reviewer must approve or reject it and may add a comment. The decision is appended to the approval store and audit log. Approved answers can later be released from the persisted run record; rejected answers remain withheld.

This is real HITL, but it is not yet a production approval hierarchy. There is one decision step, no role-based approver assignment, no quorum/four-eyes rule, no SLA/escalation, no expiry, and no authenticated reviewer identity in this local application.

## Search-mode choice: what is and is not exposed

The backend is described as supporting hybrid/vector/keyword/graph retrieval, but this application's governed policy intentionally chooses modes itself:

- hybrid for the initial grounded answer;
- keyword for exact-value recovery;
- expanded/rare-keyword search for difficult literal evidence;
- source excerpt lookup after candidate validation.

The free-form LangGraph agent can choose tool arguments allowed by the MCP schema. The governed CLI/API currently exposes validation mode and recovery depth, but **does not expose a direct end-user `search_mode` option**. Vector or graph mode selection is therefore not a current governed-workflow feature. Adding it would require a deliberate public API/CLI and policy decision.

Validation modes are exposed as `strict`, `balanced`, and `fast`. In the current implementation, `strict` forces recovery/evidence inspection even after a verified first answer; `balanced` and `fast` currently take the same early-acceptance branch. The latter two are labels awaiting more differentiated behavior.

## Audit trail and journal

There are two related records:

### Decision journal

An optional JSONL journal stores sanitized high-level outcomes: question, expected answer, anchors, status, tools, timeline, evidence verdict, rejected evidence summary, validation summary, attempts, decision trail, and failure reason.

### Tamper-evident audit log

Each orchestrated run gets a stable `run_id`. Audit events include:

- `run_started`;
- `question_classified`;
- `tool_call_started`, `tool_call_completed`, or `tool_call_failed`;
- `answer_reviewed`;
- `evidence_validated`;
- `recovery_planned` and `recovery_attempted`;
- `approval_requested`, `approval_approved`, or `approval_rejected`;
- `run_completed`.

Each sanitized event stores the previous event hash and its own SHA-256 hash over a canonical representation. The application can verify the chain and identify the first invalid event after tampering. The chain survives process restarts by reading the last hash.

This is tamper-evident, not tamper-proof: it is not digitally signed, externally anchored, write-once storage, or protected from an attacker who can rewrite the entire file and recompute every hash.

## Red-team methodology

The repository has a scenario catalog and an offline runner that calls the real local validation/risk-classification functions. Current scenarios cover:

1. prompt injection inside retrieved text;
2. answers without citations;
3. irrelevant citations;
4. incorrect exact numeric values;
5. unsupported list items;
6. unauthorized/private content requests;
7. backend timeouts;
8. backend authentication failures;
9. high-risk answers bypassing approval;
10. retrieved text attempting to override rules and leak embedded secrets.

The report labels each scenario `defended`, `failed`, `manual_review`, or `requires_backend`. ACL/private-content validation is honestly marked `requires_backend` because the agent repository cannot simulate the backend's authorization controls.

This is a deterministic regression-oriented red-team suite, not a full adversarial security assessment. It does not currently perform model fuzzing, multi-turn jailbreak campaigns, data-exfiltration probes against a live deployment, load/denial-of-service testing, or independent penetration testing.

## Evaluation and observability

The Excel evaluation harness reads `question` and `human_answer` columns, with optional file/post metadata. It runs the same governed orchestrator, checks expected terms against answer and evidence, and produces:

- `pass` only when grounding status succeeds and expected-answer terms match;
- `manual_review` for `partial` or `needs_review`;
- `fail` otherwise.

Persisted eval summaries report accuracy, grounding/faithfulness rate, latency, and an explicitly labeled estimated cost per query. Cost is based on configurable token-price assumptions, not actual billing telemetry.

The dashboard provides ask, approvals, audit runs/events, eval summaries, red-team findings, and a before/after comparison between raw `ask_grounded` and the governed result.

## What makes the project distinctive

- **Citations are treated as claims to verify, not decorative proof.**
- **Answer shape is part of correctness.** Three requested items require three individually supported items; a percentage question needs the percentage.
- **Recovery is evidence-seeking, not blind retrying.** It changes retrieval strategy, uses anchors/exact phrases, detects chunk boundaries, validates candidates, and inspects the best raw excerpt.
- **Transport failures and answer-quality failures remain separate.** This prevents a timeout from being mislabeled as “not found” and prevents weak evidence from hiding operational failures.
- **Irrelevant evidence cannot become a success merely because it comes from the right source.**
- **The deterministic path is mostly non-generative.** Optional synthesis is subordinate to source verification and extractive fallback.
- **Governance is visible.** Attempts, rejected evidence, validation reasons, recovery, approval, and audit events can be inspected rather than hidden behind one final answer.
- **Security boundaries are honest.** Backend ACL claims are not “tested” by a fake agent-layer test.
- **Weak-model behavior is anticipated.** Tool argument normalization makes the MCP contract more resilient.
- **Portfolio/shareable output is treated as a security surface.** Redaction is tested across proof, journal, audit, and diagnostics.

## Current shortcomings and production gaps

1. **The strongest workflow is not yet graph-native.** The deterministic orchestrator is a large Python method. Moving stages into explicit LangGraph nodes with typed state, conditional edges, checkpointing, and graph-native interrupts would improve visualization, resumability, and maintainability.
2. **HITL is local and unauthenticated.** JSONL persistence and reviewer-name strings are suitable for a proof application, not a regulated production approval system.
3. **Risk classification is keyword-based.** It can miss subtle high-risk questions and can over-trigger on harmless wording.
4. **Question and evidence validation are heuristic.** Lexical overlap, answer-type regexes, and hand-authored rules can produce false positives or false negatives.
5. **Some built-in evidence rules are dataset-specific.** A generalized deployment needs domain-owned policies or learned/structured validators without weakening the deterministic gates.
6. **Search policy is not user-configurable in the governed API.** Hybrid-first/keyword-recovery is fixed; vector/graph choices are backend capabilities, not current user controls.
7. **`balanced` and `fast` are not meaningfully differentiated yet.** Only `strict` changes routing.
8. **Local file stores are not concurrency-grade databases.** JSONL and one-file-per-run storage lack transactional locking, retention controls, encryption-at-rest management, backup policy, and multi-instance coordination.
9. **The audit chain is not externally trusted.** It detects ordinary edits but is not signed or anchored outside the host.
10. **Red-team coverage is mostly deterministic/offline.** Live ACL, tenant isolation, model attacks, and end-to-end deployment security still require backend and infrastructure testing.
11. **No live-backend guarantee comes from the unit suite.** The 113 tests use fakes by design; configuration discovery and a live demo proof must be run separately.
12. **The local dashboard/API needs deployment hardening.** It binds to localhost by default; exposing it would require authentication, authorization, CSRF/CORS decisions, TLS, rate limits, and protected approval/audit endpoints.

## Iterative learning embodied in the code

The commit and test history reflects a sequence of practical corrections:

- MCP responses sometimes arrived as text blocks, so a robust unwrapping layer was added.
- Backend error details could include tracebacks/local paths, so proof output, journals, audit events, diagnostics, and MCP stderr were treated as separate leakage surfaces.
- Early logic risked confusing backend timeout/auth failures with “not found,” so transport classification was isolated and made fail-fast.
- Citation presence initially looked like a sufficient success signal; later iterations added question typing, answer-shape checks, citation-snippet support, per-item validation, and chunk-cutoff recovery.
- Retrieval could find a source without finding the answer, so evidence now needs a positive `supports` verdict before recovery is called successful.
- Evaluation needed to distinguish product failure from reviewer uncertainty, so `pass`, `fail`, and `manual_review` were kept separate.
- Governance claims needed inspectability, leading to a stable run ID, attempt history, decision trail, approval persistence, hash-chained audit events, and red-team reports.
- Readable recovered answers introduced hallucination risk, so synthesis was made optional, source-constrained, independently verified, and extractive-fallback by default.
- Approval initially risked withholding only the main answer while leaking it through citations/snippets; the current release gate withholds all answer-bearing fields.

The broad lesson is that enterprise RAG quality is not one retrieval score or one prompt. It is an end-to-end contract across transport, retrieval evidence, answer shape, support validation, failure semantics, release policy, redaction, auditability, and human review.

## Main files

| File | Responsibility |
| --- | --- |
| `graph.py` | Agent model initialization and enterprise system prompt. |
| `agent.py` | Free-form LangGraph agent execution and message/tool extraction. |
| `mcp_client.py` | MCP stdio connection, tool loading, and quiet stderr context. |
| `tool_guard.py` | MCP argument normalization and structured error conversion. |
| `orchestrator.py` | Deterministic first pass, validation, recovery, statuses, attempts, approval hookup, and audit emissions. |
| `answer_quality.py` | Question types, expected answer shapes, citation/answer review. |
| `evidence.py` | Evidence scoring, rule matching, expected-answer evaluation. |
| `synthesis.py` | Optional source-only synthesis and independent verification. |
| `approval.py` | Risk assessment, approval persistence, release views, approval API. |
| `run_store.py` | Sanitized run persistence and approval-aware answer release. |
| `audit.py` | Sanitized hash-chained event log and chain verification. |
| `journal.py` | Safe decision journal and sensitive-key removal. |
| `red_team.py` | Offline red-team scenario runner and report rendering. |
| `eval_runner.py`, `eval_store.py` | QA evaluation, metrics, persistence, and API. |
| `demo_proof.py` | Shareable proof payloads and Markdown/text rendering. |
| `server.py`, `ui.py`, `static/` | FastAPI endpoints and browser dashboard. |

## Basic usage

```bash
# Install into the project virtual environment
python3.12 -m venv .venv312
.venv312/bin/pip install -e '.[dev]'

# Offline tests (no MCP/backend required)
.venv312/bin/pytest

# Live MCP configuration/tool discovery
PYTHONPATH=src .venv312/bin/python -m rag_enterprise_langgraph.cli --check-config

# Governed proof
PYTHONPATH=src .venv312/bin/python -m rag_enterprise_langgraph.cli \
  --demo-proof --question "What does the employee handbook say about VPN access?" \
  --show-decision-trail

# High-risk approval gate
PYTHONPATH=src .venv312/bin/python -m rag_enterprise_langgraph.cli \
  "What is the employee termination policy?" --require-approval

# Red-team report
PYTHONPATH=src .venv312/bin/python -m rag_enterprise_langgraph.cli --red-team

# API and dashboard at http://127.0.0.1:8080/app
PYTHONPATH=src .venv312/bin/python -m rag_enterprise_langgraph.server
```

The live commands require the sibling MCP repository, a configured backend, and appropriate credentials. The offline suite does not.

## One-paragraph description to reuse

This is a Python enterprise RAG governance layer built with LangGraph/LangChain and MCP. It never accesses the document database directly; it calls a separate MCP server for grounded answers, search, and excerpts. Its governed workflow classifies each question, validates the required answer shape, verifies that citations actually support every requested fact, and performs bounded hybrid-to-keyword recovery when the first response is weak. Unsupported answers fail closed or go to human review. High-risk HR, legal, finance, medical, security, and compliance answers can be withheld behind a persisted approval gate. Every run produces a sanitized decision trail and hash-chained audit history, while deterministic red-team and QA evaluation suites test grounding, failure handling, leakage controls, and approval routing. Its distinctive quality is not retrieval itself, but the inspectable control system around retrieval and answer release.
