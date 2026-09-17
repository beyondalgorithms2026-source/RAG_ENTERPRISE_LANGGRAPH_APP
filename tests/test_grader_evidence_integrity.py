"""Saved grader defects: factual scope, header pseudo-evidence and atomic updates."""

import copy
import json
from io import StringIO

import pytest

from rag_enterprise_langgraph import eval_assertions as grading
from rag_enterprise_langgraph import eval_judge

REFS = [
    {
        "id": "trigger",
        "document": "manual",
        "section": "1.2",
        "text": "|Term|Defined meaning|\n|---|---|\n|Temperature Excursion|More than five consecutive minutes outside range.|",
    },
    {
        "id": "other",
        "document": "manual",
        "section": "4.1",
        "text": "Quality must approve release.",
    },
]
ASSERTIONS = [
    {
        "id": "trigger",
        "type": "concept",
        "any_of": ["five consecutive minutes"],
        "source_refs": ["trigger"],
    }
]
ANSWER = "Four minutes does not meet the more-than-five-minute trigger."


def result():
    return grading.evaluate(
        answer=ANSWER, evidence=[], citations=[], assertions=ASSERTIONS, references=REFS
    )


def judgement(quote, explanation="The quoted comparison applies the governing duration."):
    return {
        "assertions": [
            {
                "id": "trigger",
                "state": "supported",
                "answer_span": ANSWER,
                "evidence_span": quote,
                "explanation": explanation,
            }
        ]
    }


def test_table_headers_are_not_evidence_choices():
    quotes = grading.factual_quotes(REFS)
    assert "|Term|Defined meaning|" not in quotes
    assert "|---|---|" not in quotes
    assert "|Temperature Excursion|More than five consecutive minutes outside range.|" in quotes


def test_judge_cannot_infer_omitted_material_exception_from_reference():
    answer = "Records are retained for 90 days."
    assertions = [
        {
            "id": "exception",
            "type": "concept",
            "any_of": ["unless an investigation is open"],
            "answer_anchors": [["investigation", "inquiry"]],
            "source_refs": ["policy"],
        }
    ]
    refs = [
        {
            "id": "policy",
            "document": "policy",
            "section": "retention",
            "text": "Records are retained for 90 days unless an investigation is open.",
        }
    ]
    graded = grading.evaluate(
        answer=answer, evidence=[], citations=[], assertions=assertions, references=refs
    )
    assert graded["hard_failure"] is True
    grading.apply_judgement(
        graded,
        {
            "assertions": [
                {
                    "id": "exception",
                    "state": "supported",
                    "answer_span": answer,
                    "evidence_span": refs[0]["text"],
                    "explanation": "Adversarial false positive: reference includes the exception.",
                }
            ]
        },
        answer=answer,
        references=refs,
        assertions=assertions,
    )
    assert graded["assertions"][0]["state"] == "missing"


@pytest.mark.parametrize("anchors", [[[]], ["inquiry"], [[""]]])
def test_invalid_answer_anchor_contracts_are_rejected(anchors):
    with pytest.raises(grading.AssertionError, match="answer anchors"):
        grading.validate([{**ASSERTIONS[0], "answer_anchors": anchors}], REFS)


@pytest.mark.parametrize("quote", ["|Term|Defined meaning|", "Quality must approve release."])
def test_header_and_unrelated_section_cannot_support_assertion(quote):
    before = result()
    snapshot = copy.deepcopy(before)
    with pytest.raises(grading.AssertionError):
        grading.apply_judgement(
            before, judgement(quote), answer=ANSWER, references=REFS, assertions=ASSERTIONS
        )
    assert before == snapshot


def test_empty_explanation_is_not_a_pass():
    with pytest.raises(grading.AssertionError):
        grading.apply_judgement(
            result(),
            judgement("More than five consecutive minutes outside range.", ""),
            answer=ANSWER,
            references=REFS,
            assertions=ASSERTIONS,
        )


def test_invalid_later_judge_row_does_not_partially_change_results():
    assertions = [*ASSERTIONS, {**ASSERTIONS[0], "id": "second"}]
    graded = grading.evaluate(
        answer=ANSWER, evidence=[], citations=[], assertions=assertions, references=REFS
    )
    snapshot = copy.deepcopy(graded)
    response = judgement("More than five consecutive minutes outside range.")
    response["assertions"].append(
        {**response["assertions"][0], "id": "second", "evidence_span": "|Term|Defined meaning|"}
    )
    with pytest.raises(grading.AssertionError):
        grading.apply_judgement(
            graded, response, answer=ANSWER, references=REFS, assertions=assertions
        )
    assert graded == snapshot


def test_valid_contiguous_data_cell_quote_remains_accepted():
    graded = grading.apply_judgement(
        result(),
        judgement("More than five consecutive minutes outside range."),
        answer=ANSWER,
        references=REFS,
        assertions=ASSERTIONS,
    )
    assert graded["assertions"][0]["state"] == "supported"


def test_judge_schema_has_unique_required_fields_and_validates_scoped_quote(monkeypatch):
    monkeypatch.setenv("EVAL_OPENAI_API_KEY", "unit-test-only")

    def transport(request, timeout):
        body = json.loads(request.data)
        schema = body["response_format"]["json_schema"]["schema"]
        assertions_schema = schema["properties"]["assertions"]
        assert assertions_schema["required"] == ["assertion_0"]
        row = assertions_schema["properties"]["assertion_0"]
        assert len(row["required"]) == len(set(row["required"]))
        assert set(row["required"]) == set(row["properties"])
        quote = "More than five consecutive minutes outside range."
        return StringIO(
            json.dumps(
                {
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {
                                "content": json.dumps(
                                    {
                                        "assertions": {
                                        "assertion_0": {
                                                "state": "supported",
                                                "answer_span": ANSWER,
                                            "evidence_span": quote,
                                                "explanation": "Duration comparison.",
                                            }
                                        }
                                    }
                                )
                            },
                        }
                    ]
                }
            )
        )

    monkeypatch.setattr(eval_judge.urllib.request, "urlopen", transport)
    response = eval_judge._request(
        grading.judge_payload(
            question="Does the duration meet the trigger?",
            answer=ANSWER,
            assertions=ASSERTIONS,
            references=REFS,
            citations=[],
        )
    )
    assert response["judgement"]["assertions"][0]["id"] == "trigger"
