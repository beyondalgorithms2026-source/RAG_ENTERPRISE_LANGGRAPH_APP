from __future__ import annotations

import contextvars
import json
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool

_current_question: contextvars.ContextVar[str] = contextvars.ContextVar(
    "rag_agent_current_question", default=""
)

_ALLOWED_ARGUMENTS = {
    "ask_grounded": {
        "question",
        "k_chunks",
        "mode",
        "filters",
        "deep_research",
        "custom_query",
        "anchor_terms",
        "exact_phrase_bias",
        "expand_neighbors",
        "dry_run",
        "force_rare_keyword_scan",
    },
    "search_documents": {
        "question",
        "k",
        "mode",
        "filters",
        "deep_research",
        "custom_query",
        "anchor_terms",
        "exact_phrase_bias",
        "expand_neighbors",
        "force_rare_keyword_scan",
        "debug",
    },
    "get_document_excerpt": {
        "question",
        "source_id",
        "source_part_id",
        "locator_filter",
        "metadata_filters",
        "mode",
        "max_chars",
    },
}


def set_current_question(question: str):
    return _current_question.set(question)


def reset_current_question(token) -> None:
    _current_question.reset(token)


def _optional_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed < minimum or parsed > maximum:
        return default
    return parsed


def normalize_tool_arguments(
    tool_name: str, arguments: dict[str, Any], fallback_question: str = ""
) -> dict[str, Any]:
    allowed = _ALLOWED_ARGUMENTS.get(tool_name, set())
    normalized = {
        key: value
        for key, value in dict(arguments).items()
        if value is not None and key in allowed
    }

    if not str(normalized.get("question") or "").strip() and fallback_question:
        normalized["question"] = fallback_question

    if normalized.get("filters") == {}:
        normalized.pop("filters")
    if normalized.get("custom_query") == "":
        normalized.pop("custom_query")

    if tool_name == "search_documents":
        normalized["k"] = _optional_int(normalized.get("k", 8), 8, 1, 50)
    elif tool_name == "ask_grounded":
        normalized["k_chunks"] = _optional_int(normalized.get("k_chunks", 6), 6, 1, 20)
    elif tool_name == "get_document_excerpt":
        normalized["max_chars"] = _optional_int(normalized.get("max_chars", 1200), 1200, 100, 4000)

    if tool_name == "search_documents":
        normalized["debug"] = False

    return normalized


def _error_payload(tool_name: str, arguments: dict[str, Any], error: Exception) -> str:
    return json.dumps(
        {
            "tool_name": tool_name,
            "is_error": True,
            "error": str(error),
            "normalized_arguments": arguments,
        },
        indent=2,
        sort_keys=True,
    )


def wrap_mcp_tool(tool: BaseTool) -> BaseTool:
    async def _call(**kwargs: Any) -> Any:
        arguments = normalize_tool_arguments(tool.name, kwargs, _current_question.get())
        try:
            return await tool.ainvoke(arguments)
        except Exception as exc:
            return _error_payload(tool.name, arguments, exc)

    return StructuredTool.from_function(
        coroutine=_call,
        name=tool.name,
        description=tool.description,
        args_schema=getattr(tool, "args", None),
    )


def wrap_mcp_tools(tools: list[BaseTool]) -> list[BaseTool]:
    return [wrap_mcp_tool(tool) for tool in tools]
