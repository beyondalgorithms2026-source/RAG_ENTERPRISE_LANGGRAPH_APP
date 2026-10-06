"""Additional fail-closed requirements for revised-suite baseline candidates."""

from __future__ import annotations

from typing import Any


class CalibrationError(ValueError):
    pass


MANDATORY_CORRECT_CASES = ("OM-044", "OM-046")

# Owner decision, 6 October 2026: a mandatory case may count as human review only when the
# answer is not shown wrong and the judge's quotes could not be verified. A stronger judge
# model was considered and deliberately not adopted for now. Record:
# docs/V2_CALIBRATION_2026-10-05.md.
HUMAN_REVIEW_EXCEPTIONS = {
    "OM-044": (
        "OM-044 counted as human review: the answer was not shown wrong, but the "
        "gpt-4o-mini judge's quotes could not be verified. A better judge model is needed "
        "to grade this case automatically; adopting one was deferred by the owner "
        "(6 October 2026)."
    ),
    "OM-046": (
        "OM-046 counted as human review: the answer was not shown wrong, but the "
        "gpt-4o-mini judge's quotes could not be verified. A better judge model is needed "
        "to grade this case automatically; adopting one was deferred by the owner "
        "(6 October 2026)."
    ),
}


def _judge_quoting_only(row: dict[str, Any]) -> bool:
    """Manual review caused only by unverifiable judge quotes, with nothing shown wrong."""
    expected = row.get("expected_eval") or {}
    typed = expected.get("typed") or {}
    return (
        row.get("eval_status") == "manual_review"
        and bool(expected.get("judge_unverifiable"))
        and not expected.get("judge_error")
        and not expected.get("forbidden_fact_matches")
        and not typed.get("hard_failure")
        and not any(
            assertion.get("state") in {"missing", "contradicted"}
            for assertion in typed.get("assertions", [])
        )
    )


def calibration_remarks(report: dict[str, Any]) -> list[str]:
    """Remarks for every human-review exception a valid report relied on."""
    by_id = {row.get("case_id"): row for row in report.get("rows") or [] if isinstance(row, dict)}
    return [
        remark
        for case_id, remark in HUMAN_REVIEW_EXCEPTIONS.items()
        if case_id in by_id
        and by_id[case_id].get("eval_status") != "pass"
        and _judge_quoting_only(by_id[case_id])
    ]


def validate_correction_report(report: dict[str, Any], expected_ids: set[str]) -> None:
    if report.get("scope", "full-stack") != "full-stack":
        raise CalibrationError(
            "STARTER-only or saved-answer runs cannot form a full-stack baseline"
        )
    rows = report.get("rows")
    if not isinstance(rows, list) or len(rows) != 90 or report.get("total") != 90:
        raise CalibrationError("revised calibration requires exactly 90 cases")
    if any(not isinstance(row, dict) for row in rows):
        raise CalibrationError("malformed calibration row")
    ids = [row.get("case_id") for row in rows]
    if (
        any(not isinstance(case_id, str) for case_id in ids)
        or len(set(ids)) != 90
        or set(ids) != expected_ids
    ):
        raise CalibrationError("revised calibration case IDs are missing, duplicated or changed")
    if report.get("refusal_total") != 8 or report.get("refusal_passed") != 8:
        raise CalibrationError("all five original and three manual refusals must pass")
    if any(row.get("failure_class") == "infrastructure" for row in rows):
        raise CalibrationError("infrastructure failures do not count")
    by_id = {row["case_id"]: row for row in rows}
    for case_id in [f"NW-{n:03}" for n in range(21, 26)] + ["OM-075", "OM-080", "OM-082"]:
        if by_id[case_id].get("eval_status") != "pass":
            raise CalibrationError(f"mandatory refusal failed: {case_id}")
    for case_id in MANDATORY_CORRECT_CASES:
        row = by_id[case_id]
        if row.get("eval_status") == "pass":
            continue
        if case_id in HUMAN_REVIEW_EXCEPTIONS and _judge_quoting_only(row):
            continue
        raise CalibrationError(f"mandatory correctness blocker: {case_id}")
    for row in rows:
        if row.get("eval_status") not in {"pass", "fail", "manual_review"}:
            raise CalibrationError("unknown calibration classification")
    configuration = report.get("configuration", {})
    for key in (
        "grader_version",
        "suite_version",
        "app_prompts",
        "starter_prompts",
        "corpus_manifest_sha256",
    ):
        if not configuration.get(key):
            raise CalibrationError(f"revised calibration requires {key}")
    if report.get("rt06", {}).get("status") != "pass":
        raise CalibrationError("RT-06 must pass in every counted run")
