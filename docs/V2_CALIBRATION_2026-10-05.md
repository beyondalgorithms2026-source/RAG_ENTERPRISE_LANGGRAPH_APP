# v2 calibration — 5–6 October 2026

Status: **paused at 2 of 10 counted runs (37396288591, 37398198971). The remaining runs are
not worthwhile until run-to-run variance is reduced (see below). v2 remains unapproved.** The approved v1 baseline (25/25) is unchanged.

A run counts towards the ten-run calibration only if `validate_correction_report`
(`src/rag_enterprise_langgraph/eval_calibration.py`) accepts it:
- all 90 cases are present, with no infrastructure failures;
- all 8 refusals pass, and RT-06 passes;
- the mandatory cases **OM-044** and **OM-046** pass;
- the grader and suite versions are recorded.

## Runs

All runs were dispatched from STARTER `full-eval` on `main` and used the correction-candidate
question sets. All of them had: 8/8 refusals, RT-06 pass, 0 infrastructure failures.

| Run | Date (UTC) | APP changes since previous run | Pass / fail / review | OM-044 | OM-046 | Cost |
|---|---|---|---|---|---|---|
| 37340163820 | 5 Oct 16:21 | synthesis on; candidate sets (#41) | 72 / 9 / 9 | fail | fail | $0.0376 |
| 37340178414 | 5 Oct 16:21 | same, STARTER answer prompt pinned to 1.2.3 | 75 / 8 / 7 | fail | fail | $0.0390 |
| 37345330051 | 5 Oct 17:01 | definition lookup and row focus; synthesis 1.1.0 (#44) | 73 / 7 / 10 | review | fail | $0.0378 |
| 37348730282 | 5 Oct 17:28 | echoed `SOURCE` label (#45); question-sourced facts; rejected spans recorded (#46) | 72 / 6 / 12 | review | fail | $0.0377 |
| 37350896514 | 5 Oct 17:46 | synthesis 1.1.1; judge feedback retry; formatting normalisation (#47) | 74 / 5 / 11 | review | review | $0.0376 |
| 37394242863 | 6 Oct 00:29 | quote cleanup (#48); elided evidence quotes (#49) | 71 / 6 / 13 | review | review | $0.0377 |
| 37396288591 | 6 Oct | judge told to quote question-sourced facts from the question (#50) | 73 / 5 / 12 | review | **pass** | $0.0377 |

Seven runs cost $0.265 in total. Prompt 1.2.3 was not promoted: the cases it targets (OM-060,
OM-084) did not change, and the other differences are within run-to-run variation.

## What was wrong, and what changed

**System side.** These problems affected live visitors as well.
- Recovery quoted the wrong text for defined-term questions. It now looks up and focuses on
  the term's definition row (#44).
- Synthesis was off in the live service, which had no model configured. It is now on
  (#41, plus the owner's Render settings).
- Synthesis rejected valid answers because of a number followed by a comma, a leading "Yes",
  and an echoed `SOURCE` label. It also left a stray quote mark in some answers
  (#44, #45, #48).

**Grader side.** These were owner decisions; the grader is now at version 2.0.5.
- Facts supplied by the question may be proven from the question (#46, #50).
- Evidence quotes shortened with "..." are accepted when every piece is literal and the
  pieces fall within one table row (#49).
- The first letter's case and spacing around table pipes are formatting (#47).
- Rejected judge quotes are recorded for diagnosis (#46).

Live, after the fixes, both mandatory questions return correct, verified answers.

## Remaining blocker

**OM-046 passes** as of run 37396288591. **OM-044 still blocks every run.** Its answer has been
correct since #44: "No, a Temperature Excursion is defined as … more than 5 consecutive
minutes, and the room only read +9°C for four minutes."

The judge (`gpt-4o-mini-2024-07-18`, at temperature 0) does not quote it reliably, and each
fix moved the error somewhere else:

| Run | How the judge failed on OM-044 |
|---|---|
| 37348730282 | Joined a table term and its meaning with "..." (now accepted by #49). |
| 37394242863 | Quoted the question-sourced duration from the answer. |
| 37396288591 | Quoted the document threshold from the answer. Answer text is not evidence, so this was correctly rejected. |

## Owner decision (6 October 2026): OM-044 may count as human review

`validate_correction_report` accepts OM-044 as `manual_review` only when **both** hold:
- the judge's quotes were unverifiable;
- nothing in the answer is shown wrong: no missing or contradicted assertion, no forbidden
  fact, no hard failure, and no judge outage.

Any other OM-044 miss still blocks the run. **OM-046 has no exception.**

Every report that relies on the exception carries this remark, printed by
`scripts/check_correction_candidate.py` and stored in the baseline candidate's
`baseline_approval.remarks` by `scripts/build_eval_baseline.py`:

> OM-044 counted as human review: the answer was not shown wrong, but the gpt-4o-mini
> judge's quotes could not be verified. A better judge model is needed to grade this case
> automatically; adopting one was deferred by the owner (6 October 2026).

**Remark: a better judge model is needed and was deliberately not adopted for now.**

Under this rule, run 37396288591 is the first valid calibration run.

## Next blocker: performance thresholds

`scripts/build_eval_baseline.py` also requires every counted run to have non-breaching
performance. Every valid run so far breaches. The thresholds are candidates pending
approval, so this is an owner decision.

| Metric | Threshold | Run 37315388125 (core fix only) | Run 37396288591 |
|---|---|---|---|
| Recovery rate | 0.25 | 0.289 (breach) | 0.289 (breach) |
| p95 latency | 5,000 ms | 4,830 ms (warn) | 5,040 ms (breach) |
| Mean latency | 3,000 ms | 2,828 ms (warn) | 2,787 ms (warn) |
| Cost per query | $0.02 | $0.00042 | $0.00042 |

The recovery-rate breach predates this work: 26 of 90 questions need recovery.

## Owner decision (6 October 2026): limits set from measured values

The limits in `eval_performance.DEFAULT_THRESHOLDS` were set from the eight full-stack v2 runs,
each with a margin:

| Metric | Old | New | Measured (8 runs) |
|---|---|---|---|
| Recovery rate | 0.25 | 0.30 | 0.267–0.289 |
| p95 latency | 5,000 ms | 6,000 ms | 4,830–5,541 ms, outlier 7,224 ms |
| Mean latency | 3,000 ms | 3,500 ms | 2,787–2,986 ms, outlier 3,723 ms |
| Cost per query | $0.02 | $0.02 | $0.00042 |

The outlier run (one 26.5 s request) still breaches, as intended. Counted run 1
(37396288591) had its performance summary recomputed with `scripts/attach_eval_performance.py`
from its unchanged measurements and usage. It is now `warn`; only the `performance` block
changed. The nine remaining counted runs use the new limits from the start.

## Counted-run batch 1 (6 October 2026)

Three runs with the new limits ($0.113):

| Run | Pass / fail / review | Result |
|---|---|---|
| 37398198971 | 76 / 5 / 9 | **counted** (performance within limits) |
| 37398207991 | 73 / 5 / 12 | not counted: OM-046 |
| 37398216341 | 73 / 5 / 12 | not counted: OM-046 |

In both rejected runs, OM-046 was a **real answer miss**, not a judge problem. The synthesized
answer left out the question's €260,000 ("…because the financial exposure is above
€250,000"), so the required exposure fact is missing.

**Why calibration paused here.** `scripts/build_eval_baseline.py` requires each case to have
the same outcome in at least 90% of the counted runs. Across the four runs with the same
configuration (37396288591 and batch 1), **8 cases already disagree**:

| Case | Outcomes |
|---|---|
| OM-015 | 2 pass, 2 review |
| OM-031 | 2 pass, 2 review |
| OM-033 | 2 fail, 2 review |
| OM-046 | 2 pass, 2 fail |
| OM-008 | 3 review, 1 pass |
| OM-040 | 3 pass, 1 review |
| OM-068 | 3 fail, 1 pass |
| OM-085 | 3 review, 1 fail |

About one run in three is valid. Reaching ten would take roughly 24 more runs (about
$0.90), and the baseline would still very likely fail the stability check. Reducing
run-to-run variance comes first: answer wording, judge quoting on OM-015 and OM-031, and
recovery on OM-033 and OM-068.
