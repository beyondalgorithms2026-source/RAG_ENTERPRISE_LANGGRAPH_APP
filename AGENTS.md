# AGENTS.md — Model Operating Manual

Operating manual for AI coding agents (Claude, Codex, etc.) working in
`RAG_ENTERPRISE_LANGGRAPH_APP`. Read this before changing anything.

## 1. What this repo is — and is not

This is a **Python LangGraph/MCP orchestration layer for enterprise RAG proof
flows**. It sits between a user (CLI/API) and the `rag-enterprise-mcp` server.

**This repo does NOT implement:**

- Retrieval (vector/keyword/hybrid search)
- ACL checks or access trimming
- Citation generation
- Database access (no Postgres, no pgvector, no SQL)
- Backend governance, auth, audit, or caching
- The RAG backend itself (that lives in the sibling `RAG_ENTERPRISE_STARTER` repo)

**What this repo owns:**

- LangGraph orchestration ([graph.py](src/rag_enterprise_langgraph/graph.py), [agent.py](src/rag_enterprise_langgraph/agent.py))
- Strict answer validation and recovery routing ([orchestrator.py](src/rag_enterprise_langgraph/orchestrator.py), [answer_quality.py](src/rag_enterprise_langgraph/answer_quality.py), [evidence.py](src/rag_enterprise_langgraph/evidence.py))
- Proof rendering ([demo_proof.py](src/rag_enterprise_langgraph/demo_proof.py))
- Eval reporting ([eval_runner.py](src/rag_enterprise_langgraph/eval_runner.py))
- Redaction and safe journaling ([journal.py](src/rag_enterprise_langgraph/journal.py), `redact_for_sharing` in demo_proof.py)
- Tool-argument normalization ([tool_guard.py](src/rag_enterprise_langgraph/tool_guard.py))

**Connection model:** the app spawns the MCP server as a child process over
**stdio** via `MultiServerMCPClient` (`build_stdio_connection` in
[mcp_client.py](src/rag_enterprise_langgraph/mcp_client.py)). The MCP server
repo defaults to `/Users/Work/Projects/repos/RAG_ENTERPRISE_MCP_SERVER` and is
launched with `python -m rag_enterprise_mcp.server`, with backend env vars
(`RAG_BACKEND_*`) passed through from `.env` / the environment
([config.py](src/rag_enterprise_langgraph/config.py)).

**Expected MCP tools** (see `REQUIRED_MCP_TOOLS` in demo_proof.py):

- `ask_grounded` — backend retrieves, reranks, synthesizes, and cites
- `search_documents` — retrieval-only candidate search
- `get_document_excerpt` — raw excerpt lookup by source/part id

The backend and MCP server own retrieval and governance. If a task appears to
require changing retrieval behavior, ACLs, or citations, the change belongs in
the MCP/backend repos, not here — stop and say so.

## 2. Commands

Install (Python 3.12 venv is the project convention):

```bash
/Users/Work/.local/bin/python3.12 -m venv .venv312
.venv312/bin/pip install -e .[dev]
```

Run tests (no backend/MCP needed — tests use fakes):

```bash
.venv312/bin/pytest
```

Diagnostics (spawns the real MCP server; requires the sibling MCP repo and a
configured `.env`):

```bash
PYTHONPATH=src .venv312/bin/python -m rag_enterprise_langgraph.cli --check-config
```

Demo proof flow:

```bash
PYTHONPATH=src .venv312/bin/python -m rag_enterprise_langgraph.cli --demo-proof
```

Useful demo-proof flags: `--question "..."` (repeatable), `--questions-file
demo-questions.txt`, `--output demo-proof.md`, `--json`,
`--max-recovery-steps 3`, `--max-attempts 3`,
`--validation-mode strict|balanced|fast`, `--show-decision-trail`,
`--hide-review-note`, `--include-debug` (internal troubleshooting only).

API server (FastAPI on 127.0.0.1:8080 — endpoints `/healthz`, `/ask`,
`/demo-proof`, `/ask-orchestrated`):

```bash
PYTHONPATH=src .venv312/bin/python -m rag_enterprise_langgraph.server
```

Eval harness (Excel QA workbook against the orchestrator):

