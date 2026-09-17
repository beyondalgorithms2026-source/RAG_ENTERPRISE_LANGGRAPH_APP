# B004 v2 quality-evidence release checklist

Started: `2026-09-17T05:37:09Z`
Hard stop: `2026-09-19T05:37:09Z`

This release produces one provisional 90-case evidence snapshot. It does not
approve a v2 baseline and does not replace the approved 25-case v1 evidence.

## Preserved approved evidence

| File | SHA-256 at release start |
| --- | --- |
| `config/eval-set-northwind.json` | `292564db50c79d5140bea7ea9e4c1bab6842f1857afcd6e6bce61f9f16893bfd` |
| `config/eval-baselines/northwind-openai-v1.json` | `6e729a9e27407493cd5352bb991c506ab00bb502438016a39672e543cad6bde4` |
| `docs/evaluation/status.json` | `b10ba12ece3b81ed8f4817d528a8de87244198a33e46f3b490eec9d9606b03ed` |
| `docs/evaluation/index.html` | `f199912336af7336a67fefe9a78ff0b732d6f5207b670a6c60a1d796d3b5e9ab` |

## Starting revisions and frozen candidate inputs

- APP start: `f2e687b05675ec2a8408a51e230f154191154fd7`
- STARTER start: `06abdaff795c26170c61c334eebc1b7d044ef3ec`
- MCP selected protected revision: `047ed8e8ef30f380eb5da437a57fb1a02f3d6625`
- Core candidate: `99ef50a3409d4a472f645b80e4a3b4b23e52e27a575164b223f4b184001ac242`
- Manual candidate: `3dc3a8ebcec8ffc26bc96c9fd74b67617a38fe1e3923bc7dd038dade9b7e7141`
- Suite declaration: `cd6c91b4691aae6c8a6058f16b379f03efeda2c4cb1619f16d1d116cf7ff6e41`

## Change ownership

- Evaluation/reliability: candidate packs, grader, eval runner, recovery,
  STARTER candidate context/prompt/configuration and their tests/docs.
- Evidence release: combined-report dimensions, evidence workflow mode,
  RT-06/RT-16 live controls, provisional generator and this checklist.
- Unrelated and excluded: APP `static/app.css`, `static/app.js`, `ui.py`; STARTER
  `backend/app/main.py`. These edits belong to the user and must not enter evidence commits.

## Hard-stop rules

- No quality tuning, model swap, general retrieval optimization or calibration loop.
- One rerun only for a diagnosed transient infrastructure failure.
- Ordinary fail/manual-review cases are retained as limitations.
- At the hard stop, preserve either the clean evidence package or a precise blocker report.
