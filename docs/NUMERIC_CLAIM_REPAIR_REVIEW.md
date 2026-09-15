# Structured numeric-claim repair — approved implementation candidate

Status: owner approved implementation on 15 September 2026. The bounded STARTER
implementation is opt-in; see its [implementation and verification record](https://github.com/beyondalgorithms2026-source/RAG_ENTERPRISE_STARTER/blob/codex/eval-correction/docs/NUMERIC_CLAIM_REPAIR.md).
The context/prompt and numeric-repair candidates remain disabled
by default and is not release-ready. Do not change models or add dependencies to
work around this failure.

## Observed failure

In repeated real STARTER-only runs, OM-044 answered Yes to +9°C for four minutes.
After retrieval selection was corrected, the selected context included the
governing definition: an excursion outside 2–8°C for **more than five consecutive
minutes**. The generated answer still incorrectly treated four as exceeding five.
This is an answer-synthesis error, not an acceptable paraphrase or grading issue.
OM-046's supplied exposure/threshold comparison was correct in the candidate
diagnostics; it still requires repeated full-stack verification.

OM-089 now receives Section 5.5.1 in model context, but generation can omit it
from the requested governing-section list. Better retrieval is necessary but
does not prove complete answers.

## Bounded design for separate review

1. Use the existing provider's structured output for threshold questions only.
   Extract claims into an explicit schema: source citation, quoted threshold,
   value, unit, comparator, supplied observation and proposed conclusion.
2. Validate units and numeric comparisons with Decimal arithmetic against the
   cited controlled evidence. Do not extract arbitrary prose into a universal
   arithmetic parser; unsupported extraction must be uncertain, not invented.
3. On a demonstrated contradiction, permit at most one repair using the existing
   bounded repair mechanism, or return a review/refusal outcome. A repair must
   not bypass evidence, ACL, citation, redaction or refusal validators.
4. Never use evaluation IDs or reference answers in production. Restrict the
   mechanism using question/claim structure, not this case's wording.
5. Preserve compatible public responses. Measure extra calls, tokens, cost and
   p95 latency; explicitly review the plan's 15%/20% limits before activation.

## Required tests and acceptance

- Four minutes versus more than five: false; exactly five: false; six: true,
  with the other triggering conditions present.
- Inclusive and exclusive financial bounds; €260,000 versus €250,000; nearby
  decimals, conflicting units, missing evidence and malformed structured claims.
- Correct numbers plus a wrong conclusion must fail validation.
- Injection in reference text, unavailable provider, timeout, repair exhaustion,
  and no disclosure of internal claims/prompts or restricted provenance.
- No extra call on ordinary questions; a bounded documented maximum for repairs.
- OM-044 and OM-046 must pass every counted calibration run. Until then, stop
  calibration, preserve the v1 gate and do not promote the revised baseline.

Implementation approval does not approve activation or a revised baseline.
Targeted live checks returned No at four and exactly five minutes, Yes at six
minutes, and Yes for €260,000 exceeding €250,000. These are STARTER-only
diagnostics, not calibrated full-stack scores. Canonical concept grading and
classification coverage still require verification, as does the matched latency
and token comparison. Preserve the approved v1 gate until release criteria pass.