```bash
PYTHONPATH=src .venv312/bin/python -m rag_enterprise_langgraph.cli \
  --eval-xlsx /path/to/acquired-qa-evaluation.xlsx \
  --eval-output acquired-eval-report.md \
  --eval-json acquired-eval-results.json \
  --journal runs/orchestration-journal.jsonl \
  --rules config/orchestration-rules.json
```

Console-script equivalents exist after install: `rag-enterprise-agent` (cli)
and `rag-enterprise-api` (server).

## 3. Coding conventions

- **Python 3.10+ compatibility** (`requires-python = ">=3.10"` in
  pyproject.toml). `X | None` unions and `from __future__ import annotations`
  are fine; do not use 3.11+-only syntax or stdlib features.
- **Package code lives under `src/rag_enterprise_langgraph/`.** Tests live in
  `tests/` and are discovered via `testpaths` in pyproject.toml.
- **Match the existing style:** frozen/typed dataclasses with `to_dict()`
  methods, small pure helper functions prefixed `_`, keyword-only arguments
  for multi-parameter functions, no classes where a function will do.
- **Tests are focused and fake-driven.** Replace MCP/backend behavior by
  assigning `orchestrator._call_tool = fake_tool_call` (see
  [test_orchestrator.py](tests/test_orchestrator.py)), by fake
  agent/orchestrator classes (see [test_demo_proof.py](tests/test_demo_proof.py)),
  or by `monkeypatch`. Never require a live MCP server or backend in tests.
- **Do not add direct backend retrieval logic to this app.** No HTTP calls to
  the backend, no DB clients, no embedding libraries. All enterprise data
  flows through the three MCP tools.
- **Do not broaden output fields casually.** Every field added to
  `OrchestratedRunResult.to_dict()`, proof payloads, journal entries, or API
  responses flows into shareable portfolio artifacts. Consider redaction and
  proof safety first (see §5, mistake 3).
- **`config/orchestration-rules.json` is a user-editable extension point.**
  `load_rules()` in evidence.py always keeps `DEFAULT_RULES` and *appends*
  file rules. Do not auto-promote journal observations into rules, and do not
  make code write to this file — humans edit it.
- No linter/formatter is configured; follow the surrounding code's formatting.

## 4. Grounding and orchestration rules

The orchestration policy in `EnterpriseRagOrchestrator.run()` is the product.
Preserve it:

1. **`ask_grounded` first**, with `k_chunks=6` and `mode="hybrid"` for the
   initial pass. The agent system prompt in graph.py encodes the same rule.
2. **Recovery** (bounded by `max_recovery_steps`, default 3) uses:
   - `ask_grounded` in `mode="keyword"` with `anchor_terms` (from
     `extract_anchor_terms`) and `exact_phrase_bias` (from
     `exact_phrase_bias` / `_phrase_for_recovery`)
   - `search_documents` in keyword mode, optionally with
     `expand_neighbors=true` when snippets look cut off, and a broadened pass
     with `force_rare_keyword_scan=true`
   - `get_document_excerpt` for raw excerpt lookup on a validated candidate
3. **Citations alone do not verify an answer.** A cited first-pass answer is
   accepted as `verified` only after `review_answer()` in answer_quality.py
   confirms answer shape (item counts, percentages, dates, numerics) and that
   cited snippets actually support the requested values/list items.
4. **Preserve answer-shape validation in answer_quality.py**: question
   classification (`classify_question`), `AnswerShape` checks, per-item
   citation support, and cut-off detection (`_looks_cut_off` →
   `needs_neighbor_expansion`).
5. **Preserve evidence validation in evidence.py**: `validate_evidence`
   verdicts are `supports` / `partial` / `irrelevant`, scored from anchor
   coverage (0.35), rule/expected-term matches (0.45), and answer-type
   signals (0.20), with `supports` requiring score ≥ 0.65 *and* a positive
   answer-type signal.
6. **Preserve the status vocabulary.** Final `grounding_status` values include
   `verified`, `recovered`, `partial`, `needs_review`, `not_grounded`,
   `not_found`, `backend_auth_failed`, `backend_timeout`, and `tool_error`
   (see `GROUNDING_SUCCESS_STATUSES`, `REVIEW_STATUSES`, `FAILURE_STATUSES`
   in orchestrator.py). `overall_status()` and `_eval_status()` in
   eval_runner.py depend on these exact strings, as do the tests.
