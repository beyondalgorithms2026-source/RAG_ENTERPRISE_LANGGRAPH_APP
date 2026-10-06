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

    async def ainvoke(self, messages):
        class _Msg:
            pass

        msg = _Msg()
        msg.content = self.text
        return msg


def test_verify_rejects_invented_number_entity_and_refusal():
    assert (
        verify_against_evidence(
            "The hard materials cost about 2% of what a rocket costs.", ROCKET_EVIDENCE
        )["verified"]
        is True
    )
    assert (
        verify_against_evidence("The materials cost about 5% of a rocket.", ROCKET_EVIDENCE)[
            "verified"
        ]
        is False
    )
    assert (
        verify_against_evidence("According to NASA, it is 2% of rocket cost.", ROCKET_EVIDENCE)[
            "verified"
        ]
        is False
    )
    assert verify_against_evidence("NOT_ANSWERABLE", ROCKET_EVIDENCE)["verified"] is False
    assert verify_against_evidence("", ROCKET_EVIDENCE)["verified"] is False


def test_verify_rejects_generic_answer_with_low_overlap():
    result = verify_against_evidence(
        "It depends entirely on unrelated market conditions elsewhere.", ROCKET_EVIDENCE
    )
    assert result["verified"] is False


def test_synthesize_verified_for_faithful_model_output():
    profile = classify_question(ROCKET_Q)
    faithful = "The hard materials of a rocket — aluminum, titanium, copper, and carbon fiber — cost about 2% of what a rocket costs."
    result = asyncio.run(
        synthesize_and_verify(
            question=ROCKET_Q,
            evidence=ROCKET_EVIDENCE,
            question_profile=profile,
            model=_StubModel(faithful),
        )
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
        async def ainvoke(self, messages):
            raise RuntimeError("no api key")

    result = asyncio.run(
        synthesize_and_verify(
            question=ROCKET_Q,
            evidence=ROCKET_EVIDENCE,
            question_profile=classify_question(ROCKET_Q),
            model=_BoomModel(),
        )
    )
    assert result["verified"] is False
    assert result["reason"].startswith("model_error")


def _rocket_orchestrator(*, enable_synthesis: bool, model=None) -> EnterpriseRagOrchestrator:
    settings = Settings(enable_synthesis=enable_synthesis)
    orchestrator = EnterpriseRagOrchestrator(settings=settings, quiet_mcp=False)
    orchestrator.synthesis_model = model

    async def fake(name, arguments):
        if name == "ask_grounded":
            return {"answer": "The materials cost about 2%.", "citations": []}, {
                "tool_name": name,
                "content": {},
            }
        if name == "search_documents":
            return {
                "results": [
                    {
                        "source_id": 9,
                        "source_part_id": 12,
                        "file_name": "spacex.txt",
                        "snippet": ROCKET_CHUNK,
                    }
                ]
            }, {"tool_name": name, "content": {}}
        return {
            "matched": True,
            "excerpt": ROCKET_CHUNK,
            "result": {"source_id": 9, "source_part_id": 12, "file_name": "spacex.txt"},
        }, {"tool_name": name, "content": {}}

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
    assert (
        result.source_evidence and "aerospace-grade aluminum" in result.source_evidence[0]["quote"]
    )
    assert result.synthesis_verified is False
    assert result.synthesized_answer is None


def test_tier2_synthesis_replaces_answer_and_keeps_verbatim_proof():
    faithful = "The hard materials of a rocket — aluminum, titanium, copper, and carbon fiber — cost about 2% of what a rocket costs."
    result = asyncio.run(
        _rocket_orchestrator(enable_synthesis=True, model=_StubModel(faithful)).run(ROCKET_Q)
    )
    assert result.synthesis_verified is True
    assert result.answer == faithful
    assert result.verbatim_answer and "aerospace-grade aluminum" in result.verbatim_answer
    assert result.source_evidence and result.source_evidence[0]["quote"]


def test_tier2_hallucination_falls_back_to_verbatim():
    result = asyncio.run(
        _rocket_orchestrator(
            enable_synthesis=True,
            model=_StubModel("Materials are 5% of cost, per NASA's John Smith."),
        ).run(ROCKET_Q)
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


def test_synthesize_falls_back_when_model_cannot_be_built(monkeypatch):
    import rag_enterprise_langgraph.graph as graph

    def broken_builder(settings):
        raise ValueError("OPENAI_API_KEY is not set")

    monkeypatch.setattr(graph, "build_chat_model", broken_builder)
    result = asyncio.run(
        synthesize_and_verify(
            question=ROCKET_Q,
            evidence=ROCKET_EVIDENCE,
            question_profile=classify_question(ROCKET_Q),
            settings=Settings(enable_synthesis=True),
        )
    )
    assert result == {"answer": None, "verified": False, "reason": "model_error:ValueError"}


def test_run_with_unbuildable_model_still_returns_verbatim_answer(monkeypatch):
    import rag_enterprise_langgraph.graph as graph

    monkeypatch.setattr(
        graph, "build_chat_model", lambda settings: (_ for _ in ()).throw(ValueError("no key"))
    )
    result = asyncio.run(_rocket_orchestrator(enable_synthesis=True).run(ROCKET_Q))
    assert result.synthesis_verified is False
    assert "2%" in result.answer or "2 %" in result.answer


def test_synthesis_reason_explains_each_outcome(monkeypatch):
    import rag_enterprise_langgraph.graph as graph

    off = asyncio.run(_rocket_orchestrator(enable_synthesis=False).run(ROCKET_Q))
    assert off.synthesis_reason == "disabled"

    faithful = "The hard materials of a rocket — aluminum, titanium, copper, and carbon fiber — cost about 2% of what a rocket costs."
    verified = asyncio.run(
        _rocket_orchestrator(enable_synthesis=True, model=_StubModel(faithful)).run(ROCKET_Q)
    )
    assert verified.synthesis_reason == "verified"
    assert verified.to_dict()["synthesis_reason"] == "verified"

    invented = asyncio.run(
        _rocket_orchestrator(enable_synthesis=True, model=_StubModel("It is 5% of the cost.")).run(
            ROCKET_Q
        )
    )
    assert invented.synthesis_reason == "unsupported_number:5%"

    monkeypatch.setattr(
        graph, "build_chat_model", lambda settings: (_ for _ in ()).throw(ValueError("no key"))
    )
    unbuilt = asyncio.run(_rocket_orchestrator(enable_synthesis=True).run(ROCKET_Q))
    assert unbuilt.synthesis_reason == "model_error:ValueError"


def test_withheld_run_hides_the_synthesis_reason():
    orchestrator = _rocket_orchestrator(
        enable_synthesis=True, model=_StubModel("It is 5% of the cost.")
    )
    result = asyncio.run(orchestrator.run(ROCKET_Q, approval_mode="always"))
    assert result.approval_status == "pending_approval"
    assert result.synthesis_reason is None
    assert "5%" not in str(result.to_dict())


def test_verify_allows_values_given_in_the_question_but_not_new_ones():
    evidence = [{"snippet": "Critical Incident: financial exposure above €250,000."}]
    question = "Expected financial exposure is €260,000. Does this meet the definition of a Critical Incident?"
    ok = verify_against_evidence(
        "Yes. A Critical Incident includes financial exposure above €250,000, and €260,000 is above it.",
        evidence,
        question=question,
    )
    assert ok == {"verified": True, "reason": "all_facts_supported"}
    invented = verify_against_evidence(
        "Yes. A Critical Incident includes financial exposure above €300,000.",
        evidence,
        question=question,
    )
    assert invented["verified"] is False
    assert invented["reason"] == "unsupported_number:300,000"


def test_verify_ignores_a_comma_after_a_number():
    evidence = [{"snippet": "The cap is £240 a night and the limit is 5,000 kilometres."}]
    answer = "The cap is £240, and the limit is 5,000, per the policy."
    assert verify_against_evidence(answer, evidence)["verified"] is True


def test_echoed_prompt_labels_are_neither_entities_nor_shown():
    evidence = [{"snippet": "Critical Incident: financial exposure above €250,000."}]
    question = "Expected exposure is €260,000. Is this a Critical Incident?"
    verdict = verify_against_evidence(
        "Yes, according to the SOURCE a Critical Incident includes exposure above €250,000.",
        evidence,
        question=question,
    )
    assert verdict["verified"] is True
    result = asyncio.run(
        synthesize_and_verify(
            question=question,
            evidence=evidence,
            model=_StubModel(
                "Yes, according to the SOURCE a Critical Incident includes exposure above "
                "€250,000, and €260,000 is above it."
            ),
        )
    )
    assert result["verified"] is True
    assert "SOURCE" not in result["answer"] and "according to the source" in result["answer"]


def test_inner_quotes_survive_answer_cleanup():
    evidence = [{"snippet": "Critical Incident: financial exposure above €250,000."}]
    question = "Expected exposure is €260,000. Is this a Critical Incident?"
    inner = 'Yes, as it is "financial exposure above €250,000."'
    result = asyncio.run(
        synthesize_and_verify(question=question, evidence=evidence, model=_StubModel(inner))
    )
    assert result["answer"] == inner
    wrapped = asyncio.run(
        synthesize_and_verify(
            question=question, evidence=evidence, model=_StubModel('"Yes, above €250,000."')
        )
    )
    assert wrapped["answer"] == "Yes, above €250,000."


def test_ordered_procedure_keeps_the_verbatim_answer():
    faithful = "The hard materials of a rocket cost about 2% of what a rocket costs."
    result = asyncio.run(
        _rocket_orchestrator(enable_synthesis=True, model=_StubModel(faithful)).run(
            "What are the steps that make up the cost of rocket materials?"
        )
    )
    assert result.synthesis_reason == "kept_verbatim_sequence"
    assert result.synthesis_verified is False
    assert result.answer != faithful


def test_openai_chat_model_gets_the_seed_and_other_providers_do_not(monkeypatch):
    import rag_enterprise_langgraph.graph as graph

    calls = []
    monkeypatch.setattr(graph, "init_chat_model", lambda name, **kwargs: calls.append(kwargs))
    graph.build_chat_model(Settings(model_provider="openai", model_name="gpt-4o-mini-2024-07-18"))
    graph.build_chat_model(Settings(model_provider="ollama", model_name="llama3.2:3b"))
    assert calls[0]["seed"] == 20261006 and calls[0]["temperature"] == 0.0
    assert "seed" not in calls[1]


class _SequenceModel:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    async def ainvoke(self, messages):
        self.calls.append(messages)
        return type("Reply", (), {"content": self.replies[len(self.calls) - 1]})()


CRITICAL_EVIDENCE = [{"snippet": "Critical Incident: financial exposure above €250,000."}]
CRITICAL_Q = "Expected exposure is €260,000. Does this meet the definition of a Critical Incident?"


def test_comparison_answer_is_retried_once_to_state_the_given_value():
    model = _SequenceModel(
        "Yes, this is a Critical Incident because the exposure is above €250,000.",
        "Yes, the €260,000 exposure is a Critical Incident because it is above €250,000.",
    )
    result = asyncio.run(
        synthesize_and_verify(question=CRITICAL_Q, evidence=CRITICAL_EVIDENCE, model=model)
    )
    assert result == {
        "answer": "Yes, the €260,000 exposure is a Critical Incident because it is above €250,000.",
        "verified": True,
        "reason": "verified",
    }
    assert len(model.calls) == 2 and "260,000" in model.calls[1][-1]["content"]


def test_retry_that_still_omits_the_value_keeps_the_first_verified_answer():
    first = "Yes, this is a Critical Incident because the exposure is above €250,000."
    model = _SequenceModel(first, "Yes, it is above €250,000.")
    result = asyncio.run(
        synthesize_and_verify(question=CRITICAL_Q, evidence=CRITICAL_EVIDENCE, model=model)
    )
    assert result["answer"] == first and result["verified"] is True


def test_no_retry_when_the_value_is_stated_or_the_question_is_not_a_comparison():
    stated = _SequenceModel("Yes, €260,000 is above €250,000, so it is a Critical Incident.")
    asyncio.run(
        synthesize_and_verify(question=CRITICAL_Q, evidence=CRITICAL_EVIDENCE, model=stated)
    )
    assert len(stated.calls) == 1
    open_question = _SequenceModel("A Critical Incident includes exposure above €250,000.")
    asyncio.run(
        synthesize_and_verify(
            question="What exposure makes a Critical Incident for a €260,000 claim?",
            evidence=CRITICAL_EVIDENCE,
            model=open_question,
        )
    )
    assert len(open_question.calls) == 1
