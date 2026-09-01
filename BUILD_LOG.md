# B004 Evidence Pack — Build Log

This log lives in the RAG_ENTERPRISE_LANGGRAPH_APP repository (portfolio asset P1)
because it is the hub of the three-repository system and the only place a daily
commit can satisfy the B004 working rules. It covers all three repositories.

Working branch: b004/evidence-pack (all three repos)
Safety tag: pre-b004 (all three repos)
Visibility: PRIVATE. All three go public at the end of D6, on approval only.
Licence decision: Apache-2.0
Cadence: 6h/day from Tue 1 Sep 2026
B004-MIN: 6 days, 36h, baseline Sat 6 Sep
B004 FULL: 11 days, 66h, baseline Fri 12 Sep
Public URLs: none yet

## Repos

- [x] A. Starter backend (P2) — `RAG_ENTERPRISE_STARTER`, default `master`, branch created, tag created
- [x] B. LangGraph app (P1) — `RAG_ENTERPRISE_LANGGRAPH_APP`, default `main`, branch created, tag created
- [x] C. MCP server — `RAG_ENTERPRISE_MCP_SERVER`, default `master`, in git, branch created, tag created

A fourth repository, `RAG_ENTERPRISE_PRIVATE_ASSETS`, exists as a private off-machine
backup of gitignored files (`.env` files, `data/uploads/`, `runs/`, the eval workbook).
It is **permanently out of B004 scope and must never be made public.**

## Days

- [ ] D1 Tue 1 Sep — branches, MCP into git, JWT history purge, secret defaults
- [ ] D2 Wed 2 Sep — paths, config, langchain-ollama, clean-clone run, corpus start
- [ ] D3 Thu 3 Sep — corpus done, evidence.py fix, evals re-run   <-- GATE
- [ ] D4 Fri 4 Sep — starter skip guards, cleanup, LICENSE x3
- [ ] D5 Sat 5 Sep — red-team wording, CI + badge, evals page, GitHub Pages
- [ ] D6 Sun 6 Sep — READMEs, capability matrix, go/no-go, PUBLIC  <-- MIN COMPLETE
- [ ] D7 Mon 8 Sep — buffer / docs polish
- [ ] D8 Tue 9 Sep — provider abstraction, corpus trim, hosted pgvector
- [ ] D9 Wed 10 Sep — deploy backend
- [ ] D10 Thu 11 Sep — deploy front end
- [ ] D11 Fri 12 Sep — walkthrough

## Verified facts — correct these against reality, never the reverse

- App tests: 109, all offline (audit-verified, `pytest --collect-only` and full run, 2.08s)
- Starter tests: 354-357 claimed, 26 files DB-bound. Offline-passing count: `<D4>`
- Red team: 10 scenarios, 9 defended, 0 failed, 1 requires_backend by design
- Eval numbers after the evidence.py fix: `<D3 — whatever they turn out to be>`
- All four GitHub repositories are PRIVATE as of D1 (verified via `gh repo list`)

## Rotated credentials

- [ ] 3 JWTs purged from history (D1)
- [ ] 3 JWTs invalidated by nulling `DEV_LOCAL_JWT_SECRET` (D1) — see note below
- [ ] 2 secret-key defaults nulled and made required (D1)

Note on "rotation": the three tokens are HS256, issuer `rag-enterprise-local-dev`,
already expired, and signed with `DEV_LOCAL_JWT_SECRET` — whose value is a default in
this codebase, not a credential held by any external service. There is no provider
console to rotate at. Removing the default (D1) is what invalidates them: after that,
no instance can mint or verify a token with the old key.

## Day log

### D1 — Tue 1 Sep 2026

**Done**

- Read `docs/AUDIT_REPORT.md` in full; confirmed its blocking findings against the
  live repositories rather than taking them on trust.
- Verified Rule 0 was completed in a prior thread on all three repos: clean trees,
  `pre-b004` tags, `b004/evidence-pack` branches checked out. Not repeated.
- Deleted remote branch `origin/RAG_enterprise_dev` on the starter after verifying it
  held zero commits unreachable from a local branch. It carried the JWT blob and
  existed only on the remote, which would have defeated a local-only history purge.
- Added `.gitignore` to the MCP server and untracked 10 `__pycache__/*.pyc` files that
  the verbatim `pre-b004` commit had captured. Commit `b501c30`.
- Created this build log.

**Found / decided**

- The starter's `master` is stale: 94 commits behind `b004/evidence-pack`, with 1
  commit of its own not present on it, and local `master` (`aa5622c`) has diverged
  from remote `master` (`3eebbf0`). The real line of work runs through
  `experimental-fable-ui-v2`, which is what `pre-b004` and `b004/evidence-pack` point
  at. **The D6 instruction "merge to the default branch" is therefore not yet a
  well-defined operation for the starter.** Open decision — see blockers.

**Broke**

- Nothing.

**Hours**

- (running)

**Commit**

- MCP: `b501c30`

## Open blockers

1. **git-filter-repo is not installed.** Needed for the JWT history purge. Awaiting
   approval to install (one-off developer tool, not a runtime dependency).
2. **Starter default-branch resolution for D6.** `master` has diverged from the line
   of work B004 sits on. Needs a decision before D6, not before D1.
3. **MCP server: submodule of the app repo, or standalone repository?** Currently
   standalone at `github.com/beyondalgorithms2026-source/RAG_Langgraph_MCP_server`.
   Decision needed on D1.
