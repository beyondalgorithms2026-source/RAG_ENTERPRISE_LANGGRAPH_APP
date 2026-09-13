# Evaluation guide

The governed Northwind suite has two isolated full-stack phases. The original schema
1.0 phase runs 25 cases against the legacy 27-source corpus. The schema 1.1 Operations
Manual phase runs 65 cases after the public manual is added as source 28 under document
ACL. Together they form 90 cases: 80 ordinary answers, eight strict refusals, and two
safe-boundary answers. RT-06 and RT-16 remain separate live SQL authorization controls.

P12 is the fast fake-driven harness smoke test; it does not measure live retrieval,
SQL authorization, model quality, or performance. P12B runs the real
APP → MCP → STARTER → PostgreSQL/pgvector stack with the pinned OpenAI configuration.

## Run locally

Generate and seed the applicable STARTER corpus, start STARTER, and point MCP at it.
Then run an individual phase:

```bash
rag-enterprise-agent \
  --eval-set config/eval-set-northwind.json \
  --eval-output runs/core-eval.md \
  --eval-json runs/core-eval.json

rag-enterprise-agent \
  --eval-set config/eval-set-operations-manual-v3.2.json \
  --eval-output runs/manual-eval.md \
  --eval-json runs/manual-eval.json
```

The two reports are combined only after the phases ran against their declared corpus
and access settings:

```bash
python scripts/combine_eval_reports.py \
  runs/core-eval.json runs/manual-eval.json runs/full-eval.json
```

`--eval-xlsx` remains a deprecated compatibility alias. Schema 1.0 remains supported.
Schema 1.1 adds `expectation`, expected-document arrays and `any`/`all` matching,
required facts with aliases, forbidden facts, optional fact ordering, question type,
difficulty, rationale, and source sections. IDs are permanent and unique. Required facts
default to `evidence_required: true`. Set it to `false` only for a scenario input or
derived result that must appear in the answer but cannot appear verbatim in the source;
the same case must retain separate source-backed facts that prove the governing rule.

## Interpret results

- `pass`: every applicable document, grounding, fact, order, refusal, or boundary rule
  passed.
- `manual_review`: evidence or answer quality was partial; this is not a pass.
- `fail`: one or more quality requirements were not met.
- `failure_class=infrastructure`: database, service, auth, timeout, MCP, or transport
  failure prevented a quality measurement.

For an `answer` case, every required fact must occur in the generated answer and every
source-backed fact must occur in supporting evidence. Explicit scenario/derived facts
are answer-only as described above. The expected document policy must pass, ordered
procedures must be in order, and no forbidden fact may occur. A `refuse` case must end in
the existing safe-refusal statuses without restricted or invented content. A
`safe_boundary` case must state the grounded information and explicitly mark the
unavailable or restricted boundary.

P19 adds end-to-end latency, recovery, request count, and sanitized STARTER generation
cost. The initial limits are P95 ≤ 5,000 ms, mean ≤ 3,000 ms, average generation cost
≤ USD 0.02 per eval case, and recovery rate ≤ 25%; 80% of a limit is a warning. Corpus
embedding cost is excluded.

## Grow the suite

Reproduce a real defect first. Review the expected fact directly against the synthetic
source, choose a permanent ID, add positive and boundary coverage, and run P12 plus the
applicable P12B phase. Never derive expected facts from model output, reuse an ID, add
question-specific production logic, or weaken evidence/refusal/ACL checks.

Candidate cases and feedback remain quarantined in `EVAL_CANDIDATE_CASES.md` and
`EVAL_GROWTH_LOG.md`. Promotion is an explicit reviewed code change; no feedback event
automatically changes the blocking suite or baseline.

## Baseline governance

The immutable v1 baseline continues to govern the original 25 cases during transition.
Baseline v2 can be created only from 10–15 successful, configuration-consistent 90-case
reports. Every counted run must pass all eight refusals, both safe-boundary cases,
RT-06, performance limits, and infrastructure checks; each case classification must be
stable in at least 90% of counted runs. Selection uses median pass count, then fewer
manual reviews, then lower P95 latency.

CI never creates, overwrites, or lowers an approved baseline. A candidate is promoted
only by an explicit justified owner-reviewed pull request. Model, embedding, chunking,
retrieval, recovery/scoring, phase access settings, corpus manifests, prompt hashes,
performance thresholds, and repository revisions remain pinned.
