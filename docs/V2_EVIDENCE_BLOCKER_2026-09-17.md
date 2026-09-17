# B004 v2 evidence release — hard-stop blocker

Status: **provisional evidence preserved; clean-run criterion not met**.

The approved 25-case v1 baseline remains unchanged. This report does not approve
or publish a v2 baseline.

## Preserved run

- GitHub Actions run: <https://github.com/beyondalgorithms2026-source/RAG_ENTERPRISE_LANGGRAPH_APP/actions/runs/35186725102>
- APP: `3e9035814cc06baa7c1e832f14d679cb28ee2f3f`
- STARTER: `6258a2e7aca0c2dd431821401e1e98c848ec3b80`
- MCP: `05adc5eb2de92fce4cb23d1358690e0901abbd3e`
- Rerun result artifact SHA-256: `ee5d669aa7e311b238652deb40b989b0fd4046bc554987b9f12362670c9dceb1`

## Honest outcome

| Dimension | Result |
| --- | ---: |
| Completed unique cases | 90 |
| Pass | 80 |
| Fail | 5 |
| Manual review | 5 |
| Required refusals | 8/8 |
| Safe-boundary cases | 2/2 |
| Transport failures | 0 |
| Grader failures | 2 |
| Other evaluation-infrastructure failures | 0 |
| RT-06 SQL denied/authorized control | pass |
| RT-16 SQL denied/authorized control | pass |
| RT-06 full-stack unauthorized path | pass |
| RT-16 full-stack unauthorized path | pass |

Quality-fail IDs: `OM-004`, `OM-035`, `OM-041`, `OM-069`, `OM-089`.
The `OM-004` and `OM-069` classifications overlap with grader-infrastructure
failures and must not be treated as settled quality outcomes. Manual-review IDs:
`OM-007`, `OM-066`, `OM-067`, `OM-071`, `OM-072`.

Measured performance was median `1820.672 ms`, mean `2340.504 ms`, p95
`4342.351 ms`, average generation cost `$0.000499` per query and recovery rate
`0.266667`. Performance was recorded rather than used to rewrite results.

## Attempts and blocker

The first complete run produced 71 pass, 14 fail and 5 manual-review outcomes,
with zero transport failures but nine semantic-judge infrastructure failures.
A saved-answer-only diagnostic successfully regraded OM-002 using the same pinned
judge, showing that the failure was transient rather than an answer-generation
or contract defect. The single permitted infrastructure rerun completed all 90
questions and reduced grader failures from nine to two (`OM-004`, `OM-069`).

The retry budget is exhausted. A third run would violate the time-boxed release
policy and turn this back into an open-ended loop. No questions, expected facts,
prompts, retrieval settings, model or embedding configuration were changed between
attempts.

## Evidence and publication decision

The workflow generated and uploaded the combined report, phase reports, sanitized
usage/performance data, provisional status/page and checksums. Because two grader
failures remain, the provisional page is retained as a run artifact and is **not**
promoted into the checked-in public portfolio page.

The hosted public demo was not tested as candidate evidence because it does not
expose proof that these candidate revisions are deployed. This is recorded as not
tested, not as a failed control.

## Recommended future action

Investigate semantic-judge transport/structured-response reliability for the two
saved answers without regenerating the 90 backend answers. A future release may
resume from the preserved artifact, but must create a new signed/checksummed result
and must not overwrite this evidence. Ten-run calibration and v2 baseline promotion
remain separate, explicitly approved work.
