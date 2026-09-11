# B004 cross-repository engineering standards

This is the canonical shared operating standard for human and AI contributors to the
three-repository B004 governed RAG system. Repository-local instructions remain
authoritative for local details, and the stricter rule applies whenever instructions
overlap.

## Architecture and repository ownership

- **APP** owns LangGraph orchestration, recovery routing, answer and evidence validation,
  red-team execution, and evaluation reporting.
- **MCP** owns the pure-standard-library JSON-RPC/HTTP integration boundary. It retains
  zero runtime dependencies and does not implement backend policy.
- **STARTER** owns retrieval, PostgreSQL/pgvector, embeddings, chunking, SQL-level ACL
  enforcement, citations, backend governance, and the active UI under `web/`.
- APP must never receive database credentials, query PostgreSQL, or call STARTER directly.
  Enterprise data flows through the MCP tools.
- MCP must not access the database, choose backend retrieval policy, implement ACLs, or
  bypass backend authentication or authorization.
- The private-assets repository is permanently out of scope.

Preserve this architecture. Do not introduce Redis, read replicas, pub/sub, asymmetric
JWT, Jest, new services, new dependencies, or comparable technology mandates unless the
technology is already part of B004 or the owner separately approves it. Generic
architecture advice is not a reason to expand this proof of concept.

## A. Before implementation

1. Identify which repository owns the requested behaviour before editing.
2. Read that repository's `AGENTS.md`, `.github/CONTRIBUTING.md`, and any applicable
   `CLAUDE.md`, status record, design document, or runbook.
3. Identify security, authorization, grounding, refusal, compatibility,
   prompt-injection, and cross-repository contract risks.
4. Establish the relevant test or evaluation case before or alongside implementation.
5. Do not silently change published claims, public API or CLI shapes, status
   vocabularies, evidence thresholds, or architecture boundaries.
6. Obtain approval before adding a dependency or changing an architecture or security
   boundary.

## B. Security invariants

- Never commit secrets, credentials, connection strings, API keys, `.env` files,
  private corpus data, generated local reports, or unsanitized diagnostics.
- Enforce document authorization inside retrieval SQL, never only after retrieval or in
  the UI.
- Treat user input, retrieved documents, tool responses, connector content, and model
  output as untrusted.
- Explicitly review every AI-facing input path for direct and indirect prompt injection.
- Preserve citation provenance, grounding validation, safe refusal, audit, approval,
  and redaction behaviour.
- Never weaken authentication, ACL, approval, audit, evidence, or refusal controls merely
  to make a test pass.

## C. Test and evaluation protocol

- Test meaningful behaviour. Do not add placeholder, dummy, tautological, or
  always-passing assertions.
- A useful test need not mutate state. Deterministic validation, parsing, schema,
  evidence, refusal, and policy tests are legitimate.
- Cover relevant failures and boundaries: malformed input, missing parameters,
  authentication or authorization failure, unavailable dependencies, timeout,
  irrelevant evidence, unsupported answers, must-refuse cases, and schema drift.
- Use fakes only when the test is explicitly a unit or deterministic mechanism test.
  Never claim that a fake proves live retrieval, SQL ACL enforcement, or full-stack
  answer quality.
- Quality-sensitive changes must run the applicable golden evaluation.
- **P12** is the fast mocked evaluation-harness smoke test. It proves deterministic
  harness behaviour, not live answer quality.
- **P12B** is the authoritative real APP → MCP → STARTER → PostgreSQL/pgvector
  25-question regression gate.
- Never automatically overwrite a baseline after a regression. Every P12B baseline
  change must be explicit, justified in its pull request, and approved by an eligible
  owner/CODEOWNER. Do not claim CODEOWNERS enforcement while no second eligible reviewer
  exists.
- Distinguish infrastructure and transport failures from answer-quality failures.

## D. API and AI-route review

For every modified API route or AI-facing path, explicitly check:

- input validation and size or range limits;
- authentication and authorization;
- direct and indirect prompt-injection exposure;
- whether untrusted retrieved content can become instructions;
- output redaction and sensitive diagnostic leakage;
- citation and grounding enforcement;
- timeout, retry, and unavailable-service behaviour;
- backward compatibility of request and response shapes; and
- whether a corresponding unit, integration, red-team, or golden-eval case is required.

## E. Completion criteria

A change is complete only when:

- relevant unit and integration tests pass;
- lint and formatting checks pass;
- repository boundaries remain intact;
- security, ACL, refusal, evidence, and redaction invariants remain intact;
- cross-repository contracts remain compatible;
- the applicable P12 or P12B evaluation meets the approved baseline;
- documentation and configuration-version metadata are updated when behaviour changes;
- actual test results, failures, and skips are reported honestly; and
- required CI checks pass.

## Guidance versus enforcement

This document is contributor guidance, not proof of compliance. Important requirements
should be encoded in CI, tests, branch protection, cross-repository contract tests,
red-team checks, SQL integration tests, and P12B wherever practical. Describe a rule as
“enforced” only when a named mechanical check actually verifies it.