7. **Transport failures are not answer-quality failures.**
   `classify_transport_failure` distinguishes auth (401/403), timeout, and
   tool errors from `not_found` / weak answers — and it deliberately ignores
   error-like text inside `debug_info` (see
   `test_normal_not_found_debug_timeout_is_not_transport_failure`).

## 5. Mistakes weaker models make — and the rules that prevent them

1. **Mistake: treating cited answers as automatically verified.**
   Rule: an answer becomes `verified` only after `review_answer()` confirms
   the answer shape and the cited snippets support each requested value/list
   item. Never short-circuit `classify_answer_quality` or `review_answer` to
   "has citations → success".

2. **Mistake: putting retrieval/ACL/backend behavior in this repo.**
   Rule: this app only orchestrates the three MCP tools. The backend/MCP own
   retrieval, ranking, ACLs, citations, and governance. If the fix needs a
   retrieval change, it goes in the MCP/backend repos — say so instead of
   hacking it here.

3. **Mistake: leaking raw debug/prompt/path/secret data into outputs.**
   Rule: every change to proof, journal, or API report output must go through
   and preserve the redaction helpers — `redact_for_sharing` /
   `_sanitize_text` in demo_proof.py, `sanitize_for_journal` /
   `SENSITIVE_KEYS` in journal.py, `_short_error_text` in orchestrator.py,
   and `diagnostic_summary()`'s `*_present` boolean pattern in config.py —
   and keep their tests passing (test_demo_proof.py, test_journal.py,
   test_config.py). Keys like `traceback`, `raw`, `*_prompt`, `messages`,
   `debug_info`, `token`, `password`, `api_key`, `cookie` are dropped or
   `[redacted]`; `/Users/...` paths become `[path-redacted]`.

4. **Mistake: collapsing failure statuses into one generic error.**
   Rule: preserve the distinctions between `backend_auth_failed`,
   `backend_timeout`, `tool_error`, `not_grounded`, and `not_found`. They
   route differently (transport failures abort the run; `not_found` and weak
   answers trigger recovery) and render differently in proofs and evals.

5. **Mistake: accepting irrelevant source matches as recovered answers.**
   Rule: recovered evidence must pass `validate_evidence` with verdict
   `supports`. A snippet from the right document that does not answer the
   question yields `needs_review` (with `rejected_evidence` populated) or
   `not_grounded` — never `recovered`. See
   `test_orchestrator_does_not_recover_from_irrelevant_excerpt`.

6. **Mistake: breaking weak-model tool normalization.**
   Rule: preserve tool_guard.py behavior — a missing/empty `question` is
   filled from the current-question contextvar, empty `filters`/`custom_query`
   are dropped, `search_documents.k` is clamped to [1, 50] with default 8,
   `ask_grounded.k_chunks` is clamped to [1, 20] with default 6, and tool
   exceptions become structured JSON error payloads instead of raising.

## 6. Quality bar (checkable per deliverable)

- **Source changes:** relevant tests added or updated in `tests/`;
  `.venv312/bin/pytest` passes; no boundary violations (no backend HTTP, DB,
  or retrieval code added to this app).
- **Orchestrator changes:** `execution_timeline`, `grounding_status`,
  `attempts`, and `decision_trail` remain mutually coherent — a run's
  timeline steps, attempt records, and final status must tell the same story,
  and journaled entries must match the returned result.
- **Proof/report changes:** rendered Markdown/text/JSON contains no raw debug
  payloads, prompts, tracebacks, secrets, or local paths unless explicitly
  sanitized and intentionally included behind `--include-debug`.
- **Eval changes:** `read_eval_xlsx` still reads the `question` and
  `human_answer` columns (plus optional `file_name`/`post_url`);
  `pass`/`fail`/`manual_review` semantics in `_eval_status` remain intact
  (`pass` requires both a success grounding status and expected-term match;
  `partial`/`needs_review` → `manual_review`).
