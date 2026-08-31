from __future__ import annotations

import asyncio

from rag_enterprise_langgraph.answer_quality import classify_question
from rag_enterprise_langgraph.config import Settings
from rag_enterprise_langgraph.orchestrator import EnterpriseRagOrchestrator
from rag_enterprise_langgraph.synthesis import synthesize_and_verify, verify_against_evidence


ROCKET_CHUNK = (
    "if you calculate the cost of goods sold for aerospace-grade aluminum alloys, plus some titanium, "
    "copper, and carbon fiber on the open commodities market, it's about 2% of what rockets cost. "
    "I want to plant that seed because the question in your mind should be why is this expensive? "
    "You're not going to get it all the way down to 2% of what that rocket costs, but 2% being the hard "
    "materials, I'm not someone who's in an industrial job."
)
ROCKET_EVIDENCE = [{"snippet": ROCKET_CHUNK, "file_name": "spacex.txt"}]
ROCKET_Q = "What is the cost of rocket travel based on the materials?"


class _StubModel:
    def __init__(self, text: str):
        self.text = text

    async def ainvoke(self, messages):  # noqa: ANN001
        class _Msg:
            pass

        msg = _Msg()
        msg.content = self.text
        return msg


def test_verify_rejects_invented_number_entity_and_refusal():
    assert verify_against_evidence("The hard materials cost about 2% of what a rocket costs.", ROCKET_EVIDENCE)["verified"] is True
    assert verify_against_evidence("The materials cost about 5% of a rocket.", ROCKET_EVIDENCE)["verified"] is False
    assert verify_against_evidence("According to NASA, it is 2% of rocket cost.", ROCKET_EVIDENCE)["verified"] is False
    assert verify_against_evidence("NOT_ANSWERABLE", ROCKET_EVIDENCE)["verified"] is False
    assert verify_against_evidence("", ROCKET_EVIDENCE)["verified"] is False


def test_verify_rejects_generic_answer_with_low_overlap():
    result = verify_against_evidence("It depends entirely on unrelated market conditions elsewhere.", ROCKET_EVIDENCE)
    assert result["verified"] is False


def test_synthesize_verified_for_faithful_model_output():
    profile = classify_question(ROCKET_Q)
    faithful = "The hard materials of a rocket — aluminum, titanium, copper, and carbon fiber — cost about 2% of what a rocket costs."
    result = asyncio.run(
        synthesize_and_verify(question=ROCKET_Q, evidence=ROCKET_EVIDENCE, question_profile=profile, model=_StubModel(faithful))
    )
    assert result["verified"] is True
    assert result["answer"] == faithful


def test_synthesize_rejected_for_hallucinated_model_output():
    profile = classify_question(ROCKET_Q)
    result = asyncio.run(
        synthesize_and_verify(
            question=ROCKET_Q,
            evidence=ROCKET_EVIDENCE,
            question_profile=profile,
            model=_StubModel("SpaceX engineer John Smith said materials are 5% of rocket cost."),
        )
    )
    assert result["verified"] is False


def test_synthesize_falls_back_when_model_errors():
    class _BoomModel:
        async def ainvoke(self, messages):  # noqa: ANN001
            raise RuntimeError("no api key")

    result = asyncio.run(
        synthesize_and_verify(question=ROCKET_Q, evidence=ROCKET_EVIDENCE, question_profile=classify_question(ROCKET_Q), model=_BoomModel())
    )
    assert result["verified"] is False
    assert result["reason"].startswith("model_error")


def _rocket_orchestrator(*, enable_synthesis: bool, model=None) -> EnterpriseRagOrchestrator:
    settings = Settings(enable_synthesis=enable_synthesis)
    orchestrator = EnterpriseRagOrchestrator(settings=settings, quiet_mcp=False)
    orchestrator.synthesis_model = model

    async def fake(name, arguments):  # noqa: ANN001, ARG001
        if name == "ask_grounded":
            return {"answer": "Not found in provided sources.", "citations": []}, {"tool_name": name, "content": {}}
        if name == "search_documents":
            return {"results": [{"source_id": 9, "source_part_id": 12, "file_name": "spacex.txt", "snippet": ROCKET_CHUNK}]}, {"tool_name": name, "content": {}}
        return {"matched": True, "excerpt": ROCKET_CHUNK, "result": {"source_id": 9, "source_part_id": 12, "file_name": "spacex.txt"}}, {"tool_name": name, "content": {}}

    orchestrator._call_tool = fake  # type: ignore[method-assign]
    return orchestrator


def test_tier1_deterministic_picks_core_fact_not_caveat():
    result = asyncio.run(_rocket_orchestrator(enable_synthesis=False).run(ROCKET_Q))
    assert result.grounding_status == "needs_review"
    # Picks the stated fact, not the "you're not going to..." caveat.
    assert "you're not going to" not in result.answer.lower()
    assert "2%" in result.answer
    assert "aerospace-grade aluminum" in result.answer
    # Verbatim proof is attached and synthesis stayed off.
    assert result.source_evidence and "aerospace-grade aluminum" in result.source_evidence[0]["quote"]
    assert result.synthesis_verified is False
    assert result.synthesized_answer is None


def test_tier2_synthesis_replaces_answer_and_keeps_verbatim_proof():
    faithful = "The hard materials of a rocket — aluminum, titanium, copper, and carbon fiber — cost about 2% of what a rocket costs."
    result = asyncio.run(_rocket_orchestrator(enable_synthesis=True, model=_StubModel(faithful)).run(ROCKET_Q))
    assert result.synthesis_verified is True
    assert result.answer == faithful
    assert result.verbatim_answer and "aerospace-grade aluminum" in result.verbatim_answer
    assert result.source_evidence and result.source_evidence[0]["quote"]


def test_tier2_hallucination_falls_back_to_verbatim():
    result = asyncio.run(
        _rocket_orchestrator(enable_synthesis=True, model=_StubModel("Materials are 5% of cost, per NASA's John Smith.")).run(ROCKET_Q)
    )
    assert result.synthesis_verified is False
    # Falls back to the extractive verbatim answer, never the unverified synthesis.
    assert "5%" not in result.answer
    assert "2%" in result.answer


def test_gated_run_live_response_withholds_all_answer_content():
    import json

    orchestrator = _rocket_orchestrator(enable_synthesis=False)
    result = asyncio.run(orchestrator.run(ROCKET_Q, approval_mode="always"))
    assert result.approval_status == "pending_approval"

    live = json.dumps(result.to_dict())
    # No field of the live response may reveal the withheld answer/source content.
    assert "2%" not in live
    assert "aerospace-grade aluminum" not in live
    assert result.source_evidence == []
    assert result.evidence == []
    assert result.citations == []
    assert result.tool_outputs == []
    assert result.rejected_evidence == []
    assert result.verbatim_answer is None
    assert result.synthesized_answer is None
    assert all(a.get("answer_preview") == "[withheld pending approval]" for a in result.attempts)
    # Process metadata stays visible.
    assert result.decision_trail and result.execution_timeline
