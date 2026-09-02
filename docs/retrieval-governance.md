# Retrieval governance: what the agent may and may not decide

This note covers one architectural principle, the capability set it governs, and one
extension that was considered and deliberately not built.

## The principle

The agent layer has no direct data access. It cannot reach the database; it can only
ask the MCP server, which asks the backend, which owns authentication, ACL trimming
and retrieval.

The same boundary applies a second time, and this is the part that is easy to miss:

> **The agent layer also cannot choose its own retrieval policy.**

Reranking, query transformation, rewriting, expansion, HyDE, multi-query and fusion
strategy are not parameters on the request. They are properties of a server-side
profile that an operator activates. A calling agent can express *what* it wants
retrieved; it cannot dictate *how* retrieval behaves.

### Why this matters beyond tidiness

Retrieval parameters are an attack surface. If a caller can set `rerank=false`, push
`k` to 50, or drop a filter, then prompt injection in retrieved text — or a careless
client — can change what the system retrieves, and therefore what it asserts, without
ever touching the data layer. Governance guarantees that depend on retrieval behaviour
do not hold if the caller controls retrieval behaviour.

Putting retrieval policy server-side under an operator-managed profile means those
guarantees hold regardless of what the agent asks for.

## What the MCP tool does expose

`ask_grounded` accepts eleven parameters: `question`, `k_chunks` (capped at 20),
`mode`, `filters`, `deep_research`, `custom_query`, `anchor_terms`,
`exact_phrase_bias`, `expand_neighbors`, `dry_run`, `force_rare_keyword_scan`.

These describe *what to look for*. Note that `deep_research` is already an
intent-level parameter rather than a raw knob: the caller says "I need higher recall"
and the backend decides what that means, using its own alpha and candidate counts.

## Capability status

Honest status per feature. "Implemented" means the code exists and runs.
"Evaluated" means it was measured on the published 25-question evaluation.

| Capability | Implemented | Evaluated | Default |
|---|---|---|---|
| Hybrid retrieval (vector + keyword) | yes | yes | on |
| Linear fusion | yes | yes | on |
| Reciprocal rank fusion (RRF) | yes | yes, in the augmented configuration | off |
| Cross-encoder reranking | yes | yes, in the augmented configuration | off |
| MMR diversity | yes | yes, in the augmented configuration | off |
| Query transformation | yes | yes, in the augmented configuration | off |
| Query rewrite | yes | yes, in the augmented configuration | off |
| Query expansion | yes | yes, in the augmented configuration | off |
| HyDE | yes | yes, in the augmented configuration | off |
| Multi-query | yes | yes, in the augmented configuration | off |
| Governed semantic cache | yes | no | off |
| Graph / temporal enrichment | yes | no | off |
| Agent-layer recovery loop | yes | yes | on |
| ACL trimming in retrieval SQL | yes | partially — see below | on |

Retrieval augmentation ships **off by default**, and the published evaluation is the
first measurement of what enabling it buys. Both configurations are published,
whichever way the numbers went.

On the ACL row: the evaluation exercises retrieval with ACL active, but the red-team
scenario that specifically tests ACL bypass (RT-06) is labelled `requires_backend` and
is not simulated. See the red-team report.

## Considered and not built: intent-level retrieval presets

A `search_depth: quick | standard | thorough` parameter on `ask_grounded` would let a
caller express a need without exposing parameters. The backend would map each value to
a governed profile, so the caller expresses intent and the server still decides
settings. The pattern already exists here — `deep_research` works exactly this way.

**Not built, deliberately.** Three reasons:

1. It weakens the claim above. "The agent cannot select retrieval policy" is a stronger
   and more memorable guarantee than "the agent selects from three governed presets."
2. Each preset needs its own evaluation to be evidence rather than decoration. Three
   presets is three evaluation runs and three sets of numbers to defend.
3. It expands the governed surface — every parameter a caller can set is a parameter an
   attacker can try to steer.

Estimated cost if it were built: 6-10 hours including per-preset evaluation. It is
recorded as a candidate for later work, not as a gap.
