# Contributing

Thank you for improving the governed RAG agent layer. This repository owns
orchestration, evidence validation, refusal and recovery behaviour, proof rendering, and
the red-team and evaluation harnesses. Retrieval, access control, citations, and database
access belong in the sibling data-layer repository.

Read [`AGENTS.md`](../AGENTS.md) and the canonical
[B004 engineering standard](../docs/ENGINEERING_STANDARDS.md) before making changes.
The local guide is sufficient for safe work when sibling repositories are unavailable;
where instructions overlap, preserve the stricter rule. Their architecture boundaries,
status vocabulary, redaction requirements, and escalation rules are contributor
guidance. CI and tests provide the corresponding mechanical checks where stated.

## Development setup

Use Python 3.12 for the project environment. The package remains compatible with Python
3.10 and later.

```bash
python3.12 -m venv .venv312
source .venv312/bin/activate
python -m pip install -e ".[dev]"
```

The offline test suite does not require the backend, MCP server, database, or a model.
Running live diagnostics or evaluation does require the sibling repositories and the
environment variables described in `AGENTS.md` and `.env.example`. Never commit `.env`
files or their values.

## Before opening a pull request

Run the same checks that protect the repository in CI:

```bash
python -m ruff check .
python -m ruff format --check .
python -m pytest -q
python -m rag_enterprise_langgraph.cli --red-team
```

Install and run the repository hooks when contributing locally:

```bash
python -m pip install pre-commit
pre-commit install
pre-commit run --all-files
```

CI runs three required jobs: `lint`, `test`, and `security`. The test job also runs the
deterministic red-team scenarios. The security job scans committed history for secrets
and audits installed Python dependencies.

If a change affects prompts, retrieval configuration, embeddings, evidence rules, or
answer/refusal behaviour, attach the relevant evaluation result to the pull request.
Never weaken evidence thresholds, change public response shapes, add a dependency, or
move responsibilities across repository boundaries without prior approval.

P12 is the fast fake-driven evaluation-harness smoke test. P12B is the authoritative
real APP → MCP → STARTER → PostgreSQL/pgvector 25-question quality gate. Do not claim
that P12 or another mocked test proves live retrieval or SQL authorization. A P12B
baseline change must be explicit, justified, and owner/CODEOWNER-reviewed; it must never
be automatically overwritten after a regression.

## Protected branch policy

Changes to `main` should go through a pull request with all required CI checks passing,
all review conversations resolved, and a CODEOWNERS review when an eligible second
maintainer is available. Force pushes and branch deletion are disabled. A solo owner
cannot approve their own pull request, so mandatory approving reviews should only be
enabled after another maintainer has been granted access.
