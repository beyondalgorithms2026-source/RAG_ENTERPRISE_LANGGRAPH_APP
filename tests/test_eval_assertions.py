import copy
import json
from pathlib import Path

import pytest

from rag_enterprise_langgraph import eval_assertions as grading
from rag_enterprise_langgraph.eval_runner import _fact_results, read_eval_json

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = [
    {
        "id": "rule",
        "document": "policy",
        "section": "1.2",
        "text": "Financial exposure above €250,000 is Critical. Written Quality release is required.",
    }
]


def assertion(kind="concept", **kwargs):
    return {"id": "fact", "type": kind, "source_refs": ["rule"], **kwargs}


def evaluate(answer, item):
    return grading.evaluate(
        answer=answer,
        assertions=[item],
        references=REFERENCE,
        evidence=[{"snippet": REFERENCE[0]["text"]}],
        citations=[],
    )


@pytest.mark.parametrize("text", ["€250,000", "250000 EUR", "250,000 euros", "EUR 250000"])
def test_currency_parsing(text):
    result = evaluate(text, assertion("numeric", value="250000", unit="EUR"))
    assert result["assertions"][0]["state"] == "supported"


@pytest.mark.parametrize("text", ["2.54%", "254%", "25.4%", "2.5 hours"])
def test_decimal_and_unit_are_not_collapsed(text):
    assert evaluate(text, assertion("numeric", value="2.5", unit="percent"))["hard_failure"]


def test_decimal_match_and_strict_comparator():
    assert not evaluate("2.5%", assertion("numeric", value="2.5", unit="percent"))["hard_failure"]
    item = assertion("numeric", value="250000", unit="EUR", comparator="gt")
    assert not evaluate("above €250,000", item)["hard_failure"]
    assert evaluate("up to €250,000", item)["hard_failure"]


def test_sentence_period_is_not_a_decimal_digit():
    assert not evaluate(
        "The limit is €250,000.", assertion("numeric", value="250000", unit="EUR")
    )["hard_failure"]
    assert evaluate("The limit is €250,000.5.", assertion("numeric", value="250000", unit="EUR"))[
        "hard_failure"
    ]


def test_wrong_polarity_cannot_pass_by_mentioning_numbers():
    assert evaluate("No, €260,000 is not above €250,000.", assertion("polarity", value="yes"))[
        "hard_failure"
    ]


def test_temperature_trigger_preserves_strict_boundary():
    item = assertion("numeric", value="5", unit="minutes", comparator="gt")
    assert not evaluate("more than 5 consecutive minutes", item)["hard_failure"]
    assert evaluate("at least 5 consecutive minutes", item)["hard_failure"]
    assert evaluate("4 minutes", item)["hard_failure"]


@pytest.mark.parametrize("value", [True, "NaN", "Infinity"])
def test_invalid_numeric_values(value):
    with pytest.raises(grading.AssertionError):
        grading.validate([assertion("numeric", value=value, unit="EUR")], REFERENCE)


def test_identifier_does_not_match_different_section():
    assert evaluate("Section 1.20", assertion("identifier", any_of=["1.2"]))["hard_failure"]


def test_om072_matches_source_seven_points():
    candidate = read_eval_json(ROOT / "config/eval-set-operations-manual-v3.2-candidate.json")
    case = next(c for c in candidate if c.case_id == "OM-072")
    assert len(case.ordered_fact_ids) == 7
    assert "seven" in case.question


@pytest.mark.parametrize(
    "kwargs",
    [
        {"type": "unknown"},
        {"source_refs": ["missing"]},
        {"source_refs": []},
        {"any_of": []},
        {"required": "true"},
    ],
)
def test_invalid_contract(kwargs):
    item = assertion(any_of=["release"])
    item.update(kwargs)
    with pytest.raises(grading.AssertionError):
        grading.validate([item], REFERENCE)


def test_contradictory_polarities():
    with pytest.raises(grading.AssertionError):
        grading.validate(
            [
                assertion("polarity", value="yes"),
                {**assertion("polarity", value="no"), "id": "other"},
            ],
            REFERENCE,
        )


def test_semantic_judge_requires_literal_support_spans():
    answer = "Written approval by Quality is mandatory."
    result = evaluate(answer, assertion(any_of=["written Quality release"]))
    valid = {
        "assertions": [
            {
                "id": "fact",
                "state": "supported",
                "answer_span": answer,
                "evidence_span": "Written Quality release is required.",
                "explanation": "Same mandatory release concept.",
            }
        ]
    }
    assert (
        grading.apply_judgement(copy.deepcopy(result), valid, answer=answer, references=REFERENCE)[
            "assertions"
        ][0]["state"]
        == "supported"
    )
    invalid = copy.deepcopy(valid)
    invalid["assertions"][0]["answer_span"] = "invented support"
    with pytest.raises(grading.AssertionError):
        grading.apply_judgement(result, invalid, answer=answer, references=REFERENCE)


def test_judge_cannot_override_hard_failure():
    result = evaluate("No.", assertion("polarity", value="yes"))
    with pytest.raises(grading.AssertionError):
        grading.apply_judgement(
            result,
            {"assertions": [{"id": "fact", "state": "supported"}]},
            answer="No.",
            references=REFERENCE,
        )
    assert result["hard_failure"]


def test_literal_span_accepts_only_whitespace_variation():
    assert grading._literal_span("Written\nQuality  release", "Written Quality release") == (
        "Written\nQuality  release"
    )
    assert grading._literal_span("Written Quality release", "Written approval") is None
    assert grading._literal_span("No release", "release is allowed") is None
    assert grading._literal_span("Five minutes", "five minutes") is None


def test_frozen_answers_reproduce_original_canonical_answer_match():
    frozen = json.loads((ROOT / "tests/fixtures/starter_manual_diagnostic_36.json").read_text())
    cases = {
        c.case_id: c for c in read_eval_json(ROOT / "config/eval-set-operations-manual-v3.2.json")
    }
    assert len(frozen["rows"]) == 36
    for row in frozen["rows"]:
        observed = _fact_results(answer=row["answer"], evidence=[], case=cases[row["case_id"]])
        assert all(f["answer_matched"] for f in observed) == row["canonical_answer_match"]
    assert sum(row["canonical_answer_match"] for row in frozen["rows"]) == 24


def test_candidate_pack_preserves_ids_and_rejects_known_wrong_answers():
    original = read_eval_json(ROOT / "config/eval-set-operations-manual-v3.2.json")
    candidate = read_eval_json(ROOT / "config/eval-set-operations-manual-v3.2-candidate.json")
    assert [c.case_id for c in original] == [c.case_id for c in candidate]
    frozen = json.loads((ROOT / "tests/fixtures/starter_manual_diagnostic_36.json").read_text())
    by_id = {c.case_id: c for c in candidate}
    for row in frozen["rows"]:
        if row["case_id"] not in {"OM-044", "OM-046"}:
            continue
        case = by_id[row["case_id"]]
        result = grading.evaluate(
            answer=row["answer"],
            assertions=list(case.assertions),
            references=list(case.reference_evidence),
            evidence=[],
            citations=row["citations"],
        )
        assert result["hard_failure"]
