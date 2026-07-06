from __future__ import annotations

from rag_enterprise_langgraph.answer_quality import classify_question, review_answer


def test_question_classifier_detects_list_count_and_comparison():
    profile = classify_question(
        "What are the 3 interrelated things that make Renaissance Technologies unique from other investment firms such as Citadel?"
    )

    assert "list_with_count" in profile.question_types
    assert "comparison" in profile.question_types
    assert profile.expected_answer_shape.item_count == 3
    assert profile.expected_answer_shape.requires_cited_support_per_item is True


def test_question_classifier_detects_material_cost_share_as_percentage_shape():
    profile = classify_question("What is the cost of rocket travel based on the materials?")

    assert "exact_numeric" in profile.question_types
    assert "percentage_or_ratio" in profile.question_types
    assert profile.expected_answer_shape.requires_percentage is True


def test_verified_list_answer_requires_each_item_to_be_citation_supported():
    question = "What are the 3 interrelated things that make Renaissance Technologies unique from other investment firms?"
    answer = (
        "1. The firm used one model everyone collaborated on. "
        "2. It kept a small team with unusually high individual impact. "
        "3. It used an LPGP/high-carry incentive model."
    )
    evidence = [
        {
            "snippet": (
                "The three interrelated things were one model everyone collaborated on, "
                "a small team with unusually high individual impact, and an LPGP high-carry incentive model."
            )
        }
    ]

    review = review_answer(question=question, answer=answer, evidence=evidence)

    assert review.status == "verified"
    assert review.supported_items == 3
    assert review.evidence_support == "complete"


def test_unsupported_list_items_are_not_verified_just_because_citation_exists():
    question = "What are the 3 interrelated things that make Renaissance Technologies unique from other investment firms?"
    answer = (
        "1. The firm used one model everyone collaborated on. "
        "2. It spun out of First Round Capital. "
        "3. It focused on consumer internet investments."
    )
    evidence = [{"snippet": "Number one, there is one model everyone collaborates on."}]

    review = review_answer(question=question, answer=answer, evidence=evidence)

    assert review.status == "weak"
    assert review.reason in {"list_items_not_supported_by_citations", "citation_snippet_appears_cut_off"}
    assert review.review_recommended is True


def test_material_cost_answer_without_percentage_is_weak():
    review = review_answer(
        question="What is the cost of rocket travel based on the materials?",
        answer="The vehicle used aerospace aluminum, titanium, copper, and carbon fiber, costing about $8 million.",
        evidence=[{"snippet": "Aerospace-grade aluminum, titanium, copper, and carbon fiber were discussed."}],
    )

    assert review.status == "weak"
    assert review.reason == "missing_percentage_answer"


def test_material_cost_percentage_supported_by_evidence_is_verified():
    review = review_answer(
        question="What is the cost of rocket travel based on the materials?",
        answer="The material cost was approximately 2% of the rocket cost.",
        evidence=[{"snippet": "The raw aerospace material cost was only about 2% of the total rocket cost."}],
    )

    assert review.status == "verified"
    assert review.answer_values == ["2%"]
    assert review.citation_values == ["2%"]
