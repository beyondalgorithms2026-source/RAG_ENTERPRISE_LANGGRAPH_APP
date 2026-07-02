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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the enterprise LangGraph agent.")
    parser.add_argument("question", nargs="?", help="User question to send to the agent.")
    parser.add_argument("--json", action="store_true", help="Print the full JSON result.")
    parser.add_argument("--check-config", action="store_true", help="Print redacted runtime diagnostics and loaded MCP tool names.")
    parser.add_argument("--demo-proof", action="store_true", help="Run the editable portfolio demo proof flow.")
    parser.add_argument("--output", help="Write demo proof Markdown to this path, for example demo-proof.md.")
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
) -> int:
    agent = RagEnterpriseAgent()
    if demo_proof:
        questions = resolve_demo_questions(
            positional_question=question,
            questions=demo_questions,
            questions_file=questions_file,
        )
        proof = await build_demo_proof(agent=agent, questions=questions)
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
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
