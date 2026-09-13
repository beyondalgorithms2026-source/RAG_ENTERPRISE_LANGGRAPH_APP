from __future__ import annotations

import json

import pytest

from scripts.generate_evaluation_report import (
    REPO,
    _read_approved_baseline,
    build_public_status,
    render_html,
    write_public_report,
)


def _red_team() -> dict:
    return {
        "total": 20,
        "defended": 18,
        "failed": 0,
        "requires_backend": 2,
        "overall_status": "pass",
    }


def test_public_status_is_sanitized_and_tied_to_approved_baseline():
    baseline_path = REPO / "config/eval-baselines/northwind-openai-v1.json"
    baseline = _read_approved_baseline(baseline_path)
    status = build_public_status(
        baseline,
        _red_team(),
        baseline_path=baseline_path,
        generated_at="2026-09-13T00:00:00+00:00",
    )
    assert status["quality"] == {
        "total": 25,
        "passed": 25,
        "failed": 0,
        "manual_review": 0,
        "strict_refusal_total": 5,
        "strict_refusal_passed": 5,
    }
    assert status["governance"]["rt06"] == "pass"
    assert status["configuration"]["llm"]["model"] == "gpt-4o-mini-2024-07-18"
    encoded = json.dumps(status)
    for prohibited in (
        '"generated_answer":',
        '"question":',
        '"error":',
        '"api_key":',
        '"password":',
    ):
        assert prohibited not in encoded.lower()


def test_report_renders_current_evidence_without_stale_claims():
    baseline_path = REPO / "config/eval-baselines/northwind-openai-v1.json"
    status = build_public_status(
        _read_approved_baseline(baseline_path),
        _red_team(),
        baseline_path=baseline_path,
        generated_at="2026-09-13T00:00:00+00:00",
    )
    page = render_html(status)
    assert "25/25" in page
    assert "5/5" in page
    assert "live denied + authorized RT-06 control" in page
    assert "gpt-4o-mini-2024-07-18" in page
    assert "public synthetic Operations Manual v3.2" in page
    assert "90-case v2 suite is under" in page
    for stale in (
        "17 of 25",
        "114 tests",
        "requires_backend by design",
        "deployment does not yet",
    ):
        assert stale not in page


def test_report_writer_creates_matching_status_and_html(tmp_path):
    html_path = tmp_path / "index.html"
    status_path = tmp_path / "status.json"
    status = write_public_report(
        baseline_path=REPO / "config/eval-baselines/northwind-openai-v1.json",
        html_path=html_path,
        status_path=status_path,
        generated_at="2026-09-13T00:00:00+00:00",
    )
    assert json.loads(status_path.read_text(encoding="utf-8")) == status
    assert "Approved full-stack evidence" in html_path.read_text(encoding="utf-8")


def test_unapproved_baseline_is_rejected(tmp_path):
    path = tmp_path / "baseline.json"
    path.write_text(
        json.dumps({"baseline_approval": {"status": "candidate"}, "rows": [{}]}),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="unapproved"):
        _read_approved_baseline(path)
