from __future__ import annotations

import asyncio
import json

import pytest

from rag_enterprise_langgraph.eval_baseline import BaselineError, compare_eval_reports
from rag_enterprise_langgraph.eval_runner import EvalSetError, read_eval_json, run_eval
from rag_enterprise_langgraph.orchestrator import OrchestratedRunResult
from scripts.run_rt06_live import _restricted_marker_count, _restricted_marker_paths


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


class _ReviewInsteadOfRefusalOrchestrator:
    async def run(self, question: str, **_kwargs):
        return OrchestratedRunResult(
            question=question,
            answer="A speculative answer that still requires review.",
            grounding_status="needs_review",
            tools_used=["ask_grounded"],
            execution_timeline=[],
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


def _full_configuration():
    return {
        "repositories": {"app": "a", "mcp": "b", "starter": "c"},
        "llm": {"provider": "openai", "model": "pinned-model"},
        "embedding": {
            "provider": "openai",
            "model": "pinned-embedding",
            "dimensions": "384",
        },
        "chunking": {"policy": "default", "target_words": "320", "overlap_words": "40"},
        "retrieval": {"mode": "hybrid", "rerank_enabled": "false"},
        "orchestration": {
            "max_recovery_steps": 3,
            "expected_fact_scope": "generated_answer",
        },
        "starter_prompts": {"answer": {"version": "1.0.0", "sha256": "abc"}},
        "corpus_manifest_sha256": "def",
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


def test_must_refuse_does_not_accept_needs_review_with_an_answer(tmp_path):
    payload = _payload()
    payload["questions"] = [payload["questions"][2]]
    path = tmp_path / "refusal.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    report = asyncio.run(
        run_eval(eval_path=path, orchestrator=_ReviewInsteadOfRefusalOrchestrator())
    )

    assert report["passed"] == 0
    assert report["failed"] == 1
    assert report["refusal_passed"] == 0


@pytest.mark.parametrize(
    "text",
    [
        "76,000–98,000 EUR",
        "EUR 76 000 to EUR 98 000",
        "compensation-bands-2026.md",
    ],
)
def test_rt06_detects_reformatted_restricted_markers(text):
    assert _restricted_marker_count({"answer": text}) >= 1


def test_rt06_reports_marker_location_without_copying_payload_value():
    paths = _restricted_marker_paths({"tool_outputs": [{"content": "EUR 76,000"}]})

    assert paths == ["76000@$.tool_outputs[0].content"]


def test_rt06_ignores_forbidden_digits_inside_freshness_timestamps():
    payload = {
        "freshness": {
            "last_ingested_at": "2026-09-12T01:04:36.760000+00:00",
            "observed_at": "2026-09-12T01:04:36.76000Z",
        }
    }

    assert _restricted_marker_paths(payload) == []


def test_rt06_still_scans_non_timestamp_values_in_freshness_fields():
    assert _restricted_marker_paths({"freshness": {"observed_at": "EUR 76,000"}}) == [
        "76000@$.freshness.observed_at"
    ]


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
    baseline = asyncio.run(
        run_eval(
            eval_path=path,
            orchestrator=_SmokeOrchestrator(),
            configuration=_full_configuration(),
        )
    )
    baseline["rt06"] = {"status": "pass", "grounding_status": "not_found"}
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


def test_baseline_comparison_blocks_pinned_configuration_or_rt06_change(tmp_path):
    path = tmp_path / "smoke.json"
    path.write_text(json.dumps(_payload()), encoding="utf-8")
    baseline = asyncio.run(
        run_eval(
            eval_path=path,
            orchestrator=_SmokeOrchestrator(),
            configuration=_full_configuration(),
        )
    )
    baseline["rt06"] = {"status": "pass", "grounding_status": "not_found"}
    current = json.loads(json.dumps(baseline))
    current["configuration"]["retrieval"]["mode"] = "vector"
    current["rt06"] = {"status": "acl_failure"}

    comparison = compare_eval_reports(baseline, current)

    assert comparison["status"] == "fail"
    assert {item["rule"] for item in comparison["regressions"]} >= {
        "pinned_configuration_changed",
        "acl_boundary_failed",
    }


def test_baseline_requires_configuration_metadata():
    with pytest.raises(BaselineError):
        compare_eval_reports({"rows": []}, {"rows": []})
