from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Sequence

from langchain_core.tools import BaseTool

from rag_enterprise_langgraph.config import Settings
from rag_enterprise_langgraph.mcp_client import load_mcp_tools, suppress_mcp_stdio_stderr
from rag_enterprise_langgraph.tool_guard import reset_current_question, set_current_question


GROUNDING_SUCCESS_STATUSES = {"grounded", "recovered", "not_found"}
FAILURE_STATUSES = {"backend_auth_failed", "backend_timeout", "tool_error", "not_grounded", "partial"}


_STOPWORDS = {
    "about",
    "after",
    "before",
    "could",
    "does",
    "from",
    "have",
    "into",
    "itself",
    "just",
    "more",
    "than",
    "that",
    "their",
    "there",
    "these",
    "they",
    "this",
    "what",
    "when",
    "where",
    "which",
    "while",
    "with",
    "would",
    "first",
    "answer",
}


@dataclass
class OrchestrationStep:
    step: int
    tool_name: str
    purpose: str
    result_status: str
    citation_count: int = 0
    result_count: int = 0
    used_chunks_count: int | None = None
    mode: str | None = None
    latency_ms: int | float | None = None
    recovery_reason: str | None = None
    failure_reason: str | None = None
    source_id: int | None = None
    source_part_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "tool_name": self.tool_name,
            "purpose": self.purpose,
            "result_status": self.result_status,
            "citation_count": self.citation_count,
            "result_count": self.result_count,
            "used_chunks_count": self.used_chunks_count,
            "mode": self.mode,
            "latency_ms": self.latency_ms,
            "recovery_reason": self.recovery_reason,
            "failure_reason": self.failure_reason,
            "source_id": self.source_id,
            "source_part_id": self.source_part_id,
        }


@dataclass
class OrchestratedRunResult:
    question: str
    answer: str
    grounding_status: str
    tools_used: list[str]
    execution_timeline: list[dict[str, Any]]
    citations: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    tool_outputs: list[dict[str, Any]] = field(default_factory=list)
    citation_count: int = 0
    evidence_count: int = 0
    used_chunks_count: int | None = None
    mode: str | None = None
    latency_ms: int | float | None = None
    recovery_attempted: bool = False
    recovery_successful: bool = False
    portfolio_safe: bool = False
    failure_reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "answer": self.answer,
            "grounding_status": self.grounding_status,
            "answer_status": self.grounding_status,
            "tools_used": self.tools_used,
            "execution_timeline": self.execution_timeline,
            "citations": self.citations,
            "evidence": self.evidence,
            "tool_outputs": self.tool_outputs,
            "citation_count": self.citation_count,
            "evidence_count": self.evidence_count,
            "used_chunks_count": self.used_chunks_count,
            "mode": self.mode,
            "latency_ms": self.latency_ms,
            "recovery_attempted": self.recovery_attempted,
            "recovery_successful": self.recovery_successful,
            "portfolio_safe": self.portfolio_safe,
            "failure_reason": self.failure_reason,
            "error": self.error,
            "message_count": len(self.tool_outputs),
        }


