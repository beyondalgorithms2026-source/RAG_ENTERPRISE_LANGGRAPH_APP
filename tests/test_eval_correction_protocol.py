from __future__ import annotations

import asyncio
import copy
import io
import json
from pathlib import Path

import pytest

from rag_enterprise_langgraph import eval_assertions as grading
from rag_enterprise_langgraph import eval_judge
from rag_enterprise_langgraph.eval_calibration import CalibrationError, validate_correction_report
from rag_enterprise_langgraph.eval_runner import (
    EvalSetError,
    _eval_status,
    _typed_order,
    read_eval_json,
)
from scripts.regrade_saved_answers import regrade

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "config/eval-set-operations-manual-v3.2-candidate.json"


def test_judge_schema_requires_known_ids_and_actual_table_quotes(monkeypatch):
    monkeypatch.setenv("EVAL_OPENAI_API_KEY", "unit-test-placeholder")
    answer = "Band 6+ approves."
    reference = "|Authority|Deadline|\n|Band 6+|Three days|"

    def respond(request, timeout):
        body = json.loads(request.data)
        schema = body["response_format"]["json_schema"]["schema"]
        assertions = schema["properties"]["assertions"]
        assert assertions["required"] == ["authority"]
        row = assertions["properties"]["authority"]
        quotes = row["properties"]["evidence_span"]["enum"]
        assert "|Band 6+|Three days|" in quotes
        assert "Authority|Band 6+" not in quotes
        content = {
            "assertions": {
                "authority": {
                    "state": "supported",
                    "answer_span": answer,
                    "evidence_span": "|Band 6+|Three days|",
                    "explanation": "Correct approval authority.",
                }
            }
        }
        return io.BytesIO(
            json.dumps(
                {
                    "choices": [
                        {"finish_reason": "stop", "message": {"content": json.dumps(content)}}
                    ]
                }
            ).encode()
        )

    monkeypatch.setattr(eval_judge.urllib.request, "urlopen", respond)
    payload = grading.judge_payload(
        question="Who approves?",
        answer=answer,
        assertions=[{"id": "authority", "type": "concept"}],
        references=[{"id": "r", "text": reference}],
        citations=[],
    )
    result = eval_judge._request(payload)
    assert result["judgement"]["assertions"][0]["id"] == "authority"


def test_90_candidate_cases_preserve_five_original_refusals():
    core = read_eval_json(ROOT / "config/eval-set-northwind-candidate.json")
    manual = read_eval_json(PACK)
    assert len(core) == 25 and len(manual) == 65
    assert len({c.case_id for c in core + manual}) == 90
    assert [c.case_id for c in core if c.expect_refusal] == [f"NW-{n:03}" for n in range(21, 26)]


def test_minor_incident_question_explicitly_requests_elapsed_deadline_without_lowering_it():
    case = next(c for c in read_eval_json(PACK) if c.case_id == "OM-085")
    assert "elapsed hours" in case.question
    assert "Spanish or Belgian public holiday" in case.question
    deadline = next(a for a in case.assertions if a["id"] == "deadline")
    assert deadline["type"] == "numeric"
    assert deadline["required"] is True
    assert deadline["value"] == "24"
    assert "within 24 hours" in " ".join(r["text"] for r in case.reference_evidence)


def test_saved_minor_incident_answer_cannot_pass_with_belgian_holiday_exception():
    case = next(c for c in read_eval_json(PACK) if c.case_id == "OM-085")
    result = grading.evaluate(
        answer=(
            "A Minor incident must be reported within 24 hours of discovery [S5]. "
            "A Spanish public holiday does not extend that deadline unless it is also "
            "a Belgian public holiday [S1]."
        ),
        evidence=[],
        citations=[],
        assertions=list(case.assertions),
        references=list(case.reference_evidence),
    )
    states = {a["id"]: a["state"] for a in result["assertions"]}
    assert states["deadline"] == "supported"
    assert states["no_local_delay"] == "contradicted"


@pytest.mark.parametrize(
    "answer,case_id",
    [
        ("Section 6.3.1", "OM-089"),
    ],
)
def test_identifiers_do_not_accept_different_section(answer, case_id):
    case = next(c for c in read_eval_json(PACK) if c.case_id == case_id)
    testing = next(a for a in case.assertions if a["id"] == "testing")
    result = grading.evaluate(
        answer=answer,
        evidence=[],
        citations=[],
        assertions=[testing],
        references=list(case.reference_evidence),
    )
    assert result["hard_failure"]


