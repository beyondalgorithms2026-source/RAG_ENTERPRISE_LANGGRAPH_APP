# Evaluation growth log

This append-only log records reviewed changes to the active quality suites. User
feedback, mined questions, and candidate cases remain quarantined until a contributor
documents the source truth and promotes them through review.

| Date | Change | Evidence and governance state |
|---|---|---|
| 2026-08-29 | Established schema 1.0 Northwind set with 25 cases. | Approved v1 baseline contains 20 answerable cases and five strict refusals. |
| 2026-09-13 | Added schema 1.1 and curated Operations Manual set with 65 cases. | 60 answer cases, three strict refusals, and two safe-boundary cases; awaiting live calibration and v2 approval. |
| 2026-09-13 | Declared two isolated phases and a 90-case combined report. | Legacy 27-source core phase remains isolated from the source-28 manual phase. |
| 2026-09-13 | Added P19 performance fields and thresholds. | Local deterministic tests pass; live cost/latency calibration remains pending. |
| 2026-09-13 | Expanded red-team inventory from RT-01–10 to RT-01–20. | Eighteen deterministic mechanisms pass offline; RT-06 and RT-16 require live SQL proof. |

No entry in this file is evidence of a live pass by itself. The sanitized workflow
artifacts, approved baseline, and named CI checks are authoritative.
