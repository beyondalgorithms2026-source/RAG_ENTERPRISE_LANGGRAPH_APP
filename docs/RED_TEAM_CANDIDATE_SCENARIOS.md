# Red-team candidate scenarios

Potential scenarios remain quarantined here until they have a concrete adversarial
input, a named production control, an honest test type, and an expected safe outcome.
They never enter the blocking suite automatically.

| Candidate | Risk to explore | Promotion requirement |
|---|---|---|
| Unicode confusable injection variants | Attack wording disguised with mixed scripts or invisible characters. | Add normalization/control evidence without blocking ordinary multilingual questions. |
| Oversized nested filter payloads | Parser or transport resource exhaustion. | Prove limits at APP, MCP, and STARTER boundaries with compatible errors. |
| Citation-locator poisoning | Retrieved metadata tries to inject markup or unsafe links. | Add public rendering sanitization and a production-path rendering test. |
| Recovery-loop amplification | Crafted evidence repeatedly triggers expensive recovery. | Prove bounded attempts plus P19 cost/recovery behavior. |
| Cross-case state contamination | One eval query influences a later query in a reused process. | Reproduce state leakage and prove per-case isolation. |

Rejected or promoted candidates must be recorded here or in `EVAL_GROWTH_LOG.md` with
the reason and linked verification.
