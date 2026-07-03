from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Sequence

from rag_enterprise_langgraph.agent import AgentRunResult, RagEnterpriseAgent
from rag_enterprise_langgraph.orchestrator import EnterpriseRagOrchestrator, overall_status


REQUIRED_MCP_TOOLS = ("ask_grounded", "search_documents", "get_document_excerpt")

DEFAULT_DEMO_QUESTIONS = (
    "What does the employee handbook say about VPN access?",
    "Summarize the policy with citations.",
    "Find the most relevant source excerpt for VPN access.",
)

SECURITY_BOUNDARY_SUMMARY = (
    "LangGraph app: orchestration only, no database access.",
    "MCP server: read-only RAG tool interface.",
    "Backend: owns auth, ACL trimming, retrieval, citations, audit, cache, and governance.",
    "Agent prompt: treats retrieved text as untrusted evidence.",
    "Tool guard: normalizes invalid tool arguments and returns structured errors.",
)


def read_questions_file(path: str | Path) -> list[str]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]


def resolve_demo_questions(
    *,
    positional_question: str | None = None,
    questions: Sequence[str] | None = None,
    questions_file: str | Path | None = None,
) -> list[str]:
    resolved: list[str] = []
    if positional_question:
        resolved.append(positional_question.strip())
    for question in questions or ():
        if question and question.strip():
            resolved.append(question.strip())
    if questions_file:
        resolved.extend(read_questions_file(questions_file))
    return resolved or list(DEFAULT_DEMO_QUESTIONS)


def _redacted_key(key: str) -> bool:
    lowered = key.lower()
    secret_words = ("password", "token", "secret", "api_key", "authorization", "cookie")
    present_flags = (
        "present",
        "enabled",
        "configured",
    )
    return any(word in lowered for word in secret_words) and not any(flag in lowered for flag in present_flags)


def _sanitize_text(value: str) -> str:
    import re

    text = re.sub(r'File "[^"]+"', 'File "[path-redacted]"', value)
    return re.sub(r"/Users/[^\\s\"']+", "[path-redacted]", text)


def redact_for_sharing(value: Any, *, include_debug: bool = False) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text in {"traceback", "raw", "system_prompt", "user_prompt", "prompt", "raw_prompt", "messages"}:
                continue
            if not include_debug and key_text in {"debug_info"}:
                continue
            redacted[key_text] = (
                "[redacted]"
                if _redacted_key(key_text)
                else redact_for_sharing(item, include_debug=include_debug)
            )
        return redacted
    if isinstance(value, list):
        return [redact_for_sharing(item, include_debug=include_debug) for item in value]
    if isinstance(value, tuple):
        return [redact_for_sharing(item, include_debug=include_debug) for item in value]
    if isinstance(value, str):
        return _sanitize_text(value)
    return value


def _content_dict(output: dict[str, Any]) -> dict[str, Any]:
    content = output.get("content")
    return content if isinstance(content, dict) else {}


