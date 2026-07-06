from __future__ import annotations

import argparse
import asyncio
import json

from rag_enterprise_langgraph.agent import RagEnterpriseAgent
from rag_enterprise_langgraph.demo_proof import (
    build_demo_proof,
    render_text_report,
    resolve_demo_questions,
    write_markdown_report,
)
from rag_enterprise_langgraph.eval_runner import render_eval_markdown, run_eval, write_eval_outputs
from rag_enterprise_langgraph.orchestrator import EnterpriseRagOrchestrator


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
    return parser


async def _run(
    question: str | None,
    as_json: bool,
    check_config: bool,
    demo_proof: bool,
    output: str | None,
    demo_questions: list[str],
    questions_file: str | None,
    include_debug: bool,
    max_recovery_steps: int,
    max_attempts: int | None,
    validation_mode: str,
    show_decision_trail: bool,
    hide_review_note: bool,
    eval_xlsx: str | None,
    eval_output: str | None,
    eval_json: str | None,
    journal: str | None,
    rules: str | None,
) -> int:
    agent = RagEnterpriseAgent()
    if eval_xlsx:
        report = await run_eval(
            xlsx_path=eval_xlsx,
            rules_path=rules,
            journal_path=journal,
            max_recovery_steps=max_recovery_steps,
        )
        written = write_eval_outputs(report, markdown_path=eval_output, json_path=eval_json)
        if as_json:
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            print(render_eval_markdown(report))
            for kind, path in written.items():
                print(f"Wrote eval {kind}: {path}")
        return 0 if report["status"] == "pass" else 1

    if demo_proof:
        questions = resolve_demo_questions(
            positional_question=question,
            questions=demo_questions,
            questions_file=questions_file,
        )
        orchestrator = EnterpriseRagOrchestrator(rules_path=rules, journal_path=journal)
        proof = await build_demo_proof(
            orchestrator=orchestrator,
            questions=questions,
            include_debug=include_debug,
            max_recovery_steps=max_recovery_steps,
            max_attempts=max_attempts,
            validation_mode=validation_mode,
            show_decision_trail=True if show_decision_trail else True,
            show_review_note=not hide_review_note,
            rules_path=rules,
            journal_path=journal,
        )
        if output:
            output_path = write_markdown_report(proof, output)
            if not as_json:
                print(f"Wrote demo proof Markdown: {output_path}")
        if as_json:
            print(json.dumps(proof, indent=2, sort_keys=True))
        else:
            print(render_text_report(proof))
        return 1 if proof["status"] == "error" else 0

    if check_config:
        print(json.dumps(await agent.check_configuration(), indent=2, sort_keys=True))
        return 0
    if not question:
        raise SystemExit("question is required unless --check-config is used")

    result = await agent.run(question)
    if as_json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        return 1 if result.error else 0

    print("Answer:")
    print(result.answer or "[no final answer produced]")
    if result.tool_outputs:
        print("\nTool Outputs:")
        print(json.dumps(result.tool_outputs, indent=2, sort_keys=True))
    return 1 if result.error else 0


def main() -> int:
    args = build_parser().parse_args()
    return asyncio.run(
        _run(
            args.question,
            args.json,
            args.check_config,
            args.demo_proof,
            args.output,
            args.demo_questions,
            args.questions_file,
            args.include_debug,
            args.max_recovery_steps,
            args.max_attempts,
            args.validation_mode,
            args.show_decision_trail,
            args.hide_review_note,
            args.eval_xlsx,
            args.eval_output,
            args.eval_json,
            args.journal,
            args.rules,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