def _safe_json_parse(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _content_dict(value: Any) -> dict[str, Any]:
    parsed = _safe_json_parse(value)
    if isinstance(parsed, dict):
        return parsed
    return {"raw": str(value)}


def _short_error_text(value: Any) -> str | None:
    parsed = _safe_json_parse(value)
    if isinstance(parsed, dict):
        nested_error = _safe_json_parse(parsed.get("error"))
        if isinstance(nested_error, dict):
            message = nested_error.get("message") or nested_error.get("detail") or nested_error.get("error")
            status_code = nested_error.get("status_code")
            if message:
                suffix = f" (status_code={status_code})" if status_code else ""
                return f"{str(message).strip()}{suffix}"[:360]
        message = parsed.get("message") or parsed.get("detail")
        if message:
            return str(message).strip()[:360]
    text = json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else str(value or "")
    if not text.strip():
        return None
    text = re.sub(r'"traceback"\s*:\s*".*?(?=",\s*"|\}\s*$)', '"traceback": "[redacted]"', text)
    cleaned = re.sub(r'File "[^"]+"', 'File "[path-redacted]"', text)
    cleaned = re.sub(r"/Users/[^\\s\"']+", "[path-redacted]", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:360]


def classify_failure(value: Any) -> str | None:
    text = json.dumps(value, sort_keys=True).lower() if isinstance(value, (dict, list)) else str(value or "").lower()
    if not text:
        return None
    if "timed out" in text or "timeout" in text:
        return "backend_timeout"
    if "401" in text or "403" in text or "unauthorized" in text or "authentication" in text:
        return "backend_auth_failed"
    if "is_error" in text or '"error"' in text or "traceback" in text or "jsonrpc" in text:
        return "tool_error"
    return None


def _is_not_found(answer: Any) -> bool:
    return "not found in provided sources" in str(answer or "").lower()


def _citations(content: dict[str, Any]) -> list[dict[str, Any]]:
    citations = content.get("citations")
    return [item for item in citations if isinstance(item, dict)] if isinstance(citations, list) else []


def _results(content: dict[str, Any]) -> list[dict[str, Any]]:
    results = content.get("results")
    return [item for item in results if isinstance(item, dict)] if isinstance(results, list) else []


def _evidence_from_citations(citations: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for citation in citations:
        evidence.append(
            {
                "source_id": citation.get("source_id"),
                "source_part_id": citation.get("source_part_id"),
                "chunk_id": citation.get("chunk_id"),
                "file_name": citation.get("file_name"),
                "heading": citation.get("heading"),
                "locator": citation.get("locator"),
                "snippet": citation.get("snippet"),
                "evidence_type": "citation",
            }
        )
    return evidence


def _evidence_from_results(results: Sequence[dict[str, Any]], *, limit: int = 3) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for result in list(results)[:limit]:
        evidence.append(
            {
                "source_id": result.get("source_id"),
                "source_part_id": result.get("source_part_id"),
                "chunk_id": result.get("chunk_id"),
                "file_name": result.get("file_name"),
                "heading": result.get("heading"),
                "locator": result.get("locator"),
                "snippet": result.get("snippet"),
                "score": result.get("score") or result.get("combined_score") or result.get("rank_score"),
                "evidence_type": "search_result",
            }
        )
    return evidence


def _evidence_from_excerpt(content: dict[str, Any]) -> list[dict[str, Any]]:
    if not content.get("matched"):
        return []
    result = content.get("result") if isinstance(content.get("result"), dict) else {}
    return [
        {
            "source_id": result.get("source_id"),
            "source_part_id": result.get("source_part_id"),
            "chunk_id": result.get("chunk_id"),
            "file_name": result.get("file_name"),
            "heading": result.get("heading"),
            "locator": result.get("locator"),
            "snippet": content.get("excerpt") or result.get("snippet"),
            "evidence_type": "excerpt",
        }
    ]


def _answer_from_evidence(question: str, evidence: Sequence[dict[str, Any]]) -> str:
    if not evidence:
        return "No grounded answer could be produced from the available MCP evidence."
    top = evidence[0]
    source = top.get("file_name") or f"source_id={top.get('source_id')}"
    snippet = str(top.get("snippet") or "").strip()
    if not snippet:
        return f"Recovered supporting evidence from {source}, but no safe snippet was available to quote."
    return (
        "Recovered supporting evidence from retrieval-only MCP tools. "
        f"For the question '{question}', the strongest evidence is from {source}: {snippet}"
    )


def extract_anchor_terms(question: str) -> list[str]:
    anchors: list[str] = []
    seen: set[str] = set()
    for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9._%-]*", question):
        normalized = token.strip(".,;:!?()[]{}\"'").lower()
        if not normalized or normalized in seen or normalized in _STOPWORDS:
            continue
        if len(normalized) < 4 and not any(char.isdigit() for char in normalized):
            continue
        seen.add(normalized)
        anchors.append(token.strip(".,;:!?()[]{}\"'"))
    return anchors[:8]


def exact_phrase_bias(question: str, anchors: Sequence[str]) -> str | None:
    quoted = re.findall(r'"([^"]{3,80})"', question)
    if quoted:
        return quoted[0].strip()
    capitalized = re.findall(r"\b[A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+){0,4}\b", question)
    capitalized = [
        phrase
        for phrase in capitalized
        if phrase.split()[0].lower() not in _STOPWORDS
        and phrase.split()[0].lower() not in {"what", "why", "how", "who", "when", "where"}
    ]
    if capitalized:
        return max(capitalized, key=len).strip()
    if anchors:
        return anchors[0]
    return None


class EnterpriseRagOrchestrator:
    def __init__(self, settings: Settings | None = None, *, quiet_mcp: bool = True):
        self.settings = settings or Settings()
        self.quiet_mcp = quiet_mcp
        self._tools: dict[str, BaseTool] | None = None

    async def _get_tools(self) -> dict[str, BaseTool]:
        if self._tools is None:
            tools = await load_mcp_tools(self.settings)
            self._tools = {tool.name: tool for tool in tools}
        return self._tools

    async def check_configuration(self) -> dict[str, Any]:
        with suppress_mcp_stdio_stderr(self.quiet_mcp):
            tools = await self._get_tools()
        return {
            **self.settings.diagnostic_summary(),
            "mcp_tool_names": list(tools.keys()),
        }

    async def _call_tool(self, name: str, arguments: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        tools = await self._get_tools()
        if name not in tools:
            content = {"is_error": True, "error": f"Tool not available: {name}"}
            output = {"tool_name": name, "tool_call_id": None, "content": content}
            return content, output
        raw = await tools[name].ainvoke(arguments)
        content = _content_dict(raw)
        output = {"tool_name": name, "tool_call_id": None, "content": content}
        return content, output

    def _step_from_content(self, *, index: int, tool_name: str, purpose: str, content: dict[str, Any]) -> OrchestrationStep:
        failure = classify_failure(content)
        citations = _citations(content)
        results = _results(content)
        status = failure or "completed"
        if tool_name == "ask_grounded":
            if citations and not _is_not_found(content.get("answer")):
                status = "grounded"
            elif _is_not_found(content.get("answer")):
                status = "not_found"
            elif not citations and content.get("answer"):
                status = "not_grounded"
        elif tool_name == "search_documents":
            status = "candidate_evidence_found" if results else "not_found"
        elif tool_name == "get_document_excerpt":
            status = "evidence_found" if content.get("matched") else "not_found"

        top_result = results[0] if results else content.get("result") if isinstance(content.get("result"), dict) else {}
        return OrchestrationStep(
            step=index,
            tool_name=tool_name,
            purpose=purpose,
            result_status=status,
            citation_count=len(citations),
            result_count=len(results),
            used_chunks_count=content.get("used_chunks_count"),
            mode=content.get("mode") or top_result.get("mode"),
            latency_ms=content.get("latency_ms"),
            failure_reason=_short_error_text(content) if failure else None,
            source_id=top_result.get("source_id"),
            source_part_id=top_result.get("source_part_id"),
        )

    async def run(self, question: str, *, max_recovery_steps: int = 3) -> OrchestratedRunResult:
        token = set_current_question(question)
        tool_outputs: list[dict[str, Any]] = []
        timeline: list[OrchestrationStep] = []
        tools_used: list[str] = []
        anchors = extract_anchor_terms(question)
        phrase_bias = exact_phrase_bias(question, anchors)

        async def call(name: str, purpose: str, arguments: dict[str, Any]) -> dict[str, Any]:
            with suppress_mcp_stdio_stderr(self.quiet_mcp):
                try:
                    content, output = await self._call_tool(name, arguments)
                except Exception as exc:
                    content = {
                        "is_error": True,
                        "error": str(exc),
                        "exception_type": exc.__class__.__name__,
                    }
                    output = {"tool_name": name, "tool_call_id": None, "content": content}
            tool_outputs.append(output)
            tools_used.append(name)
            timeline.append(
                self._step_from_content(
                    index=len(timeline) + 1,
                    tool_name=name,
                    purpose=purpose,
                    content=content,
                )
            )
            return content

        try:
            initial = await call(
                "ask_grounded",
                "initial_grounded_answer",
                {"question": question, "k_chunks": 6, "mode": "hybrid"},
            )
            initial_failure = classify_failure(initial)
            if initial_failure:
                return self._failure_result(question, initial_failure, timeline, tools_used, tool_outputs, initial)

            initial_citations = _citations(initial)
            if initial_citations and not _is_not_found(initial.get("answer")):
                evidence = _evidence_from_citations(initial_citations)
                return self._success_result(
                    question=question,
                    answer=str(initial.get("answer") or ""),
                    status="grounded",
                    citations=initial_citations,
                    evidence=evidence,
                    timeline=timeline,
                    tools_used=tools_used,
                    tool_outputs=tool_outputs,
                    content=initial,
                )

            recovery_attempted = False
            if max_recovery_steps >= 1:
                recovery_attempted = True
                keyword_args: dict[str, Any] = {
                    "question": question,
                    "k_chunks": 12,
                    "mode": "keyword",
                    "anchor_terms": anchors,
                    "expand_neighbors": True,
                }
                if phrase_bias:
                    keyword_args["exact_phrase_bias"] = phrase_bias
                keyword_ask = await call("ask_grounded", "keyword_grounded_recovery", keyword_args)
                keyword_failure = classify_failure(keyword_ask)
                if keyword_failure:
                    return self._failure_result(question, keyword_failure, timeline, tools_used, tool_outputs, keyword_ask)
                keyword_citations = _citations(keyword_ask)
                if keyword_citations and not _is_not_found(keyword_ask.get("answer")):
                    evidence = _evidence_from_citations(keyword_citations)
                    return self._success_result(
                        question=question,
                        answer=str(keyword_ask.get("answer") or ""),
                        status="recovered",
                        citations=keyword_citations,
                        evidence=evidence,
                        timeline=timeline,
                        tools_used=tools_used,
                        tool_outputs=tool_outputs,
                        content=keyword_ask,
                        recovery_attempted=recovery_attempted,
                        recovery_successful=True,
                    )

            search_content: dict[str, Any] | None = None
            search_results: list[dict[str, Any]] = []
            if max_recovery_steps >= 2:
                recovery_attempted = True
                search_args: dict[str, Any] = {
                    "question": question,
                    "k": 8,
                    "mode": "keyword",
                    "anchor_terms": anchors,
                    "expand_neighbors": True,
                    "debug": False,
                }
                if phrase_bias:
                    search_args["exact_phrase_bias"] = phrase_bias
                search_content = await call("search_documents", "keyword_evidence_search", search_args)
                search_failure = classify_failure(search_content)
                if search_failure:
                    return self._failure_result(question, search_failure, timeline, tools_used, tool_outputs, search_content)
                search_results = _results(search_content)

            excerpt_evidence: list[dict[str, Any]] = []
            if max_recovery_steps >= 3 and search_results:
                recovery_attempted = True
                top = search_results[0]
                excerpt_args: dict[str, Any] = {
                    "question": question,
                    "mode": "keyword",
                    "max_chars": 1800,
                }
                if top.get("source_id") is not None:
                    excerpt_args["source_id"] = top.get("source_id")
                if top.get("source_part_id") is not None:
                    excerpt_args["source_part_id"] = top.get("source_part_id")
                excerpt_content = await call("get_document_excerpt", "raw_excerpt_lookup", excerpt_args)
                excerpt_failure = classify_failure(excerpt_content)
                if excerpt_failure:
                    return self._failure_result(question, excerpt_failure, timeline, tools_used, tool_outputs, excerpt_content)
                excerpt_evidence = _evidence_from_excerpt(excerpt_content)

            evidence = excerpt_evidence or _evidence_from_results(search_results)
            if evidence:
                return self._success_result(
                    question=question,
                    answer=_answer_from_evidence(question, evidence),
                    status="recovered",
                    citations=[],
                    evidence=evidence,
                    timeline=timeline,
                    tools_used=tools_used,
                    tool_outputs=tool_outputs,
                    content=search_content or {},
                    recovery_attempted=recovery_attempted,
                    recovery_successful=True,
                )

            final_status = "not_found" if _is_not_found(initial.get("answer")) else "not_grounded"
            return OrchestratedRunResult(
                question=question,
                answer="No grounded answer could be produced from the available MCP evidence.",
                grounding_status=final_status,
                tools_used=_dedupe(tools_used),
                execution_timeline=[step.to_dict() for step in timeline],
                tool_outputs=tool_outputs,
                recovery_attempted=recovery_attempted,
                recovery_successful=False,
                portfolio_safe=final_status == "not_found",
                failure_reason=None if final_status == "not_found" else "answer_without_citations_or_evidence",
                error=None if final_status == "not_found" else "answer_without_citations_or_evidence",
            )
        finally:
            reset_current_question(token)

    def _success_result(
        self,
        *,
        question: str,
        answer: str,
        status: str,
        citations: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
        timeline: list[OrchestrationStep],
        tools_used: list[str],
        tool_outputs: list[dict[str, Any]],
        content: dict[str, Any],
        recovery_attempted: bool = False,
        recovery_successful: bool = False,
    ) -> OrchestratedRunResult:
        return OrchestratedRunResult(
            question=question,
            answer=answer,
            grounding_status=status,
            tools_used=_dedupe(tools_used),
            execution_timeline=[step.to_dict() for step in timeline],
            citations=citations,
            evidence=evidence,
            tool_outputs=tool_outputs,
            citation_count=len(citations),
            evidence_count=len(evidence),
            used_chunks_count=content.get("used_chunks_count"),
            mode=content.get("mode"),
            latency_ms=content.get("latency_ms"),
            recovery_attempted=recovery_attempted,
            recovery_successful=recovery_successful,
            portfolio_safe=True,
        )

    def _failure_result(
        self,
        question: str,
        status: str,
        timeline: list[OrchestrationStep],
        tools_used: list[str],
        tool_outputs: list[dict[str, Any]],
        content: dict[str, Any],
    ) -> OrchestratedRunResult:
        failure_reason = _short_error_text(content) or status
        return OrchestratedRunResult(
            question=question,
            answer="No grounded answer could be produced because the MCP/backend tool path failed.",
            grounding_status=status,
            tools_used=_dedupe(tools_used),
            execution_timeline=[step.to_dict() for step in timeline],
            tool_outputs=tool_outputs,
            portfolio_safe=False,
            failure_reason=failure_reason,
            error=failure_reason,
        )


def _dedupe(items: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output


def overall_status(runs: Sequence[dict[str, Any]]) -> str:
    statuses = [str(run.get("grounding_status") or run.get("answer_status") or "") for run in runs]
    if not statuses:
        return "error"
    if any(status in FAILURE_STATUSES for status in statuses):
        if any(status in GROUNDING_SUCCESS_STATUSES for status in statuses):
            return "partial"
        return "error"
    return "ok"
