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

- [x] 3 JWTs purged from the starter's local history (D1) — 73 of 101 commits carried
      the file; 0 occurrences remain across all refs
- [ ] Purged history force-pushed to origin — **awaiting approval**
- [x] 3 JWTs invalidated by nulling `DEV_LOCAL_JWT_SECRET` (D1) — see note below
- [x] 4 secret defaults nulled and made required (D1, commit `d0a813e`) —
      `AUTH_STATE_SIGNING_SECRET`, `DEV_LOCAL_JWT_SECRET`, `DEV_TEST_USER_PASSWORD`,
      `DEV_TEST_ADMIN_PASSWORD`

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

- Installed `git-filter-repo` (Homebrew, `/opt/homebrew/bin/git-filter-repo`). One-off
  developer tool; it is not a dependency of any published package.
- **Private assets repo cleaned.** Removed 8 Acquired podcast transcripts, 16 third-party
  academic PDFs and the derived `acquired-qa-evaluation.xlsx` from
  `RAG_ENTERPRISE_PRIVATE_ASSETS` and its history, then force-pushed. All 25 files were
  verified to exist in the local working corpus before removal. Correction to an earlier
  assumption: the 3 personal billing documents were **never** in that repo — the prior
  thread had already excluded them. README updated to say the repo is no longer a backup
  for the removed files. Commits `bfe211c` (rewritten capture), `e894b0d`.
- **JWT purge on the starter, locally.** Removed
  `docs/additional test user_Detail_Token.txt` from all refs with `git-filter-repo`.
  It was in the tree of 73 of 101 commits. After the rewrite: 101 commits, 82 tags and
  7 branches preserved; 0 occurrences of the file and 0 matches for a JWT header pattern
  across every commit in the repository. **Not yet force-pushed.**
- **Secret defaults removed** (`d0a813e`). Four values that carried working defaults in
  `backend/app/core/config.py` now default to empty, and `validate_security_posture()`
  raises a named, actionable error in *any* environment when a mode that needs them finds
  them unset. `backend/.env.example` documents all four and how to generate them. The
  pre-existing staging/prod weak-secret checks were left intact.

**Found / decided**

- Before rewriting, `origin/master` on the starter turned out to be 1 commit **ahead** of
  local `master`, not diverged. Fast-forwarded local `master` first so that commit was
  carried through the rewrite rather than destroyed by a later force-push.
- MCP server stays a **standalone repository**, not a submodule — provisional, pending
  confirmation. Submodules produce empty-directory confusion for anyone cloning, and
  three separate public repos make the three-layer security boundary legible from the
  repository list alone.

**Broke**

- Nothing.

**Not done / carried to D2**

- Force-push of the purged starter history (needs approval).
- The starter's backend test suite could not be run to check the secret-default change:
  it requires a live migrated Postgres and has no skip guards. That is the D4 item.

**Hours**

- ~3h of 6h

**Commits**

- MCP: `b501c30` (.gitignore, untrack bytecode)
- App: `f13b883` (build log)
- Starter: `d0a813e` (secret defaults) — on rewritten history
- Assets: `e894b0d` (copyright removal record)

## Open blockers

1. **Force-push of the purged starter history to origin.** The rewrite is done locally
   and verified. GitHub still holds the old history until it is overwritten. Awaiting
   approval — this rewrites 6 remote branches and 82 tags.
2. **Starter default-branch resolution for D6.** `master` is 94 commits behind the line
   B004 sits on (which runs through `experimental-fable-ui-v2`). "Merge to the default
   branch" is not yet a well-defined operation there. Needs a decision before D6.
3. **GitHub retains unreachable objects after a force-push** until it garbage-collects,
   on a schedule you do not control. Fully removing them requires deleting and recreating
   the repository, which needs a `delete_repo` token scope the current `gh` login does not
   have. Applies to both the starter and the assets repo.
