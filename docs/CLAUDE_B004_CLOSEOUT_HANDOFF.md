# B004 closeout handoff for Claude

## Positioning

Position this work as a broad AI engineer's governed enterprise RAG portfolio project:
the value is not merely retrieval, but a deliberately separated system that enforces
document access in SQL, preserves citations, refuses unsupported answers, withholds
high-risk output for approval, and publishes reproducible evaluation and red-team
evidence. It is a self-built proof of concept over synthetic data, not a production or
client deployment.

## Public links and repositories

- Portfolio/evidence entry point: https://beyondalgorithms2026-source.github.io/RAG_ENTERPRISE_LANGGRAPH_APP/evaluation/
- Live governed UI: https://rag-enterprise-governance-demo.onrender.com/app
- Live data-layer API: https://rag-enterprise-starter-demo.onrender.com/docs
- APP: https://github.com/beyondalgorithms2026-source/RAG_ENTERPRISE_LANGGRAPH_APP
- STARTER: https://github.com/beyondalgorithms2026-source/RAG_ENTERPRISE_STARTER
- MCP: https://github.com/beyondalgorithms2026-source/RAG_Langgraph_MCP_server

Render services use the free tier and may need several minutes to wake. The GitHub Pages
evidence link is the always-available portfolio entry point.

## Architecture and ownership

1. **APP / LangGraph agent:** orchestration, bounded recovery, evidence validation,
   refusal and approval routing, evaluation, red-team evidence, and public governance UI.
2. **MCP integration server:** zero-runtime-dependency stdio/JSON-RPC boundary exposing
   `ask_grounded`, `search_documents`, and `get_document_excerpt`; no database access or
   authorization policy.
3. **STARTER data layer:** FastAPI, PostgreSQL/pgvector, ingestion, embeddings, hybrid
   retrieval, citations, governance, and access control composed into retrieval SQL.

APP never receives database credentials or queries STARTER/PostgreSQL directly.

## Verified feature inventory

- Hybrid governed retrieval with citation provenance and safe not-found behavior.
- SQL-level document ACL enforcement, including restricted-data denial.
- Bounded answer recovery and explicit `needs_review`/refusal outcomes.
- Approval withholding for sensitive answers; public visitors cannot approve or invoke
  operator-only evaluation/red-team execution.
- Public Documents reader backed by the access-filtered corpus endpoint.
- Public Security and Quality pages backed by committed, checksummed artifacts.
- Render Free readiness states: Waking, Ready, Degraded, and Unavailable.
- Stable public-demo seed identity using `seed_pack=public_demo` plus `source_file`.
- Hosted corpus reconciled to 28 canonical sources: 14 public, 10 internal, 4 restricted;
  221/221 chunks embedded and zero duplicate canonical identities.

## Approved claims register

- The approved v1 full-stack baseline is **25/25**, including **5/5 required refusals**.
- Access control is enforced inside retrieval SQL.
- APP, MCP, and STARTER preserve separate ownership boundaries.
- The public portfolio corpus contains 28 synthetic documents.
- Public red-team release evidence records **20/20 defended**: 18 deterministic checks
  and two live backend controls, RT-06 and RT-16.
- The public demo uses Render Free and Supabase Free; cold starts are disclosed.

## Candidate-only claims register

- One 90-case v2 candidate snapshot: **82 passed, 3 failed, 5 manual review**.
- Candidate safety outcomes: **8/8 required refusals** and **2/2 safe-boundary cases**.
- Evaluation infrastructure outcome: zero transport, grader, or other infrastructure
  failures in the published artifact.
- Candidate performance: mean 2,340.50 ms, p95 4,342.35 ms, average measured cost
  $0.000499/query; recovery-rate threshold breached. These are one-run measurements.
- Failed cases: `OM-035`, `OM-041`, `OM-089`.
- Manual-review cases: `OM-007`, `OM-066`, `OM-067`, `OM-071`, `OM-072`.

Always call v2 a **candidate snapshot, not an approved baseline**.

## Prohibited or overstated claims