- **API/CLI changes:** existing command flags and response shapes stay
  backward-compatible unless the change is explicitly documented in README.md
  and this file. Note `to_dict()` intentionally emits both
  `grounding_status` and `answer_status` for compatibility — keep both.

## 7. Escalation rules

Ask the user (do not proceed on your own) before:

- Changing architecture boundaries between this app, the MCP server, and the
  backend (e.g., adding a new transport, calling the backend directly,
  moving validation into the MCP server).
- Adding dependencies to pyproject.toml.
- Changing public CLI flags or API response shapes (`/ask`, `/demo-proof`,
  `/ask-orchestrated`, `OrchestratedRunResult.to_dict()` keys, proof payload
  keys).
- Changing default evidence rules (`DEFAULT_RULES` in evidence.py), verdict
  thresholds, or status semantics/vocabulary.
- Modifying files outside this repo, including the sibling
  `RAG_ENTERPRISE_MCP_SERVER` and `RAG_ENTERPRISE_STARTER` repos.

If the backend or MCP server is unavailable: develop and verify against the
test fakes (`_call_tool` overrides, fake agents/orchestrators), run
`.venv312/bin/pytest`, and state explicitly in your report that a live smoke
proof (`--check-config` / `--demo-proof` against the real MCP server) could
not be run.

## 8. Repo-specific skills

### Skill 1: Orchestrated RAG Recovery Change

**When to use:** any edit to [orchestrator.py](src/rag_enterprise_langgraph/orchestrator.py),
[answer_quality.py](src/rag_enterprise_langgraph/answer_quality.py), or
[evidence.py](src/rag_enterprise_langgraph/evidence.py) — new question types,
recovery steps, verdict scoring, status routing, or attempt comparison.

**Inputs:** the desired behavior change; one or more concrete
question/answer/evidence examples that currently misbehave (from a journal
entry, eval row, or user report).

**Workflow:**

1. Reproduce first as a test. Encode the misbehaving example as a focused
   test using a fake `_call_tool` (copy the pattern from
   `test_orchestrator_unwraps_mcp_text_blocks_before_classification`) or a
   direct unit test on `classify_question` / `review_answer` /
   `validate_evidence` / `classify_answer_quality`.
2. Decide the correct layer:
   - question typing or answer-shape checks → answer_quality.py
   - evidence relevance, verdicts, rules, expected-answer terms → evidence.py
   - tool sequencing, statuses, timeline, attempts, journal → orchestrator.py
3. Make the change without breaking invariants: `ask_grounded` hybrid
   `k_chunks=6` first; transport failures short-circuit; recovery is bounded
   by `max_recovery_steps`; `supports` verdict required for `recovered`;
   status vocabulary unchanged (§4).
4. Update `decision_trail` / `attempts` entries if routing changed, so the
   trail still narrates the actual decisions.
5. Check downstream consumers: `_eval_status` in eval_runner.py,
   `overall_status`, `render_text_report` / `render_markdown_report` in
   demo_proof.py, and journaled fields in `_record_journal`.

**Outputs:** the code change plus new/updated tests in
tests/test_orchestrator.py, tests/test_answer_quality.py, or a new focused
test file.

**Verification:** `.venv312/bin/pytest` passes; the new test fails on the old
code (verify by mentally or actually reverting); for a run-level change,
confirm the resulting `grounding_status`, `execution_timeline`, `attempts`,
and `decision_trail` in the test assertion are mutually coherent. If the
backend is available, optionally run `--demo-proof --question "..."
--show-decision-trail` as a live smoke check; if not, state that.

### Skill 2: Portfolio Proof / Redaction

**When to use:** any edit to [demo_proof.py](src/rag_enterprise_langgraph/demo_proof.py),
[journal.py](src/rag_enterprise_langgraph/journal.py), the report renderers,
or anything that adds/changes fields in CLI/API proof output
(`--demo-proof`, `/demo-proof`, `/ask-orchestrated`, `--journal`).

**Inputs:** the field or rendering change requested; whether the data is
derived from backend tool output (untrusted, may contain private document
text, paths, or debug payloads) or computed locally.

**Workflow:**

1. Trace the data path: tool content → `OrchestratedRunResult` →
   `build_demo_proof` → `redact_for_sharing` → renderer, and separately →
   `_record_journal` → `sanitize_for_journal`. Any new field must pass
   through the redaction step on *both* paths it reaches.
