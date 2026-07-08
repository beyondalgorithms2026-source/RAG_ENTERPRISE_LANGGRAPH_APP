from __future__ import annotations

import json

from rag_enterprise_langgraph.approval import ApprovalStore
from rag_enterprise_langgraph.audit import AuditLog
from rag_enterprise_langgraph.cli import _handle_standalone, build_parser
from rag_enterprise_langgraph.config import Settings


def test_parser_accepts_new_flags():
    parser = build_parser()
    args = parser.parse_args(
        [
            "--require-approval",
            "--approval-risk-mode",
            "always",
            "--reviewer",
            "Alice",
            "--comment",
            "checked",
            "--audit-log",
            "runs/audit-log.jsonl",
            "--save-eval-run",
            "--red-team-output",
            "red-team-report.md",
            "--red-team-json",
            "red-team-results.json",
        ]
    )
    assert args.require_approval is True
    assert args.approval_risk_mode == "always"
    assert args.reviewer == "Alice"
    assert args.comment == "checked"
    assert args.audit_log == "runs/audit-log.jsonl"
    assert args.save_eval_run is True
    assert args.red_team_output == "red-team-report.md"
    assert args.red_team_json == "red-team-results.json"

    listing = parser.parse_args(["--list-approvals"])
    assert listing.list_approvals is True
    assert parser.parse_args(["--approve", "abc"]).approve == "abc"
    assert parser.parse_args(["--reject", "abc"]).reject == "abc"
    assert parser.parse_args(["--show-audit", "run-1"]).show_audit == "run-1"
    assert parser.parse_args(["--export-audit", "run-1"]).export_audit == "run-1"
    assert parser.parse_args(["--eval-runs"]).eval_runs is True
    assert parser.parse_args(["--show-eval-run", "eval-1"]).show_eval_run == "eval-1"
    assert parser.parse_args(["--red-team"]).red_team is True


def _settings(tmp_path) -> Settings:
    return Settings(
        audit_log_path=str(tmp_path / "audit-log.jsonl"),
        approvals_path=str(tmp_path / "approvals.jsonl"),
        eval_runs_dir=str(tmp_path / "eval-runs"),
        red_team_latest_path=str(tmp_path / "red-team-latest.json"),
    )


def test_cli_list_and_approve_flow(tmp_path, capsys):
    settings = _settings(tmp_path)
    store = ApprovalStore(settings.approvals_path)
    record = store.create(question="Q?", answer="A", run_id="run-1")

    parser = build_parser()
    assert _handle_standalone(parser.parse_args(["--list-approvals"]), settings) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed["pending"][0]["approval_id"] == record["approval_id"]

    missing_reviewer = parser.parse_args(["--approve", record["approval_id"]])
    assert _handle_standalone(missing_reviewer, settings) == 2
    capsys.readouterr()

    approve = parser.parse_args(["--approve", record["approval_id"], "--reviewer", "Alice", "--comment", "fine"])
    assert _handle_standalone(approve, settings) == 0
    decided = json.loads(capsys.readouterr().out)
    assert decided["status"] == "approved"
    assert decided["reviewer"] == "Alice"

    event_types = [event["event_type"] for event in AuditLog(settings.audit_log_path).events()]
    assert "approval_approved" in event_types


def test_cli_reject_flow(tmp_path, capsys):
    settings = _settings(tmp_path)
    record = ApprovalStore(settings.approvals_path).create(question="Q?", answer="A")
    args = build_parser().parse_args(["--reject", record["approval_id"], "--reviewer", "Bob"])
    assert _handle_standalone(args, settings) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "rejected"


def test_cli_show_and_export_audit(tmp_path, capsys):
    settings = _settings(tmp_path)
    audit = AuditLog(settings.audit_log_path)
    audit.append(event_type="run_started", run_id="run-9", actor="orchestrator", summary="start")

    parser = build_parser()
    assert _handle_standalone(parser.parse_args(["--show-audit", "run-9"]), settings) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["event_count"] == 1

    assert _handle_standalone(parser.parse_args(["--export-audit", "run-9"]), settings) == 0
    export = json.loads(capsys.readouterr().out)
    assert export["chain_verification"]["valid"] is True

    assert _handle_standalone(parser.parse_args(["--show-audit", "missing"]), settings) == 1
    capsys.readouterr()


def test_cli_eval_run_listing(tmp_path, capsys):
    settings = _settings(tmp_path)
    parser = build_parser()
    assert _handle_standalone(parser.parse_args(["--eval-runs"]), settings) == 0
    assert json.loads(capsys.readouterr().out) == {"eval_runs": []}

    assert _handle_standalone(parser.parse_args(["--show-eval-run", "missing"]), settings) == 1
    capsys.readouterr()


def test_cli_red_team(tmp_path, capsys):
    settings = _settings(tmp_path)
    output_md = tmp_path / "red-team-report.md"
    output_json = tmp_path / "red-team-results.json"
    args = build_parser().parse_args(
        ["--red-team", "--red-team-output", str(output_md), "--red-team-json", str(output_json)]
    )
    assert _handle_standalone(args, settings) == 0
    capsys.readouterr()
    assert output_md.exists()
    assert "Red-Team Findings" in output_md.read_text(encoding="utf-8")
    report = json.loads(output_json.read_text(encoding="utf-8"))
    assert report["total"] == 10
    assert (tmp_path / "red-team-latest.json").exists()
