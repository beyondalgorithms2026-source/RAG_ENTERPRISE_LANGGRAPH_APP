from __future__ import annotations

import asyncio
import json

import pytest

from rag_enterprise_langgraph.eval_baseline import BaselineError, compare_eval_reports
from rag_enterprise_langgraph.eval_runner import EvalSetError, read_eval_json, run_eval
from rag_enterprise_langgraph.orchestrator import OrchestratedRunResult


class _SmokeOrchestrator:
    async def run(self, question: str, **_kwargs):
        if "unknown" in question:
            return OrchestratedRunResult(
                question=question,
                answer="Not found in provided sources.",
                grounding_status="not_found",
                tools_used=["ask_grounded"],
                execution_timeline=[],
                portfolio_safe=True,
            )
        document = "policy-two.md" if "second" in question else "policy-one.md"
        fact = "two days" if "second" in question else "fourteen days"
        return OrchestratedRunResult(
            question=question,
            answer=fact,
            grounding_status="verified",
            tools_used=["ask_grounded"],
            execution_timeline=[],
            citations=[{"file_name": document, "snippet": fact}],
            evidence=[{"file_name": document, "snippet": fact}],
            evidence_count=1,
            citation_count=1,
            portfolio_safe=True,
        )


def _payload():
    return {
        "schema_version": "1.0",
        "eval_set": "smoke",
        "questions": [
            {
                "case_id": "S-1",
                "question": "first",
                "expect_refusal": False,
                "expected_document": "policy-one",
                "expected_fact": "fourteen days",
            },
            {
                "case_id": "S-2",
                "question": "second",
                "expect_refusal": False,
                "expected_document": "policy-two",
                "expected_fact": "two days",
            },
            {
                "case_id": "S-3",
                "question": "unknown",
                "expect_refusal": True,
                "expected_document": None,
                "expected_fact": None,
            },
        ],
    }


def test_three_case_eval_smoke(tmp_path):
    path = tmp_path / "smoke.json"
    path.write_text(json.dumps(_payload()), encoding="utf-8")

    report = asyncio.run(run_eval(eval_path=path, orchestrator=_SmokeOrchestrator()))

    assert report["total"] == 3
    assert report["passed"] == 3
    assert report["refusal_passed"] == report["refusal_total"] == 1
    assert all(row["expected_document_matched"] is not False for row in report["rows"])
    assert report["infrastructure_failures"] == 0


@pytest.mark.parametrize("mutation", ["missing_id", "duplicate", "contradictory_refusal"])
def test_eval_set_rejects_malformed_cases(tmp_path, mutation):
    payload = _payload()
    if mutation == "missing_id":
        payload["questions"][0].pop("case_id")
    elif mutation == "duplicate":
        payload["questions"][1]["case_id"] = "S-1"
    else:
        payload["questions"][2]["expected_fact"] = "invented"
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(EvalSetError):
        read_eval_json(path)


def test_baseline_comparison_blocks_case_and_aggregate_regressions(tmp_path):
    path = tmp_path / "smoke.json"
    path.write_text(json.dumps(_payload()), encoding="utf-8")
    baseline = asyncio.run(run_eval(eval_path=path, orchestrator=_SmokeOrchestrator()))
    current = json.loads(json.dumps(baseline))
    current["rows"][0]["eval_status"] = "fail"
    current["rows"][0]["expected_document_matched"] = False
    current["passed"] -= 1
    current["failed"] += 1

    comparison = compare_eval_reports(baseline, current)

    assert comparison["status"] == "fail"
    assert {item["rule"] for item in comparison["regressions"]} >= {
        "prior_pass_regressed",
        "expected_document_regressed",
        "passed_minimum",
    }


def test_baseline_requires_configuration_metadata():
    with pytest.raises(BaselineError):
        compare_eval_reports({"rows": []}, {"rows": []})
