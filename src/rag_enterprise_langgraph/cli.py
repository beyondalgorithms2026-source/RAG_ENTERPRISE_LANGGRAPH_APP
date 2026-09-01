from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from rag_enterprise_langgraph.agent import RagEnterpriseAgent
from rag_enterprise_langgraph.approval import ApprovalStore
from rag_enterprise_langgraph.audit import AuditLog
from rag_enterprise_langgraph.config import ConfigError, Settings
from rag_enterprise_langgraph.demo_proof import (
    build_demo_proof,
    render_text_report,
    resolve_demo_questions,
    write_markdown_report,
)
from rag_enterprise_langgraph.eval_runner import render_eval_markdown, run_eval, write_eval_outputs
from rag_enterprise_langgraph.eval_store import EvalStore, build_eval_run_summary
from rag_enterprise_langgraph.orchestrator import EnterpriseRagOrchestrator
from rag_enterprise_langgraph.red_team import render_red_team_markdown, run_red_team, save_latest
from rag_enterprise_langgraph.run_store import RunStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the enterprise LangGraph agent.")
    parser.add_argument("question", nargs="?", help="User question to send to the agent.")
    parser.add_argument("--json", action="store_true", help="Print the full JSON result.")
    parser.add_argument("--check-config", action="store_true", help="Print redacted runtime diagnostics and loaded MCP tool names.")
    parser.add_argument("--demo-proof", action="store_true", help="Run the editable portfolio demo proof flow.")
    parser.add_argument("--output", help="Write demo proof Markdown to this path, for example demo-proof.md.")
    parser.add_argument("--eval-xlsx", help="Run the Acquired-style eval questions from an .xlsx workbook.")
    parser.add_argument("--eval-output", help="Write eval Markdown report to this path.")
    parser.add_argument("--eval-json", help="Write eval JSON report to this path.")
    parser.add_argument("--journal", help="Append safe orchestration decisions to a JSONL journal.")
    parser.add_argument("--rules", help="Path to editable orchestration rules JSON.")
    parser.add_argument("--include-debug", action="store_true", help="Include sanitized debug payloads in demo-proof JSON/Markdown.")
    parser.add_argument("--max-recovery-steps", type=int, default=3, help="Maximum demo-proof recovery steps after the first grounded call.")
    parser.add_argument("--max-attempts", type=int, default=None, help="Maximum answer/recovery attempts for orchestrated validation.")
    parser.add_argument("--validation-mode", choices=["strict", "balanced", "fast"], default="balanced", help="Answer validation depth for orchestrated proof runs.")
    parser.add_argument("--show-decision-trail", action="store_true", help="Show the safe decision trail in demo proof output.")
    parser.add_argument("--hide-review-note", action="store_true", help="Hide enterprise review guidance in demo proof output.")
    parser.add_argument(
        "--question",
        dest="demo_questions",
        action="append",
        default=[],
        help="Add a demo-proof question. Repeat this flag for multiple questions.",
    )
    parser.add_argument("--questions-file", help="Read demo-proof questions from a newline-delimited text file.")

    approval = parser.add_argument_group("human approval gate")
    approval.add_argument("--require-approval", action="store_true", help="Hold high-risk answers at pending_approval until a reviewer decides.")
    approval.add_argument(
        "--approval-risk-mode",
        choices=["off", "high-risk-only", "always"],
        default="off",
        help="When to require approval: off, high-risk-only, or always.",
    )
    approval.add_argument("--approvals-file", default=None, help="Path to the JSONL approval store (default: runs/approvals.jsonl).")
    approval.add_argument("--list-approvals", action="store_true", help="List pending approval requests and exit.")
    approval.add_argument("--approve", metavar="APPROVAL_ID", help="Approve a pending approval request and exit.")
    approval.add_argument("--reject", metavar="APPROVAL_ID", help="Reject a pending approval request and exit.")
    approval.add_argument("--reviewer", help="Reviewer name for --approve/--reject.")
    approval.add_argument("--comment", help="Reviewer comment for --approve/--reject.")

    audit = parser.add_argument_group("audit log")
    audit.add_argument("--audit-log", default=None, help="Path to the hash-chained JSONL audit log (default: runs/audit-log.jsonl).")
    audit.add_argument("--show-audit", metavar="RUN_ID", help="Print the audit events for a run and exit.")
    audit.add_argument("--export-audit", metavar="RUN_ID", help="Print the full audit export (with chain verification) for a run and exit.")

    evals = parser.add_argument_group("eval dashboard")
    evals.add_argument("--save-eval-run", action="store_true", help="Persist the eval run summary for the eval dashboard.")
    evals.add_argument("--eval-runs", action="store_true", help="List saved eval run summaries and exit.")
    evals.add_argument("--show-eval-run", metavar="EVAL_RUN_ID", help="Print one saved eval run summary and exit.")

    red_team = parser.add_argument_group("red team")
    red_team.add_argument("--red-team", action="store_true", help="Run the deterministic red-team checks and print the findings table.")
    red_team.add_argument("--red-team-output", metavar="PATH", help="Write the red-team Markdown report to this path.")
    red_team.add_argument("--red-team-json", metavar="PATH", help="Write the red-team JSON report to this path.")
    return parser