- Do not claim 90/90, production readiness, production scale, client deployment, real
  users, real workload evidence, multi-tenancy, or a promoted v2 baseline.
- Do not imply deterministic tests alone prove SQL enforcement; RT-06 and RT-16 are the
  live backend controls.
- Do not call the synthetic corpus proprietary, confidential, or client data.
- Do not claim outbound agent actions execute; email, Slack, and calendar operations are
  deliberately non-dispatching.
- Do not hide the three v2 failures, five manual reviews, free-tier cold start, or the
  recovery-rate threshold breach.

## Evidence identities

- Approved v1 baseline SHA-256:
  `6e729a9e27407493cd5352bb991c506ab00bb502438016a39672e543cad6bde4`
- Candidate report SHA-256:
  `a3480e7094dd6333b607d7680380d8c8a57b941f9aab83ce72ee7a10ac2bac55`
- Candidate status SHA-256:
  `fd74d71fedd0e4a7a701f30427ab53266869e0e29fd80bbba7139e61225e86e4`
- Red-team release SHA-256:
  `39f73d75482a84a457331a84e216898568a515571f913d8773f6c4f2b66cd1f6`
- Evidence APP commit: `ec170afe82dd08dd5b74310f67059bbe9e6a6ab0`
- STARTER closeout branch head before final safety/docs commit:
  `d881b11a5462df35ff7e8a742c5833329eb5066e`
- MCP pinned local head: `3aa83780fbb715dfcc73efd7ee5101ab829c7950`
- Hosted cleanup rollback snapshot SHA-256:
  `5367068771b373ee3d109c4f783fc8472029697665309357012942f228d7faba`

Machine-readable sources are `docs/evaluation/status.json`,
`docs/evaluation/candidate-v2-report.json`, and
`docs/evaluation/red-team-release.json`. Do not replace their numbers with manually
invented totals.

## Portfolio narrative and asset order

1. Lead with the public evidence page and the business risk: unsupported answers and
   unauthorized retrieval.
2. Show the three-layer boundary diagram.
3. Show a cited grounded answer and the Documents reader.
4. Show unsupported refusal, approval withholding, and restricted-data denial.
5. Show Security evidence, then Quality with approved v1 and candidate v2 separated.
6. End with limitations and the next-step calibration plan.

Recommended Upwork themes: AI engineering, enterprise RAG, LangGraph/MCP integration,
PostgreSQL/pgvector retrieval, evaluation engineering, red teaming, access-controlled
knowledge systems, and honest evidence-based delivery. Claude may choose the marketing
voice but must not alter technical claims without returning to this register.

## Three-minute walkthrough storyboard

- 0:00–0:25 — open the evidence page; disclose synthetic data and free hosting.
- 0:25–0:50 — explain APP → MCP → STARTER and SQL-level authorization.
- 0:50–1:25 — run/show a grounded answer with citations and open its source.
- 1:25–1:55 — show unsupported refusal and restricted-data denial.
- 1:55–2:20 — show approval withholding without exposing the withheld answer.
- 2:20–2:45 — show 20 red-team checks and the two evidence modes.
- 2:45–3:00 — show v1 25/25 separately from candidate v2 82/90 and disclose limitations.

Use `docs/walkthrough-script.md` for the full recording script. Claude should order the
final screenshots as: cited Ask result, Documents reader, refusal/withholding, Security,
Quality, then mobile view.

## Deferred B005 work

- Ten-run v2 calibration and explicit baseline-promotion review.
- Correct the three genuine failed cases and adjudicate the five manual-review cases.
- Resolve the `OM-067` question/source conflict.
- Compare backend-tuned models under a hard request and spend budget.
- Deeper retrieval tuning and additional frontend polish.
- Production hosting, multi-worker/multi-tenant design, and real-user evidence are
  separate future work, not implied by B004.

## Claude responsibility

Use this handoff to prepare the Upwork profile and portfolio entry, choose the final
marketing voice, and update Upwork using Claude's existing account context. Do not alter
technical claims without returning to the evidence register. No repository investigation
should be necessary unless a public link no longer resolves.
