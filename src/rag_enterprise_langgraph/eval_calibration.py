"""Additional fail-closed requirements for revised-suite baseline candidates."""

from __future__ import annotations

from typing import Any


class CalibrationError(ValueError):
    pass


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
    for case_id in ("OM-044", "OM-046"):
        if by_id[case_id].get("eval_status") != "pass":
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
