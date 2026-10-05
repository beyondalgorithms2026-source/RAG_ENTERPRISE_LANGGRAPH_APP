"""Which fictional company (corpus) a recorded run, approval or audit event belongs to.

Runs record the corpus they were scoped to. Records written before corpus scoping
existed, and unscoped runs, belong to the original demo company.
"""

from __future__ import annotations

LEGACY_CORPUS = "northwind-public-demo"


def corpus_of(value: object) -> str:
    text = str(value or "").strip()
    return text or LEGACY_CORPUS
