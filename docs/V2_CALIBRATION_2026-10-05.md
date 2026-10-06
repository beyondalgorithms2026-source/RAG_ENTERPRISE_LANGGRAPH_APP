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

Six runs cost $0.227 in total. Prompt 1.2.3 was not promoted: the cases it targets (OM-060,
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

The answers to OM-044 and OM-046 are correct, but the judge (`gpt-4o-mini-2024-07-18`, at
temperature 0) does not reliably quote them literally:

- **OM-044.** In run 37394242863 the judge quoted the question-sourced duration from the
  answer instead of the question. #50 now states that rule in the judge prompt; this has
  not yet been measured.
- **OM-046.** The judge paraphrases the answer ("exposure is €260,000" where the answer says
  "exposure of €260,000") on every attempt, despite the retry feedback.

## Next

1. Run one confirmation run with #50 (about $0.04) once the OpenAI budget allows.
2. If OM-046 is still blocked only by the judge's paraphrase, decide between:
   - a stronger judge model, which changes the grading setup and costs more per run; or
   - accepting human review for that case in the counted runs, which requires changing the
     mandatory rule.
3. Then run the ten counted runs (about $0.38).