2. If the new field can contain free text from the backend, decide: is it a
   snippet-like field (allowed, truncated — see `_truncate` /
   `snippet_preview[:220]`) or diagnostic (must be dropped or summarized via
   `_short_error_text`-style helpers)?
3. Never emit raw secrets — follow the `*_present` boolean pattern from
   `diagnostic_summary()` for anything credential-like.
4. Respect the display flags: `include_debug`, `show_decision_trail`,
   `show_review_note`. Default output must stay screenshot-safe.
5. Add a redaction test proving the sensitive variant of the new field is
   stripped or `[redacted]` (pattern:
   `test_redaction_removes_raw_prompts_and_tracebacks_even_with_debug_enabled`,
   `test_journal_sanitizes_debug_paths_and_secrets`).

**Outputs:** code change, updated renderer(s) if the field is user-visible,
and redaction + rendering tests in tests/test_demo_proof.py /
tests/test_journal.py.

**Verification:** `.venv312/bin/pytest` passes; grep the rendered report
string produced in tests for `traceback`, `/Users/`, `prompt`, and known fake
secret values — none may appear; confirm `--include-debug` still gates
`debug_info` and that even debug mode never re-admits `traceback`, `raw`, or
prompt keys.

### Skill 3: MCP Boundary and Tool Contract

**When to use:** any edit to [mcp_client.py](src/rag_enterprise_langgraph/mcp_client.py),
[tool_guard.py](src/rag_enterprise_langgraph/tool_guard.py),
[graph.py](src/rag_enterprise_langgraph/graph.py), or
[config.py](src/rag_enterprise_langgraph/config.py) — connection setup, env
passthrough, tool discovery, argument normalization, or the agent system
prompt.

**Inputs:** the contract change (new tool, new tool argument, new env var,
prompt rule change) and which side owns it — if the MCP server's tool schema
itself must change, that is the MCP repo's job (escalate per §7).

**Workflow:**

1. For config/env changes: add the setting to `Settings` (env prefix
   `RAG_AGENT_`), decide whether the MCP child process needs it — if so, wire
   it through `build_mcp_server_env()` (backend vars go in
   `DEFAULT_BACKEND_ENV_KEYS` or via `RAG_AGENT_MCP_ENV_PASSTHROUGH`) — and
   update `.env.example`. Keep `diagnostic_summary()` redaction-safe for any
   new secret.
2. For tool-argument changes: extend `normalize_tool_arguments` keeping its
   guarantees — fallback question injection from the contextvar, empty-value
   cleanup, and k/k_chunks clamping with defaults 8/6. Wrapped tools must
   still return structured JSON errors instead of raising
   (`_error_payload`).
3. For prompt changes in `SYSTEM_PROMPT`: keep the rules the tests assert on
   (mentions of all three tools, "untrusted evidence",
   `expand_neighbors=true`, "no usable evidence", the no-memory-answers
   rule), and keep the prompt consistent with the orchestrator's actual
   first-pass policy (hybrid, `k_chunks=6`).
4. For connection changes: preserve stdio transport, absolute resolved paths,
   `cwd` = MCP repo, and `suppress_mcp_stdio_stderr` (it prevents child
   stderr from leaking local paths into proof runs; it monkeypatches the
   adapter locally on purpose — do not "fix" it by patching the MCP repo).
5. If a new MCP tool is expected, update `REQUIRED_MCP_TOOLS` in
   demo_proof.py and the tool inventory rendering, and decide whether the
   orchestrator should use it or only the free-form agent path.

**Outputs:** code change; updated `.env.example` and README env list when env
vars change; tests in tests/test_config.py, tests/test_mcp_client.py,
tests/test_tool_guard.py, tests/test_graph.py.

**Verification:** `.venv312/bin/pytest` passes; if the MCP server repo exists
locally and `.env` is configured, run
`PYTHONPATH=src .venv312/bin/python -m rag_enterprise_langgraph.cli
--check-config` and confirm `mcp_tool_names` lists `ask_grounded`,
`search_documents`, `get_document_excerpt` and no secret values appear in the
output; otherwise state that the live discovery check could not be run.
