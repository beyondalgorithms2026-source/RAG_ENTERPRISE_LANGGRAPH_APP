from __future__ import annotations

from scripts.generate_candidate_evidence import build_status, render


def report():
    rows = [
        {"case_id": f"C-{index:03}", "eval_status": "pass", "expectation": "answer"}
        for index in range(90)
    ]
    rows[0]["eval_status"] = "fail"
    rows[1]["eval_status"] = "manual_review"
    return {
        "total": 90,
        "passed": 88,
        "failed": 1,
        "manual_review": 1,
        "refusal_total": 8,
        "refusal_passed": 7,
        "safe_boundary_total": 2,
        "safe_boundary_passed": 2,
        "transport_failures": 0,
        "grader_failures": 0,
        "other_infrastructure_failures": 0,
        "infrastructure_failures": 0,
        "rt06": {"status": "pass"},
        "rt16": {"status": "pass"},
        "rows": rows,
    }


def test_candidate_status_and_html_derive_counts_and_limitations_from_report():
    status = build_status(report(), source_name="eval-report.json", source_sha256="abc")
    assert status["evidence_status"] == "provisional"
    assert status["approved_baseline"] == {"id": "northwind-openai-v1", "case_count": 25}
    assert status["quality"]["passed"] == 88
    assert status["limitations"]["failed_case_ids"] == ["C-000"]
    assert status["limitations"]["manual_review_case_ids"] == ["C-001"]
    page = render(status)
    assert "88" in page and "C-000" in page and "not calibration" in page


def test_candidate_status_rejects_incomplete_or_inconsistent_run():
    broken = report()
    broken["rows"].pop()
    try:
        build_status(broken, source_name="bad.json", source_sha256="abc")
    except ValueError as exc:
        assert "exactly 90" in str(exc)
    else:
        raise AssertionError("incomplete report accepted")
