from __future__ import annotations

import pytest

from scripts.combine_eval_reports import CombinedReportError, combine_reports


def _report(prefix: str, count: int, *, schema_version: str) -> dict:
    rows = []
    for index in range(1, count + 1):
        expectation = "refuse" if prefix == "NW" and index > 20 else "answer"
        if prefix == "OM" and index in {61, 62}:
            expectation = "safe_boundary"
        if prefix == "OM" and index > 62:
            expectation = "refuse"
        rows.append(
            {
                "case_id": f"{prefix}-{index:03d}",
                "eval_status": "pass",
                "expectation": expectation,
                "failure_class": None,
            }
        )
    return {
        "schema_version": schema_version,
        "eval_set": prefix,
        "configuration": {"phase": prefix},
        "status": "pass",
        "rows": rows,
    }


def test_combines_two_isolated_phases_into_90_case_report():
    report = combine_reports(
        _report("NW", 25, schema_version="1.0"), _report("OM", 65, schema_version="1.1")
    )
    assert report["total"] == report["passed"] == 90
    assert report["failed"] == report["manual_review"] == 0
    assert report["refusal_total"] == report["refusal_passed"] == 8
    assert report["safe_boundary_total"] == report["safe_boundary_passed"] == 2
    assert report["status"] == "pass"
    assert report["configuration"]["evaluation_phases"]["core"] == {"phase": "NW"}
    assert {row["evaluation_phase"] for row in report["rows"]} == {
        "core",
        "operations-manual",
    }


def test_rejects_wrong_phase_size_or_duplicate_case_id():
    with pytest.raises(CombinedReportError, match="exactly 65"):
        combine_reports(
            _report("NW", 25, schema_version="1.0"), _report("OM", 64, schema_version="1.1")
        )
    manual = _report("OM", 65, schema_version="1.1")
    manual["rows"][0]["case_id"] = "NW-001"
    with pytest.raises(CombinedReportError, match="duplicate"):
        combine_reports(_report("NW", 25, schema_version="1.0"), manual)
