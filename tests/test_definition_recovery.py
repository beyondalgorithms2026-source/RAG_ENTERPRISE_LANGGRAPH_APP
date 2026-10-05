"""Recovery answers a defined-term question from the term's definition row.

Replays keyword search results captured from the live demo for OM-044 and OM-046, the
two mandatory v2 calibration cases that recovery answered with the wrong passage.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from rag_enterprise_langgraph.config import Settings
from rag_enterprise_langgraph.orchestrator import (
    EnterpriseRagOrchestrator,
    _defined_term_candidates,
    _definition_rows,
)

FIXTURE = json.loads(
    Path("tests/fixtures/definition_recovery_live_2026-10-05.json").read_text(encoding="utf-8")
)


class _StubModel:
    def __init__(self, text: str):
        self.text = text

    async def ainvoke(self, messages):
        return type("Reply", (), {"content": self.text})()


def _run(case: str, *, synthesis: str | None = None):
    data = FIXTURE[case]
    calls: list[tuple[str, dict]] = []
    orchestrator = EnterpriseRagOrchestrator(
        settings=Settings(enable_synthesis=synthesis is not None), quiet_mcp=False
    )
    if synthesis is not None:
        orchestrator.synthesis_model = _StubModel(synthesis)

    async def fake_tool_call(name, arguments):
        calls.append((name, dict(arguments)))
        if name == "ask_grounded":
            # As live: STARTER saw candidate chunks but produced no grounded answer.
            first_chunk = data["search"][0]["chunk_id"]
            return {
                "answer": "Not found in provided sources.",
                "citations": [],
                "used_chunks_count": 5,
                "debug_info": {
                    "retrieval_trace": {
                        "score_diagnostics": [{"chunk_id": first_chunk, "keyword_score": 1.0}]
                    }
                },
            }, {
                "tool_name": name,
                "content": {},
            }
        if name == "search_documents":
            lookup = str(arguments.get("question", "")).endswith("defined meaning")
            results = data.get("definition_lookup", []) if lookup else data["search"]
            return {"results": results}, {"tool_name": name, "content": {}}
        return {"matched": False}, {"tool_name": name, "content": {}}

    orchestrator._call_tool = fake_tool_call  # type: ignore[method-assign]
    return asyncio.run(orchestrator.run(data["question"])), calls


def test_om_044_recovery_quotes_the_temperature_excursion_definition():
    result, calls = _run("OM-044")
    assert result.grounding_status in {"recovered", "needs_review"}
    assert "Temperature Excursion:" in result.answer
    assert "5 consecutive minutes" in result.answer
    assert "maximum excursion time is 30 minutes" not in result.answer
    lookups = [
        args for name, args in calls if args.get("question", "").endswith("defined meaning")
    ]
    assert lookups == [
        {"question": "Temperature Excursion defined meaning", "k": 4, "mode": "keyword"}
    ]
    assert any(step["label"] == "Definition lookup" for step in result.decision_trail)


def test_om_046_recovery_quotes_the_critical_incident_row_not_the_table_start():
    result, calls = _run("OM-046")
    assert "Critical Incident:" in result.answer
    assert "above €250,000" in result.answer
    assert "Board of Directors" not in result.answer
    # The definition was already in the retrieved evidence, so no extra lookup is made.
    assert not [args for _, args in calls if args.get("question", "").endswith("defined meaning")]


@pytest.mark.parametrize(
    ("question", "terms"),
    [
        ("Is that a Temperature Excursion?", ["Temperature Excursion"]),
        ("The matter must be handled Immediately. What is the latest time?", ["Immediately"]),
        ("Does Working Day allow a delay in Spain?", ["Working Day", "Spain"]),
        ("What is the cap on gifts?", []),
    ],
)
def test_defined_term_candidates(question, terms):
    assert _defined_term_candidates(question) == terms


def test_definition_rows_reads_collapsed_and_multiline_tables():
    collapsed = (
        "|Term|Defined meaning| |---|---| |Board|The Board.| |Critical Incident|Above €250,000.|"
    )
    assert _definition_rows(collapsed, ["Critical Incident"]) == [
        "Critical Incident: Above €250,000."
    ]
    multiline = (
        "|Term|Defined meaning|\n|---|---|\n|Working Day|Mon–Fri, not Belgian public holidays.|"
    )
    assert _definition_rows(multiline, ["working day"]) == [
        "Working Day: Mon–Fri, not Belgian public holidays."
    ]
    assert _definition_rows(collapsed, ["Excursion"]) == []


@pytest.mark.parametrize(
    ("case", "reply", "required"),
    [
        (
            "OM-044",
            "No. A Temperature Excursion is a temperature outside the required range for more "
            "than 5 consecutive minutes, and four minutes is shorter than that.",
            ("5 consecutive minutes", "four minutes"),
        ),
        (
            "OM-046",
            "Yes. A Critical Incident includes financial exposure above €250,000, and the "
            "expected €260,000 is above that threshold.",
            ("above €250,000", "€260,000"),
        ),
    ],
)
def test_verified_synthesis_compares_the_question_value_with_the_definition(case, reply, required):
    result, _ = _run(case, synthesis=reply)
    assert result.synthesis_reason == "verified"
    assert result.answer == reply
    assert all(fact in result.answer for fact in required)
    assert "Temperature Excursion:" in result.verbatim_answer or "Critical Incident:" in (
        result.verbatim_answer
    )
