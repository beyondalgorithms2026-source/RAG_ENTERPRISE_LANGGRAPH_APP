# Evaluation guide

The checked-in Northwind set contains 25 stable cases: 20 answerable questions and five
questions the corpus cannot answer. P12 tests the harness with fakes; it does not measure
live retrieval. P12B runs the real APP → MCP → STARTER → PostgreSQL/pgvector stack.

## Run locally

With all three repositories and the backend configured:

```bash
rag-enterprise-agent \
  --eval-set config/eval-set-northwind.json \
  --eval-output runs/eval.md \
  --eval-json runs/eval.json
```

`--eval-xlsx` remains available for legacy workbooks. New checked-in sets must use JSON
schema `1.0`, unique permanent `case_id` values, and explicit `expect_refusal` values.
Answerable cases require a document and fact; refusal cases require both to be null.

## Interpret results

- `pass`: a supported answer matched the expected fact, or a must-refuse case declined.
- `manual_review`: evidence or answer quality was partial.
- `fail`: the expected fact/refusal requirement was not met.
- `failure_class=infrastructure`: auth, timeout, or tool transport prevented measurement.

Infrastructure failures are not quality scores and fail P12B distinctly. The report also
records whether the expected document appeared in citations/evidence and the active APP
prompt versions and hashes.

## Grow the set

Add a permanent case when fixing a retrieval, grounding, refusal, evidence, or schema
defect. Reproduce the failure first, choose the next stable ID, and review the expected
fact against the synthetic source rather than against model output. Never delete or reuse
an ID to hide a regression.

## Baseline governance

P12B compares cases and aggregates; it is not an exact-answer string comparison. All
must-refuse cases, infrastructure failures, prior passes, and prior expected-document
matches are hard controls. CI never writes the approved baseline. A candidate baseline
comes from the documented calibration runs and is promoted only in an explicit,
justified, owner-reviewed pull request.