def _print_json(payload) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _handle_standalone(args: argparse.Namespace, settings: Settings) -> int | None:
    """Handle flags that run without an MCP/backend connection. Returns exit code or None."""
    approvals_path = args.approvals_file or settings.approvals_path
    audit_path = args.audit_log or settings.audit_log_path

    if args.list_approvals:
        store = ApprovalStore(approvals_path)
        _print_json({"pending": store.pending()})
        return 0

    if args.approve or args.reject:
        if not args.reviewer:
            print("error: --reviewer NAME is required with --approve/--reject")
            return 2
        store = ApprovalStore(approvals_path)
        audit_log = AuditLog(audit_path)
        approval_id = args.approve or args.reject
        try:
            if args.approve:
                record = store.approve(approval_id, reviewer=args.reviewer, comment=args.comment)
                event_type = "approval_approved"
            else:
                record = store.reject(approval_id, reviewer=args.reviewer, comment=args.comment)
                event_type = "approval_rejected"
        except (KeyError, ValueError) as exc:
            print(f"error: {exc}")
            return 1
        audit_log.append(
            event_type=event_type,
            run_id=record.get("run_id"),
            actor=f"reviewer:{record.get('reviewer')}",
            summary=f"Approval {approval_id} {record.get('status')} by {record.get('reviewer')}",
            payload={"approval_id": approval_id, "status": record.get("status"), "comment": record.get("comment")},
        )
        _print_json(record)
        return 0

    if args.show_audit:
        audit_log = AuditLog(audit_path)
        events = audit_log.events(run_id=args.show_audit)
        if not events:
            print(f"error: no audit events found for run_id {args.show_audit}")
            return 1
        _print_json({"run_id": args.show_audit, "event_count": len(events), "events": events})
        return 0

    if args.export_audit:
        audit_log = AuditLog(audit_path)
        export = audit_log.export_run(args.export_audit)
        if not export["events"]:
            print(f"error: no audit events found for run_id {args.export_audit}")
            return 1
        _print_json(export)
        return 0

    if args.eval_runs:
        _print_json({"eval_runs": EvalStore(settings.eval_runs_dir).list()})
        return 0

    if args.show_eval_run:
        summary = EvalStore(settings.eval_runs_dir).get(args.show_eval_run)
        if summary is None:
            print(f"error: eval run not found: {args.show_eval_run}")
            return 1
        _print_json(summary)
        return 0

    if args.red_team:
        report = run_red_team(findings_path=settings.red_team_findings_path)
        save_latest(report, settings.red_team_latest_path)
        if args.red_team_output:
            path = Path(args.red_team_output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(render_red_team_markdown(report), encoding="utf-8")
        if args.red_team_json:
            path = Path(args.red_team_json)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        if args.json:
            _print_json(report)
        else:
            print(render_red_team_markdown(report))
            if args.red_team_output:
                print(f"Wrote red-team Markdown: {args.red_team_output}")
            if args.red_team_json:
                print(f"Wrote red-team JSON: {args.red_team_json}")
        return 0 if report["overall_status"] == "pass" else 1

    return None


async def _run(args: argparse.Namespace) -> int:
    settings = Settings()

    standalone = _handle_standalone(args, settings)
    if standalone is not None:
        return standalone

    # Everything past this point spawns the MCP server, so check the paths now
    # rather than letting a child process fail with an opaque import error.
    settings.validate_paths()

    approval_gating = args.require_approval or args.approval_risk_mode != "off"
    audit_log = AuditLog(args.audit_log or settings.audit_log_path)
    approval_store = ApprovalStore(args.approvals_file or settings.approvals_path)
    run_store = RunStore(settings.run_results_dir)

    if args.eval_xlsx:
        report = await run_eval(
            xlsx_path=args.eval_xlsx,
            rules_path=args.rules,
            journal_path=args.journal,
            max_recovery_steps=args.max_recovery_steps,
        )
        written = write_eval_outputs(report, markdown_path=args.eval_output, json_path=args.eval_json)
        saved_summary = None
        if args.save_eval_run:
            saved_summary = build_eval_run_summary(report, settings=settings)
            EvalStore(settings.eval_runs_dir).save(saved_summary)
        if args.json:
            _print_json(report)
        else:
            print(render_eval_markdown(report))
            for kind, path in written.items():
                print(f"Wrote eval {kind}: {path}")
        if saved_summary and not args.json:
            print(f"Saved eval run: {saved_summary['eval_run_id']}")
        return 0 if report["status"] == "pass" else 1

    if args.demo_proof:
        questions = resolve_demo_questions(
            positional_question=args.question,
            questions=args.demo_questions,
            questions_file=args.questions_file,
        )
        orchestrator = EnterpriseRagOrchestrator(
            rules_path=args.rules,
            journal_path=args.journal,
            audit_log=audit_log,
            approval_store=approval_store,
            run_store=run_store,
        )
        proof = await build_demo_proof(
            orchestrator=orchestrator,
            questions=questions,
            include_debug=args.include_debug,
            max_recovery_steps=args.max_recovery_steps,
            max_attempts=args.max_attempts,
            validation_mode=args.validation_mode,
            show_decision_trail=True,
            show_review_note=not args.hide_review_note,
            rules_path=args.rules,
            journal_path=args.journal,
            require_approval=args.require_approval,
            approval_mode=args.approval_risk_mode,
        )
        if args.output:
            output_path = write_markdown_report(proof, args.output)
            if not args.json:
                print(f"Wrote demo proof Markdown: {output_path}")
        if args.json:
            _print_json(proof)
        else:
            print(render_text_report(proof))
        return 1 if proof["status"] == "error" else 0

    agent = RagEnterpriseAgent()
    if args.check_config:
        _print_json(await agent.check_configuration())
        return 0
    if not args.question:
        raise SystemExit("question is required unless --check-config is used")

    if approval_gating:
        orchestrator = EnterpriseRagOrchestrator(
            rules_path=args.rules,
            journal_path=args.journal,
            audit_log=audit_log,
            approval_store=approval_store,
            run_store=run_store,
        )
        result = await orchestrator.run(
            args.question,
            max_recovery_steps=args.max_recovery_steps,
            max_attempts=args.max_attempts,
            validation_mode=args.validation_mode,
            journal_path=args.journal,
            require_approval=args.require_approval,
            approval_mode=args.approval_risk_mode,
        )
        run = result.to_dict()
        if args.json:
            _print_json(run)
        else:
            print(f"Status: {run.get('grounding_status')} | Approval: {run.get('approval_status')}")
            if run.get("approval_id"):
                print(f"Approval ID: {run.get('approval_id')}")
            print(f"Run ID: {run.get('run_id')}")
            print("Answer:")
            print(run.get("answer") or "[no final answer produced]")
        return 1 if run.get("error") else 0

    result = await agent.run(args.question)
    if args.json:
        _print_json(result.to_dict())
        return 1 if result.error else 0

    print("Answer:")
    print(result.answer or "[no final answer produced]")
    if result.tool_outputs:
        print("\nTool Outputs:")
        print(json.dumps(result.tool_outputs, indent=2, sort_keys=True))
    return 1 if result.error else 0


def main() -> int:
    args = build_parser().parse_args()
    try:
        return asyncio.run(_run(args))
    except ConfigError as exc:
        # Configuration problems are the user's to fix, so report them as a
        # message rather than a traceback.
        print(f"Configuration error:\n{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
