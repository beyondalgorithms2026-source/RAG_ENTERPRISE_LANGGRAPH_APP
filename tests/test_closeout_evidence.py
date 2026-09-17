from __future__ import annotations

from scripts.generate_red_team_release import build_release
from scripts.merge_saved_regrade import merge


def test_merge_saved_regrade_replaces_only_named_rows_and_recomputes_infrastructure():
    rows = [
        {
            "case_id": f"C-{index:03}",
            "eval_status": "pass",
            "failure_class": None,
            "grounding_status": "verified",
            "expected_eval": {},
        }
        for index in range(90)
    ]
    rows[3].update(
        eval_status="fail",
        failure_class="infrastructure",
        expected_eval={"judge_error": "offline_judge_infrastructure_failure"},
    )
    report = {"rows": rows, "rt06": {"status": "pass"}, "rt16": {"status": "pass"}}
    revised = merge(
        report,
        {
            "rows": [
                {
                    "case_id": "C-003",
                    "typed": {"assertions": []},
                    "judge_metadata": {"model": "pinned"},
                    "revised_answer_status": "manual_review",
                    "failure_class": None,
                }
            ]
        },
    )
    assert revised["grader_failures"] == 0
    assert revised["infrastructure_failures"] == 0
    assert revised["manual_review"] == 1
    assert revised["release_notes"]["answers_regenerated"] is False


def test_red_team_release_has_18_deterministic_and_two_live_controls():
    release = build_release(
        {
            "rt06": {"status": "pass"},
            "rt16": {"status": "pass"},
            "configuration": {"workflow": {"url": "https://example.test/run"}},
        }
    )
    assert release["total"] == 20
    assert release["defended"] == 20
    assert release["deterministic_verified"] == 18
    assert release["live_verified"] == 2
    assert release["requires_backend"] == 0
