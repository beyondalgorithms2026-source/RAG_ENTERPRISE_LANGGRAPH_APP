# Evaluation correction — candidate implementation and verification

Status: work in progress. The approved 25-case v1 gate remains unchanged. No
revised baseline has been approved, and the candidate is not a production release.

## Source-contract corrections

- OM-072 uses the **seven** ordered escalation-call points in Section 3.4.3,
  as explicitly approved by the owner. The previously proposed ten conflated
  other reporting requirements with the escalation call.
- The Temperature Excursion definition requires **more than five consecutive
  minutes**, not at least five. Numeric comparator checks retain this distinction.
- OM-039 checks the section through citation metadata rather than requiring the
  section number in answer prose.
- OM-041 and OM-085 concern elapsed-hour reporting deadlines; local-holiday
  wording must not introduce an unrelated Working Day requirement.
- Clarified questions request the certification and assignment conditions
  (OM-045), the four budget-tier components (OM-060), and the source-defined call
  points (OM-072).

The candidate packs preserve 25 Northwind and 65 manual IDs (90 total), with
five original Northwind refusals and three manual refusals. All assertions are
source-linked in `EVALUATION_CORRECTION_CONTRACTS.md`; owner review remains
required. OM-067 has a question/source timing conflict pending clarification.

## Frozen diagnostic evidence

`tests/fixtures/starter_manual_diagnostic_36.json` preserves 36 public-synthetic,
STARTER-only answers, citations and original required facts. Missing retrieval
traces and prompt identifiers are explicitly recorded as unavailable, not invented.

| Check | Answer/fact matches |
| --- | ---: |
| Historical temporary substring checker | 23/36 |
| Original canonical APP grader, answer-side checks | 24/36 |

The difference is OM-071 punctuation handling. Neither number is an approved
benchmark score: saved snippets are insufficient to reproduce full grounding,
and the outputs did not traverse APP and MCP. Revised semantic adjudication and
human-labelled comparison remain pending.

## Candidate implementation

APP adds backward-compatible schema 1.2, typed checks, decimal/unit/comparator
handling, identifier boundaries, concept adjudication and structured judge
failure classification. The judge is evaluation-only, uses the pinned existing
OpenAI model, and cannot override deterministic hard failures. Judge support
must include literal answer and controlled-reference spans. Legacy packs and
the v1 baseline are not overwritten.

STARTER adds opt-in candidate context selection and an immutable candidate
answer prompt. Both flags default to false:

- `ANSWER_CONTEXT_SELECTION_ENABLED`
- `ANSWER_PROMPT_CANDIDATE`

Candidate selection only consumes already-authorized retrieval results. It
widenes compound questions to ten candidates, bounds selected context, suppresses
duplicates and records selection/budget decisions. There is no extra production
model call. The 4,000-character cap is a test candidate, not a changed global
default. SQL authorization is unchanged. MCP is unchanged.

## Verification recorded on 2026-09-15

| Check | Result |
| --- | --- |
| APP complete pytest suite | 220 passed |
| STARTER complete unittest discovery | 93 discovered: 57 passed, 36 skipped |
| New STARTER candidate mechanism/protocol tests | 11 passed |
| STARTER reader-clarity checks | 21 passed |
| STARTER repository hygiene | Passed |
| Ruff on changed evaluator/candidate files | Passed after formatting |
| Cross-repository contract comparison | Compatible |
| APP deterministic red-team | 18 defended, 2 require backend, 0 failed |
| Real STARTER RT-06/RT-16 production SQL ACL controls | 2 passed in isolated Docker database |
| Revised questions, current STARTER candidate configuration | 36 real answers saved |
| Revised questions, opt-in STARTER context/prompt changes | 36 real answers saved |
| Full candidate STARTER suite | 25 + 65 real answers saved |

Skipped STARTER tests must not be represented as live database/security proof.
The explicitly reported SQL controls are separate real-database tests. An initial
SQL test invocation used the wrong working directory and failed import; the
correct backend-directory invocation passed both tests.

The live runs used the pinned OpenAI model, existing embedding configuration,
and disposable localhost databases named `b004_eval_*`. Supabase was not accessed
or migrated. Full-suite answer generation completed without infrastructure errors.
These are STARTER-only reports, not P12B or approved benchmark results.

Saved reports are under `/private/tmp/b004-eval-correction-20260915`. Temporary
files are not durable release artifacts; export sanitized reports before cleanup.

### Measured 36-question performance comparison

| Metric | Current | Candidate |
| --- | ---: | ---: |
| p95 end-to-end latency | 4,526 ms | 3,171 ms |
| Average input tokens | 2,379 | 2,504 |
| Average generation calls | 1.028 | 1.028 |

This sample showed -29.95% p95 latency and +5.26% input tokens, within candidate
review limits. It is not a calibrated production promise and does not establish
answer correctness. Offline judge calls/cost are excluded.

### Confirmed blockers

- OM-030's emergency exception reaches context and was correctly answered in
  the targeted candidate check.
- OM-089's Section 5.5.1 reaches context after selection changes, but answers can
  still omit that governing section. Retrieval improvement is not complete synthesis.
- OM-044 repeatedly gives the wrong four-versus-more-than-five-minute conclusion
  even with the governing definition present. Candidate release and calibration
  are blocked. `NUMERIC_CLAIM_REPAIR_REVIEW.md` proposes a separately approved
  bounded structured-claim design; it is not implemented.
- OM-046 was correct in targeted checks but omitted the required threshold in
  the 36-case answer. It has not met the every-run acceptance condition.
- The initial offline judge invented nonliteral table-header/cell quotes and
  occasionally unknown assertion IDs. These are evaluation infrastructure errors,
  not quality scores. The revised output schema constrains IDs and quotes to
  actual supplied evidence; regression tests cover this failure.
- The full 25-case STARTER candidate answer-side regrade passed 25/25 under the
  preceding judge revision. This does not prove APP grounding or replace v1.

Unrelated existing APP `ui.py` formatting and STARTER `main.py` duplicate-import
lint issues remain in the user's working tree. They are excluded from this work;
whole-tree verification must distinguish them from changed-file results.

## Outstanding release work

1. Complete owner source-contract review of the all-90 ledger, resolve OM-067,
   and produce the independently human-labelled frozen-answer comparison.
2. Finish final all-90 offline grading under the constrained judge; report
   quality failures separately from infrastructure failures. APP actual-context
   coverage remains unavailable unless explicitly instrumented, never inferred.
3. Obtain approval for the additional structured-claim/repair design and solve
   genuine numeric and multi-section synthesis failures before release.
4. Archive sanitized full reports durably and complete the attribution table
   distinguishing question/grader improvements from backend improvements.
5. Extend controlled performance verification if the separately approved repair
   introduces extra calls; the current single comparison is insufficient for
   production latency guarantees.
6. Deliver evaluator and opt-in backend changes in separate review branches;
   verify repository CI and real full-stack P12B. Live SQL controls, offline
   red-team and contracts already passed in this increment, but full-stack
   authorization and answer quality are not established by those checks.
7. Collect ten successful full-stack calibration runs; require refusals, RT-06,
   OM-044 and OM-046 in every counted run. Require other classifications stable
   in at least nine runs; investigate/extend to fifteen when necessary.
8. Promote a new baseline
   through an explicit owner-reviewed PR. Do not activate revised blocking checks
   before approval.

Existing unrelated frontend/main changes in the working trees are preserved and
must not be included accidentally in evaluator/backend delivery commits.