def _unique(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output


def _collect_citations(tool_outputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    for output in tool_outputs:
        content = _content_dict(output)
        raw_citations = content.get("citations")
        if not isinstance(raw_citations, list):
            continue
        for citation in raw_citations:
            if isinstance(citation, dict):
                citations.append(redact_for_sharing(citation))
    return citations


def _first_content_value(tool_outputs: list[dict[str, Any]], key: str) -> Any:
    for output in tool_outputs:
        content = _content_dict(output)
        value = content.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _citations_in_output(output: dict[str, Any]) -> list[dict[str, Any]]:
    citations = _content_dict(output).get("citations")
    return [item for item in citations if isinstance(item, dict)] if isinstance(citations, list) else []


def _results_in_output(output: dict[str, Any]) -> list[dict[str, Any]]:
    results = _content_dict(output).get("results")
    return [item for item in results if isinstance(item, dict)] if isinstance(results, list) else []


def _answer_status(result: AgentRunResult, citation_count: int) -> str:
    if result.error:
        return "error"
    answer = (result.answer or "").strip()
    if not answer:
        return "no_answer"
    if answer == "Not found in provided sources.":
        return "not_found"
    if "pending human approval" in answer.lower():
        return "pending_approval"
    return "grounded" if citation_count else "answered"


def summarize_result(result: AgentRunResult) -> dict[str, Any]:
    tool_outputs = redact_for_sharing(result.tool_outputs)
    citations = _collect_citations(tool_outputs)
    tools_used = _unique(
        str(output.get("tool_name") or "")
        for output in tool_outputs
        if output.get("tool_name") and output.get("tool_name") != "agent"
    )
    return {
        "question": result.question,
        "answer": result.answer,
        "answer_status": _answer_status(result, len(citations)),
        "grounding_status": _answer_status(result, len(citations)),
        "tools_used": tools_used,
        "execution_timeline": [
            {
                "step": index,
                "tool_name": output.get("tool_name"),
                "purpose": "agent_tool_call",
                "result_status": "tool_error" if _content_dict(output).get("is_error") else "completed",
                "citation_count": len(_citations_in_output(output)),
                "result_count": len(_results_in_output(output)),
            }
            for index, output in enumerate(tool_outputs, start=1)
        ],
        "citation_count": len(citations),
        "citations": citations,
        "evidence": citations,
        "evidence_count": len(citations),
        "used_chunks_count": _first_content_value(tool_outputs, "used_chunks_count"),
        "mode": _first_content_value(tool_outputs, "mode"),
        "latency_ms": _first_content_value(tool_outputs, "latency_ms"),
        "message_count": result.message_count,
        "error": result.error,
        "tool_outputs": tool_outputs,
    }


def required_tool_status(tool_names: Sequence[str]) -> dict[str, bool]:
    available = set(tool_names)
    return {tool_name: tool_name in available for tool_name in REQUIRED_MCP_TOOLS}


async def build_demo_proof(
    *,
    agent: RagEnterpriseAgent | None = None,
    orchestrator: EnterpriseRagOrchestrator | None = None,
    questions: Sequence[str] | None = None,
    include_debug: bool = False,
    max_recovery_steps: int = 3,
    rules_path: str | Path | None = None,
    journal_path: str | Path | None = None,
) -> dict[str, Any]:
    runtime_orchestrator = orchestrator or (
        None
        if agent
        else EnterpriseRagOrchestrator(
            rules_path=str(rules_path) if rules_path else None,
            journal_path=str(journal_path) if journal_path else None,
        )
    )
    runtime_agent = agent or RagEnterpriseAgent()
    resolved_questions = list(questions or DEFAULT_DEMO_QUESTIONS)
    diagnostics: dict[str, Any]
    check_error: str | None = None
    try:
        diagnostics = (
            await runtime_orchestrator.check_configuration()
            if runtime_orchestrator
            else await runtime_agent.check_configuration()
        )
    except Exception as exc:
        diagnostics = {}
        check_error = str(exc)

    tool_names = [str(item) for item in diagnostics.get("mcp_tool_names", [])] if diagnostics else []
    runs: list[dict[str, Any]] = []
    for question in resolved_questions:
        if runtime_orchestrator:
            run = (
                await runtime_orchestrator.run(
                    question,
                    max_recovery_steps=max_recovery_steps,
                    journal_path=str(journal_path) if journal_path else None,
                )
            ).to_dict()
        else:
            result = await runtime_agent.run(question)
            run = summarize_result(result)
        if not include_debug:
            run.pop("tool_outputs", None)
        runs.append(redact_for_sharing(run, include_debug=include_debug))

    errors = [run["error"] for run in runs if run.get("error")]
    if check_error:
        errors.insert(0, check_error)
    status = overall_status(runs)
    if check_error and status == "ok":
        status = "error"

    return {
        "status": status,
        "overall_status": status,
        "diagnostics": redact_for_sharing(diagnostics, include_debug=include_debug),
        "diagnostics_error": check_error,
        "mcp_tools": tool_names,
        "required_tool_status": required_tool_status(tool_names),
        "questions": resolved_questions,
        "runs": runs,
        "security_boundary_summary": list(SECURITY_BOUNDARY_SUMMARY),
        "errors": errors,
        "include_debug": include_debug,
    }


def _table_value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    text = str(value).replace("\n", " ").replace("|", "\\|").strip()
    return text or "-"


def _truncate(text: Any, limit: int = 260) -> str:
    normalized = " ".join(str(text or "").split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def render_text_report(proof: dict[str, Any]) -> str:
    lines = ["Enterprise LangGraph + MCP RAG Demo Proof", "=" * 45, ""]
    lines.append(f"Status: {proof.get('status', 'unknown')}")
    if proof.get("diagnostics_error"):
        lines.append(f"Diagnostics error: {proof['diagnostics_error']}")
    lines.append("")
    lines.append("MCP Tools:")
    for tool_name, present in proof.get("required_tool_status", {}).items():
        marker = "available" if present else "missing"
        lines.append(f"- {tool_name}: {marker}")
    lines.append("")
    lines.append("Security Boundary Summary:")
    for item in proof.get("security_boundary_summary", []):
        lines.append(f"- {item}")
    lines.append("")
    lines.append("Demo Runs:")
    for index, run in enumerate(proof.get("runs", []), start=1):
        tools = ", ".join(run.get("tools_used") or []) or "-"
        lines.append(f"{index}. {run.get('question')}")
        lines.append(
            f"   Status: {run.get('grounding_status') or run.get('answer_status')} | "
            f"Tools: {tools} | Citations: {run.get('citation_count', 0)} | "
            f"Evidence: {run.get('evidence_count', 0)}"
        )
        timeline = run.get("execution_timeline") or []
        if timeline:
            lines.append("   Execution Timeline:")
            for step in timeline:
                reason = f" ({step.get('recovery_reason')})" if step.get("recovery_reason") else ""
                lines.append(
                    f"   - {step.get('step')}. {step.get('tool_name')} -> "
                    f"{step.get('purpose')} -> {step.get('result_status')}{reason}"
                )
        if run.get("latency_ms") is not None:
            lines.append(f"   Latency: {run.get('latency_ms')} ms")
        verdict = run.get("evidence_verdict") or {}
        if verdict:
            lines.append(
                f"   Evidence verdict: {verdict.get('status')} | "
                f"{verdict.get('reason')} | score={verdict.get('score')}"
            )
        if run.get("error"):
            lines.append(f"   Error: {run.get('error')}")
        lines.append(f"   Answer: {_truncate(run.get('answer'), 420) or '[no answer]'}")
    return "\n".join(lines).rstrip() + "\n"


def render_markdown_report(proof: dict[str, Any]) -> str:
    diagnostics = proof.get("diagnostics") or {}
    lines = [
        "# Enterprise LangGraph + MCP RAG Demo Proof",
        "",
        "This report is generated by the LangGraph app and is safe to use as a portfolio proof after reviewing source snippets for private business content.",
        "",
        "## Runtime Summary",
        "",
        "| Field | Value |",
        "| --- | --- |",
    ]
    summary_fields = (
        ("Status", proof.get("status")),
        ("App name", diagnostics.get("app_name")),
        ("Model provider", diagnostics.get("model_provider")),
        ("Model name", diagnostics.get("model_name")),
        ("MCP server", diagnostics.get("mcp_server_name")),
        ("Backend base URL", diagnostics.get("backend_base_url")),
        ("Bearer token present", diagnostics.get("backend_bearer_token_present")),
        ("Dev login email present", diagnostics.get("backend_dev_login_email_present")),
        ("Dev login password present", diagnostics.get("backend_dev_login_password_present")),
    )
    for label, value in summary_fields:
        lines.append(f"| {label} | {_table_value(value)} |")
    if proof.get("diagnostics_error"):
        lines.append(f"| Diagnostics error | {_table_value(proof['diagnostics_error'])} |")

    lines.extend(["", "## MCP Tool Inventory", "", "| Tool | Status |", "| --- | --- |"])
    for tool_name, present in proof.get("required_tool_status", {}).items():
        lines.append(f"| `{tool_name}` | {'available' if present else 'missing'} |")
    discovered = [tool for tool in proof.get("mcp_tools", []) if tool not in REQUIRED_MCP_TOOLS]
    for tool_name in discovered:
        lines.append(f"| `{tool_name}` | discovered |")

    lines.extend(["", "## Demo Run Summary", "", "| # | Question | Status | Tools | Citations | Evidence | Chunks | Mode | Latency |", "| --- | --- | --- | --- | ---: | ---: | ---: | --- | ---: |"])
    for index, run in enumerate(proof.get("runs", []), start=1):
        tools = ", ".join(f"`{tool}`" for tool in run.get("tools_used") or []) or "-"
        lines.append(
            "| "
            + " | ".join(
                [
                    str(index),
                    _table_value(run.get("question")),
                    _table_value(run.get("grounding_status") or run.get("answer_status")),
                    tools,
                    _table_value(run.get("citation_count")),
                    _table_value(run.get("evidence_count")),
                    _table_value(run.get("used_chunks_count")),
                    _table_value(run.get("mode")),
                    _table_value(run.get("latency_ms")),
                ]
            )
            + " |"
        )

    lines.extend(["", "## Detailed Answers", ""])
    for index, run in enumerate(proof.get("runs", []), start=1):
        lines.extend(
            [
                f"### {index}. {_table_value(run.get('question'))}",
                "",
                f"**Status:** `{_table_value(run.get('grounding_status') or run.get('answer_status'))}`",
                "",
                "**Execution Timeline**",
                "",
            ]
        )
        timeline = run.get("execution_timeline") or []
        if timeline:
            for step in timeline:
                reason = f" ({step.get('recovery_reason')})" if step.get("recovery_reason") else ""
                lines.append(
                    f"- {step.get('step')}. `{step.get('tool_name')}` -> "
                    f"{step.get('purpose')} -> `{step.get('result_status')}`{reason}"
                )
        else:
            lines.append("- No tool timeline captured.")
        verdict = run.get("evidence_verdict") or {}
        if verdict:
            lines.extend(
                [
                    "",
                    f"**Evidence verdict:** `{_table_value(verdict.get('status'))}` - "
                    f"{_table_value(verdict.get('reason'))} (score={_table_value(verdict.get('score'))})",
                ]
            )
        lines.extend(
            [
                "",
                "**Answer**",
                "",
                run.get("answer") or "[no final answer produced]",
                "",
                "**Citations / Evidence**",
                "",
            ]
        )
        evidence_items = (run.get("citations") or []) + (run.get("evidence") or [])
        if not evidence_items:
            lines.append("- No citations or excerpt-backed evidence returned.")
        for evidence in evidence_items:
            file_name = evidence.get("file_name") or evidence.get("source_id") or "source"
            citation_id = evidence.get("citation_id") or evidence.get("chunk_id") or evidence.get("evidence_type") or "evidence"
            locator = evidence.get("locator") or evidence.get("heading") or ""
            snippet = _truncate(evidence.get("snippet"), 240)
            lines.append(f"- `{citation_id}` {file_name} {f'({locator})' if locator else ''}: {snippet}")
        if run.get("error"):
            lines.extend(["", "**Error**", "", f"`{run['error']}`"])
        lines.append("")

    lines.extend(["## Security / Governance Boundary", ""])
    for item in proof.get("security_boundary_summary", []):
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Architecture",
            "",
            "```mermaid",
            "flowchart LR",
            "    U[\"User / API Client\"] --> LG[\"LangGraph Agent<br/>Tool orchestration only\"]",
            "    LG -->|stdio MCP| MCP[\"RAG Enterprise MCP Server<br/>ask_grounded<br/>search_documents<br/>get_document_excerpt\"]",
            "    MCP -->|HTTP + auth cookie/token| BE[\"Enterprise RAG Backend<br/>FastAPI\"]",
            "    BE --> AUTH[\"Auth + ACL Layer\"]",
            "    BE --> RET[\"Retrieval + Citations + Governance\"]",
            "    RET --> DB[\"Postgres + pgvector\"]",
            "    BE -->|grounded answer + citations| MCP",
            "    MCP -->|structured tool output| LG",
            "    LG -->|final answer + visible proof| U",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def write_markdown_report(proof: dict[str, Any], path: str | Path) -> Path:
    output_path = Path(path)
    output_path.write_text(render_markdown_report(proof), encoding="utf-8")
    return output_path
