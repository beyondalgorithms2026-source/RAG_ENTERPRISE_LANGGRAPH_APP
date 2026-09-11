from __future__ import annotations

from typing import Any


class BaselineError(ValueError):
    """An evaluation report cannot be compared safely."""


def _rows(report: dict[str, Any], label: str) -> dict[str, dict[str, Any]]:
    rows = report.get("rows")
    if not isinstance(rows, list) or not rows:
        raise BaselineError(f"{label} report has no rows")
    mapped: dict[str, dict[str, Any]] = {}
    for row in rows:
        case_id = str(row.get("case_id") or "").strip() if isinstance(row, dict) else ""
        if not case_id:
            raise BaselineError(f"{label} report contains a row without case_id")
        if case_id in mapped:
            raise BaselineError(f"{label} report contains duplicate case_id: {case_id}")
        mapped[case_id] = row
    return mapped


def compare_eval_reports(baseline: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(baseline.get("configuration"), dict) or not baseline["configuration"]:
        raise BaselineError("baseline configuration metadata is required")
    if not isinstance(current.get("configuration"), dict) or not current["configuration"]:
        raise BaselineError("current configuration metadata is required")
    baseline_rows = _rows(baseline, "baseline")
    current_rows = _rows(current, "current")
    if set(baseline_rows) != set(current_rows):
        missing = sorted(set(baseline_rows) - set(current_rows))
        added = sorted(set(current_rows) - set(baseline_rows))
        raise BaselineError(f"case ids changed; missing={missing}, added={added}")

    regressions: list[dict[str, str]] = []
    for case_id, before in baseline_rows.items():
        after = current_rows[case_id]
        if after.get("failure_class") == "infrastructure":
            regressions.append({"case_id": case_id, "rule": "infrastructure_failure"})
        if after.get("expect_refusal") and after.get("eval_status") != "pass":
            regressions.append({"case_id": case_id, "rule": "must_refuse_failed"})
        if before.get("eval_status") == "pass" and after.get("eval_status") != "pass":
            regressions.append({"case_id": case_id, "rule": "prior_pass_regressed"})
        if (
            before.get("expected_document_matched") is True
            and after.get("expected_document_matched") is not True
        ):
            regressions.append({"case_id": case_id, "rule": "expected_document_regressed"})

    for metric, direction in (
        ("passed", "minimum"),
        ("failed", "maximum"),
        ("manual_review", "maximum"),
    ):
        before_value = int(baseline.get(metric, 0))
        after_value = int(current.get(metric, 0))
        regressed = (
            after_value < before_value if direction == "minimum" else after_value > before_value
        )
        if regressed:
            regressions.append({"case_id": "aggregate", "rule": f"{metric}_{direction}"})

    if int(current.get("refusal_passed", 0)) != int(current.get("refusal_total", 0)):
        regressions.append({"case_id": "aggregate", "rule": "refusal_zero_tolerance"})
    if int(current.get("infrastructure_failures", 0)):
        regressions.append({"case_id": "aggregate", "rule": "infrastructure_zero_tolerance"})

    return {
        "schema_version": "1.0",
        "status": "pass" if not regressions else "fail",
        "regression_count": len(regressions),
        "regressions": regressions,
    }
