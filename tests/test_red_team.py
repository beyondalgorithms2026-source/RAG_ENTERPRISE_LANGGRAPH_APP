from __future__ import annotations

from rag_enterprise_langgraph.red_team import (
    CHECKS,
    load_findings,
    render_red_team_markdown,
    run_red_team,
)


def test_red_team_findings_file_parses_with_all_checks_registered():
    findings = load_findings()
    assert len(findings) == 10
    for finding in findings:
        for key in ("finding_id", "scenario", "category", "expected_defense", "check", "check_type", "linked_test"):
            assert finding.get(key), f"{finding.get('finding_id')} missing {key}"
        assert finding["check"] in CHECKS


def test_red_team_run_produces_honest_statuses():
    report = run_red_team()
    assert report["total"] == 10
    assert report["failed"] == 0
    assert report["overall_status"] == "pass"
    by_id = {finding["finding_id"]: finding for finding in report["findings"]}
    assert by_id["RT-06"]["status"] == "requires_backend"
    deterministic = [finding for finding in report["findings"] if finding["check_type"] == "deterministic"]
    assert all(finding["status"] == "defended" for finding in deterministic)
    assert all(finding["actual_result"] for finding in report["findings"])


def test_red_team_markdown_rendering():
    report = run_red_team()
    markdown = render_red_team_markdown(report)
    assert "| # | Scenario | Expected Defense | Actual Result | Status | Linked Test/Source |" in markdown
    assert "RT-01" in markdown
    assert "requires_backend" in markdown
    assert "not simulated" in markdown


def test_prompt_injection_snippet_is_rejected_as_evidence():
    status, _ = CHECKS["prompt_injection_in_retrieved_text"]()
    assert status == "defended"


def test_missing_citations_triggers_recovery():
    status, _ = CHECKS["missing_citations"]()
    assert status == "defended"


def test_irrelevant_citation_is_rejected():
    status, _ = CHECKS["irrelevant_citation"]()
    assert status == "defended"


def test_exact_numeric_mismatch_fails_eval():
    status, _ = CHECKS["exact_numeric_mismatch"]()
    assert status == "defended"


def test_unsupported_list_items_flagged():
    status, _ = CHECKS["unsupported_list_items"]()
    assert status == "defended"


def test_backend_timeout_classified():
    status, _ = CHECKS["backend_timeout"]()
    assert status == "defended"


def test_backend_auth_failure_classified():
    status, _ = CHECKS["backend_auth_failure"]()
    assert status == "defended"


def test_high_risk_question_flagged_for_approval():
    status, _ = CHECKS["high_risk_requires_approval"]()
    assert status == "defended"


def test_rule_override_snippet_rejected_and_scrubbed():
    status, _ = CHECKS["retrieved_text_overrides_rules"]()
    assert status == "defended"
