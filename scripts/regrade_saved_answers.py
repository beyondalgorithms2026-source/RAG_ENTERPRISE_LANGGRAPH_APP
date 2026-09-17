"""Regrade public-synthetic STARTER fixtures offline, without generating answers."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from rag_enterprise_langgraph import eval_assertions
from rag_enterprise_langgraph.demo_proof import redact_for_sharing
from rag_enterprise_langgraph.eval_judge import judge
from rag_enterprise_langgraph.eval_runner import _typed_order, read_eval_json


async def regrade(pack: Path, fixture: dict, *, semantic_judge=None, use_judge=False) -> dict:
    cases = {case.case_id: case for case in read_eval_json(pack)}
    rows = []
    for saved in fixture["rows"]:
        case = cases[saved["case_id"]]
        answer = saved.get("answer") or saved.get("generated_answer") or ""
        result = eval_assertions.evaluate(
            answer=answer,
            evidence=saved.get("evidence", []),
            citations=saved.get("citations", []),
            assertions=list(case.assertions),
            references=list(case.reference_evidence),
        )
        unresolved_polarity = {
            a["id"]
            for a in result["assertions"]
            if a["type"] == "polarity" and a["state"] == "uncertain"
        }
        concepts = [
            a for a in case.assertions if a["type"] == "concept" or a["id"] in unresolved_polarity
        ]
        error = (
            "starter_infrastructure_failure"
            if saved.get("failure_class") == "infrastructure"
            else None
        )
        metadata = None
        no_grounded_answer = saved.get("grounding_status") in {"not_found", "not_grounded"}
        if (
            use_judge
            and concepts
            and not result["hard_failure"]
            and not error
            and not no_grounded_answer
        ):
            try:
                response = await (semantic_judge or judge)(
                    question=case.question,
                    answer=answer,
                    assertions=concepts,
                    references=list(case.reference_evidence),
                    citations=saved.get("citations", []),
                )
                eval_assertions.apply_judgement(
                    result,
                    response["judgement"],
                    answer=answer,
                    references=list(case.reference_evidence),
                    assertions=concepts,
                )
                metadata = {"model": response.get("model"), "usage": response.get("usage", {})}
            except Exception as exc:
                error = "offline_judge_infrastructure_failure"
                metadata = {
                    "failure_reason": str(exc)
                    if isinstance(exc, eval_assertions.AssertionError)
                    else "judge_transport_or_response_failure"
                }
        required = [a for a in result["assertions"] if a["required"]]
        order = _typed_order(answer, case, result)
        answer_status = (
            "fail"
            if result["hard_failure"]
            or any(a["state"] in {"missing", "contradicted"} for a in required)
            or order is False
            else (
                "manual_review"
                if error
                or any(a["state"] == "uncertain" for a in required)
                or (case.ordered_fact_ids and order is None)
                else "pass"
            )
        )
        if any(a["state"] == "contradicted" for a in result["assertions"]):
            answer_status = "fail"
        if no_grounded_answer and not case.expect_refusal:
            answer_status = "fail"
        if case.expect_refusal:
            safe_text = (
                answer.strip()
                .casefold()
                .startswith(
                    (
                        "not found in provided sources",
                        "not found in the provided sources",
                        "i couldn't find",
                        "i could not find",
                    )
                )
            )
            answer_status = (
                "pass"
                if safe_text
                and not saved.get("citations")
                and saved.get("backend_answer_path") == "not_found"
                else "fail"
            )
        rows.append(
            {
                "case_id": case.case_id,
                "original_question": saved.get("question"),
                "revised_question": case.question,
                "answer": answer,
                "question_changed": saved.get("question") != case.question,
                "temporary_checker_pass": saved.get("temporary_checker_pass"),
                "canonical_answer_match": saved.get("canonical_answer_match"),
                "canonical_order_match": saved.get("canonical_order_match"),
                "revised_answer_status": answer_status,
                "typed": result,
                "ordered_complete": order,
                "judge_metadata": metadata,
                "failure_class": "infrastructure" if error else None,
                "human_label": saved.get("human_label", "not_reviewed"),
            }
        )
    return redact_for_sharing(
        {
            "scope": "starter-only-saved-answer-regrade",
            "grounding_reproduced": False,
            "baseline_eligible": False,
            "grader_version": eval_assertions.GRADER_VERSION,
            "suite_version": next(iter(cases.values())).suite_version,
            "limitation": "No new answers generated. Missing live context/grounding is not inferred. Changed questions require new runs.",
            "rows": rows,
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--semantic-judge", action="store_true")
    parser.add_argument("--case-id", action="append")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("refusing to overwrite a saved comparison")
    fixture = json.loads(args.fixture.read_text())
    if args.case_id:
        fixture["rows"] = [r for r in fixture["rows"] if r["case_id"] in args.case_id]
    report = asyncio.run(regrade(args.pack, fixture, use_judge=args.semantic_judge))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Regraded {len(report['rows'])} saved answers; not a live or baseline-eligible result.")
    return 2 if any(r["failure_class"] == "infrastructure" for r in report["rows"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