def test_unresolved_polarity_can_accept_equivalent_negative_grammar():
    references = [
        {
            "id": "r",
            "document": "policy",
            "section": "1",
            "text": "Visual inspection alone is insufficient.",
        }
    ]
    answer = "Visual appearance alone cannot justify release."
    result = grading.evaluate(
        answer=answer,
        evidence=[],
        citations=[],
        assertions=[{"id": "negative", "type": "polarity", "value": "no", "source_refs": ["r"]}],
        references=references,
    )
    assert result["assertions"][0]["state"] == "uncertain"
    grading.apply_judgement(
        result,
        {
            "assertions": [
                {
                    "id": "negative",
                    "state": "supported",
                    "answer_span": answer,
                    "evidence_span": references[0]["text"],
                    "explanation": "Equivalent negative conclusion.",
                }
            ]
        },
        answer=answer,
        references=references,
    )
    assert result["assertions"][0]["state"] == "supported"


def test_missing_order_or_forbidden_claim_cannot_pass():
    case = next(c for c in read_eval_json(PACK) if c.case_id == "OM-072")
    expected = {
        "typed": {"assertions": [{"state": "supported", "required": True}]},
        "ordered_facts_matched": None,
    }
    assert (
        _eval_status(
            {"grounding_status": "verified"}, expected, case, expected_document_matched=True
        )
        == "manual_review"
    )


def test_whole_list_quotes_do_not_prove_or_disprove_order():
    case = next(c for c in read_eval_json(PACK) if c.case_id == "OM-072")
    answer = "Complete list quoted by judge."
    typed = {
        "assertions": [
            {"id": ident, "state": "supported", "answer_span": answer}
            for ident in case.ordered_fact_ids
        ]
    }
    assert _typed_order(answer, case, typed) is None
    expected = {"typed": typed, "ordered_facts_matched": None}
    expected["forbidden_fact_matches"] = ["contradictory claim"]
    assert (
        _eval_status(
            {"grounding_status": "verified"}, expected, case, expected_document_matched=True
        )
        == "fail"
    )


def test_saved_answer_judge_failure_is_infrastructure_not_quality_pass():
    fixture = json.loads((ROOT / "tests/fixtures/starter_manual_diagnostic_36.json").read_text())
    fixture["rows"] = [r for r in fixture["rows"] if r["case_id"] == "OM-064"]

    async def unavailable(**kwargs):
        raise TimeoutError("secret/raw/path must not appear")

    report = asyncio.run(regrade(PACK, fixture, semantic_judge=unavailable, use_judge=True))
    assert report["rows"][0]["failure_class"] == "infrastructure"
    assert report["rows"][0]["revised_answer_status"] != "pass"
    assert "secret/raw/path" not in json.dumps(report)
    assert report["baseline_eligible"] is False


def test_saved_missing_grounded_answer_is_quality_failure_without_judge_call():
    fixture = {
        "rows": [
            {
                "case_id": "OM-064",
                "answer": "Not found in provided sources.",
                "grounding_status": "not_found",
                "citations": [],
                "evidence": [],
            }
        ]
    }

    async def forbidden(**kwargs):
        pytest.fail("An absent answer must not consume a semantic judge call")

    report = asyncio.run(regrade(PACK, fixture, semantic_judge=forbidden, use_judge=True))
    assert report["rows"][0]["revised_answer_status"] == "fail"
    assert report["rows"][0]["failure_class"] is None
    assert report["rows"][0]["judge_metadata"] is None


def test_missing_shared_reference_is_contract_error(tmp_path):
    pack = json.loads(PACK.read_text())
    pack["questions"][0]["reference_ids"].append("nonexistent")
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(pack))
    with pytest.raises(EvalSetError, match="unknown shared reference"):
        read_eval_json(path)


@pytest.mark.parametrize(
    "change",
    ["wrong_critical", "wrong_scope", "missing_case", "zero_refusals", "missing_metadata"],
)
def test_calibration_fails_closed(change):
    ids = {f"NW-{n:03}" for n in range(1, 26)} | {f"OM-{n:03}" for n in range(26, 91)}
    report = {
        "scope": "full-stack",
        "total": 90,
        "refusal_total": 8,
        "refusal_passed": 8,
        "rt06": {"status": "pass"},
        "configuration": {
            k: "present"
            for k in (
                "grader_version",
                "suite_version",
                "app_prompts",
                "starter_prompts",
                "corpus_manifest_sha256",
            )
        },
        "rows": [{"case_id": c, "eval_status": "pass"} for c in sorted(ids)],
    }
    validate_correction_report(copy.deepcopy(report), ids)
    if change == "wrong_critical":
        next(r for r in report["rows"] if r["case_id"] == "OM-044")["eval_status"] = (
            "manual_review"
        )
    elif change == "wrong_scope":
        report["scope"] = "starter-only-live"
    elif change == "missing_case":
        report["rows"].pop()
    elif change == "zero_refusals":
        report["refusal_total"] = report["refusal_passed"] = 0
    else:
        report["configuration"].pop("grader_version")
    with pytest.raises(CalibrationError):
        validate_correction_report(report, ids)
