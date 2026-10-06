"""Judge spans for facts the question supplies, and recording of rejected spans."""

from __future__ import annotations

import json
from io import StringIO

import pytest

from rag_enterprise_langgraph import eval_assertions as grading
from rag_enterprise_langgraph import eval_judge

QUESTION = (
    "A chilled room briefly reads +9°C for four minutes then returns to +6°C. "
    "Is that a Temperature Excursion?"
)
ANSWER = (
    "No, a Temperature Excursion is any temperature outside the required range for more "
    "than 5 consecutive minutes, and the room only read +9°C for four minutes."
)
REFS = [
    {
        "id": "controlled-4",
        "document": "manual",
        "section": "1.2",
        "text": "Temperature Excursion: outside the required range for more than 5 consecutive minutes.",
    }
]


def _assertion(fact_id: str, phrase: str, *, question_sourced: bool = False) -> dict:
    item = {"id": fact_id, "type": "concept", "any_of": [phrase], "source_refs": ["controlled-4"]}
    return {**item, "question_sourced": True} if question_sourced else item


def _response(rows):
    content = json.dumps({"assertions": rows})
    return StringIO(
        json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": content}}]})
    )


def _payload(assertions):
    return grading.judge_payload(
        question=QUESTION, answer=ANSWER, assertions=assertions, references=REFS, citations=[]
    )


DURATION_ROW = {
    "state": "supported",
    "answer_span": "the room only read +9°C for four minutes",
    "evidence_span": "+9°C for four minutes",
    "explanation": "The duration comes from the question.",
}


def test_question_sourced_fact_may_be_proven_from_the_question(monkeypatch):
    monkeypatch.setenv("EVAL_OPENAI_API_KEY", "unit-test-only")
    assertions = [_assertion("duration", "four minutes", question_sourced=True)]
    monkeypatch.setattr(
        eval_judge.urllib.request,
        "urlopen",
        lambda request, timeout: _response({"assertion_0": DURATION_ROW}),
    )
    response = eval_judge._request(_payload(assertions))
    graded = grading.evaluate(
        answer=ANSWER, evidence=[], citations=[], assertions=assertions, references=REFS
    )
    grading.apply_judgement(
        graded,
        response["judgement"],
        answer=ANSWER,
        references=REFS,
        assertions=assertions,
        question=QUESTION,
    )
    assert graded["assertions"][0]["state"] == "supported"
    assert graded["assertions"][0]["evidence_span"] == "+9°C for four minutes"


def test_a_document_fact_still_needs_a_document_quote(monkeypatch):
    monkeypatch.setenv("EVAL_OPENAI_API_KEY", "unit-test-only")
    monkeypatch.setattr(eval_judge.time, "sleep", lambda seconds: None)
    assertions = [_assertion("duration", "four minutes")]  # not question-sourced
    monkeypatch.setattr(
        eval_judge.urllib.request,
        "urlopen",
        lambda request, timeout: _response({"assertion_0": DURATION_ROW}),
    )
    with pytest.raises(eval_judge.JudgeInfrastructureError) as raised:
        eval_judge._request(_payload(assertions))
    assert raised.value.last_reason == "invalid scoped evidence span"
    # B: every attempt's rejected quote is kept for diagnosis.
    spans = raised.value.rejected_spans
    assert len(spans) == eval_judge.MAX_ATTEMPTS
    assert spans[0] == {
        "assertion_id": "duration",
        "state": "supported",
        "answer_span": "the room only read +9°C for four minutes",
        "evidence_span": "+9°C for four minutes",
        "reason": "invalid scoped evidence span",
    }
    # apply_judgement applies the same rule without the question exemption.
    graded = grading.evaluate(
        answer=ANSWER, evidence=[], citations=[], assertions=assertions, references=REFS
    )
    with pytest.raises(grading.AssertionError):
        grading.apply_judgement(
            graded,
            {"assertions": [{"id": "duration", **DURATION_ROW}]},
            answer=ANSWER,
            references=REFS,
            assertions=assertions,
            question=QUESTION,
        )


def test_rejected_spans_are_bounded(monkeypatch):
    monkeypatch.setenv("EVAL_OPENAI_API_KEY", "unit-test-only")
    monkeypatch.setattr(eval_judge.time, "sleep", lambda seconds: None)
    row = {**DURATION_ROW, "answer_span": "x" * 5000}
    monkeypatch.setattr(
        eval_judge.urllib.request,
        "urlopen",
        lambda request, timeout: _response({"assertion_0": row}),
    )
    with pytest.raises(eval_judge.JudgeInfrastructureError) as raised:
        eval_judge._request(
            _payload([_assertion("duration", "four minutes", question_sourced=True)])
        )
    assert raised.value.last_reason == "invalid literal answer span"
    assert all(len(span["answer_span"]) == 300 for span in raised.value.rejected_spans)


def test_retry_after_a_rejected_quote_tells_the_judge_why(monkeypatch):
    monkeypatch.setenv("EVAL_OPENAI_API_KEY", "unit-test-only")
    monkeypatch.setattr(eval_judge.time, "sleep", lambda seconds: None)
    stitched = {
        "state": "supported",
        "answer_span": "more than 5 consecutive minutes",
        # One-word pieces: still rejected under the elided-quote rule.
        "evidence_span": "Excursion...minutes.",
        "explanation": "Definition threshold.",
    }
    contiguous = {**stitched, "evidence_span": "for more than 5 consecutive minutes."}
    requests = []

    def transport(request, timeout):
        requests.append(json.loads(request.data))
        return _response({"assertion_0": stitched if len(requests) == 1 else contiguous})

    monkeypatch.setattr(eval_judge.urllib.request, "urlopen", transport)
    response = eval_judge._request(_payload([_assertion("threshold", "5 consecutive minutes")]))

    assert response["judgement"]["assertions"][0]["evidence_span"] == contiguous["evidence_span"]
    assert len(requests) == 2
    assert len(requests[0]["messages"]) == 2
    feedback = requests[1]["messages"][-1]["content"]
    assert "invalid scoped evidence span" in feedback and "no ellipses" in feedback


ROW = (
    "### 1.2 Definitions\n\n|Term|Defined meaning|\n|---|---|\n"
    "|Temperature Excursion|Any recorded, observed or suspected temperature outside the "
    "required range for a Cold Chain Product for more than 5 consecutive minutes.|\n"
    "|Quarantine|Physical and system hold preventing release.|"
)


@pytest.mark.parametrize(
    ("quote", "accepted"),
    [
        ("Temperature Excursion...for more than 5 consecutive minutes.", True),  # within one row
        ("Temperature Excursion … for more than 5 consecutive minutes.", True),  # unicode ellipsis
        ("Temperature Excursion...Physical and system hold", False),  # joins two rows
        ("for more than 5 consecutive minutes...Temperature Excursion", False),  # out of order
        ("Temperature Excursion...for over 5 consecutive minutes.", False),  # paraphrased piece
        ("Excursion...minutes.", False),  # one-word pieces
        ("Temperature Excursion...Any recorded...outside the required...more than 5", False),
    ],
)
def test_elided_evidence_quotes_must_be_literal_ordered_and_in_one_row(quote, accepted):
    assert (grading._elided_span(ROW, quote) is not None) is accepted


def test_answer_quotes_are_never_elided():
    answer = "No, a Temperature Excursion lasts more than 5 consecutive minutes."
    assert grading._answer_span(answer, "Temperature Excursion...5 consecutive minutes.") is None
