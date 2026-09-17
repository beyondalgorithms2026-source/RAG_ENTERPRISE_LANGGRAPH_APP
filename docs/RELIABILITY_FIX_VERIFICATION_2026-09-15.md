# Reliability and grader fixes — diagnostic verification

This is not baseline approval, calibration or a production deployment.
Historical v1 evaluation data/baseline is unchanged. MCP source is unchanged.
Supabase/OpenAI were used online; no Docker, corpus provisioning, migrations,
ACL changes, model/embedding swaps or new dependencies were used.

## Implemented

- Grader 2.0.1: source-scoped factual quotes, no table-header evidence, mandatory
  explanations, atomic validation and unique judge request-schema fields.
- Missing grounded answers fail quality without semantic judge calls, including
  saved-answer regrading. Infrastructure failures remain separate.
- Optional typed concept `answer_anchors` groups protect required material
  conditions against reference-only false positives. Missing protected anchors
  cannot be overridden by a judge. Core candidate/suite is 2.1.3; manual pack
  remains 2.1.2. NW-015 now protects the open-investigation condition.
- APP recovery preserves complete bounded procedures/prohibitions. Opening
  auxiliary verbs cannot collapse recovery to searches such as just "Are".
- STARTER context selection suppresses authorized duplicate copies and irrelevant
  administrative/title snippets; history and governing-definition evidence are
  prioritized for relevant questions. Existing authorization and budgets remain.
- Immutable STARTER candidate prompt 1.2.2; registered 1.2.1 history remains.
  Numeric repair/context selection/candidate prompts remain default-on.

## Online diagnostic outcome

Seventeen selected cases ran through real APP → MCP → STARTER against the existing
83-source shared corpus. The initial process loaded the malformed judge schema:
core had two judge infrastructure failures and manual had seven. Corrected offline
regrading of the saved answers produced **zero judge infrastructure failures**.
No answers were regenerated for that regrade.

The manual regrade reported seven answer-contract passes out of twelve:
OM-032, OM-044, OM-056, OM-059, OM-066, OM-068, OM-085. These are diagnostic
answer grades, not full-stack baseline scores or human-approved judgements.
OM-066 and OM-068 retained complete procedure/prohibition evidence in recovery.

Core regrading also exposed a false pass for NW-015: "90 days" was wrongly
treated as expressing its omitted open-investigation exception. The later
2.1.3 contract guard rejects this answer deterministically. Missing-answer
saved grades NW-012/NW-014 were subsequently corrected from manual review to
quality failure. Preserve original reports; do not reuse their raw pass counts.

Four additional STARTER-only requests captured actual model context. OM-042
answered 20:00 from the four-hour definition; OM-046 answered Yes, EUR 260,000
exceeds EUR 250,000. Both had failed the mixed-corpus full-stack attempt, so these
single successful scoped checks are not evidence of every-run stability.

| Remaining case | Evidence-backed finding | Next action |
| --- | --- | --- |
| NW-012/NW-014 | Shared-corpus path returns missing policy answers. | Inspect intended legacy-corpus retrieval; do not relax expected facts. |
| NW-015 | Answer omits material investigation exception; judge false positive now guarded. | Improve exception synthesis, verify sourced completeness. |
| NW-016 | Legacy policy requires Finance Director; Manual v3.2 permits Band 4–5 up to EUR 28,600. | Restore intended evaluation corpus scope or approve explicit precedence; do not hardcode an authority. |
| NW-017 | Still nonpassing in saved core regrade. | Inspect evidence, controlled boundary and answer before proposing a fix. |
| OM-035 | STARTER has calibration evidence and the explicit Section 4.3.5 cross-reference, but says Section 4.2.4. Full-stack attempt produced no grounded answer. | Address source-identifier synthesis and scope-dependent retrieval; preserve exact required section. |
| OM-041 | Recovery returns a Working Day holiday example, losing the elapsed-hour deadline. | Prevent relevant-looking but incomplete recovery from replacing the deadline answer; verify requested clock deadline. |
| OM-042/OM-046 | Scoped STARTER answers correct; shared full-stack attempts fail or are incomplete. | Trace corpus/candidate differences and repeat targeted controls after correction. |
| OM-089 | Actual selected STARTER context includes 5.5.1, 6.3 and 6.4; generated answer omits 5.5.1. | This is synthesis incompleteness, not evidence absent from context. Improve component coverage without an unsafe automatic section-list appender. |

Do not add case-specific runtime answers, silently alter questions, or accept
aggregate improvement as proof that these failures are fixed.

## Verification

- APP pytest: **239 passed**; changed-code Ruff lint/format passes.
- MCP pytest: **39 passed**, runtime/source unchanged.
- STARTER offline discovery: **117 cases, 81 passed, 36 skipped** using an
  explicitly unreachable offline database and blank model credentials.
- STARTER reader-clarity: **21 passed**; repository hygiene passes.
- STARTER scenario validation: **9 passed, 2 skipped**.
- APP offline red-team: **18 defended, 2 require backend, 0 failed**; this run
  does not claim a fresh live SQL ACL test.
- A first offline invocation used an unavailable psycopg dialect and failed
  import; rerun with the existing psycopg2 dialect passed. No dependency added.
- Changes are local/uncommitted. CI has not been run for this patch. Existing
  unrelated APP UI and STARTER main edits are preserved; their previously observed
  whole-tree lint/format issues are not silently repaired or attributed here.

Sanitized online artifacts are under STARTER
`data/reports/targeted-reliability-fixes-2026-09-15/` (ignored generated reports).
API diagnostic subprocesses terminated normally. No baseline was overwritten.

## Still pending

Remaining genuine failures, controlled cloud-corpus isolation, historical v1
baseline metadata reconciliation, performance comparison, full-suite verification,
CI and ten-run calibration/explicit baseline review. V2 remains advisory.
