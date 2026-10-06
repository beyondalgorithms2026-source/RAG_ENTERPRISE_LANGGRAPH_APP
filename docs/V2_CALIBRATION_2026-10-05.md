# v2 calibration — 5–6 October 2026

Status: **paused; no counted run yet. v2 remains unapproved.** The approved v1 baseline
(25/25) is unchanged.

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

## Next

The remaining options are both owner decisions:

1. **A stronger judge model** for concept grading. This changes the grading setup and costs
   more per run; it needs one confirmation run before the ten counted runs.
2. **Accept human review for OM-044** in counted runs. This changes the mandatory rule in
   `validate_correction_report`.

Either way, the ten counted runs cost about $0.38 at current per-run cost.
