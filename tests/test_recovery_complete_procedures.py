"""Recovery must not turn a complete authorized procedure into its first action."""

from rag_enterprise_langgraph.answer_quality import classify_question
from rag_enterprise_langgraph.orchestrator import (
    _answer_from_evidence,
    exact_phrase_bias,
    extract_anchor_terms,
)


def test_question_opening_verbs_are_not_distinctive_recovery_phrases():
    for question in [
        "Are facilitation payments allowed?",
        "Can contractors approve expenses?",
        "Does weekend overtime require approval?",
    ]:
        assert exact_phrase_bias(question, extract_anchor_terms(question)) is None


def test_recovery_preserves_all_ordered_actions_and_numbers():
    question = "What is the ordered sequence of actions for a temperature excursion?"
    procedure = "Temperature excursion response:\n1. Stop loading.\n2. Quarantine stock.\n3. Capture temperature graph.\n4. Notify Quality.\n5. Check released stock.\n6. Notify customer if required.\n7. Record deviation.\n8. Await written Quality release."
    answer = _answer_from_evidence(
        question,
        [{"file_name": "manual.md", "snippet": procedure}],
        anchors=["temperature", "excursion"],
        question_profile=classify_question(question),
    )
    assert procedure in answer
    assert answer.index("1. Stop") < answer.index("8. Await")


def test_recovery_preserves_prohibitions_not_just_notice_duration():
    question = "Which five things may an interim control notice not do?"
    snippet = "An interim control notice is valid for 60 days.\nAn interim control notice may not increase authority, waive reporting, reduce PPE, shorten retention, or authorise unqualified drivers."
    answer = _answer_from_evidence(
        question,
        [{"file_name": "manual.md", "snippet": snippet}],
        anchors=["interim", "control", "notice"],
        question_profile=classify_question(question),
    )
    for clause in [
        "may not increase authority",
        "waive reporting",
        "reduce PPE",
        "shorten retention",
        "authorise unqualified drivers",
    ]:
        assert clause in answer


def test_unrelated_numbered_procedure_is_not_promoted_by_its_shape():
    question = "What is the ordered temperature excursion response?"
    answer = _answer_from_evidence(
        question,
        [{"snippet": "1. Pick shoes.\n2. Pay cashier.", "file_name": "shop.md"}],
        anchors=["temperature", "excursion"],
        question_profile=classify_question(question),
    )
    assert "Recovered answer" not in answer
