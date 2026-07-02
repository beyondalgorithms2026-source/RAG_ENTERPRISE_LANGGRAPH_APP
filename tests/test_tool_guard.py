from __future__ import annotations

import asyncio

from langchain_core.tools import tool

from rag_enterprise_langgraph.tool_guard import normalize_tool_arguments, reset_current_question, set_current_question, wrap_mcp_tool


def test_normalize_search_documents_clamps_invalid_k_and_cleans_empty_values():
    normalized = normalize_tool_arguments(
        "search_documents",
        {
            "question": "Q",
            "k": 0,
            "filters": {},
            "custom_query": "",
            "mode": "hybrid",
            "exact_phrase_bias": None,
        },
    )

    assert normalized == {"question": "Q", "k": 8, "mode": "hybrid"}


def test_normalize_ask_grounded_clamps_invalid_k_chunks_and_injects_question():
    normalized = normalize_tool_arguments(
        "ask_grounded",
        {"k_chunks": 0, "mode": "hybrid"},
        fallback_question="Original question",
    )

    assert normalized == {"question": "Original question", "k_chunks": 6, "mode": "hybrid"}


async def _capture_search_documents(question: str, k: int = 8) -> str:
    """Capture normalized search arguments."""
    return f"{question}:{k}"


def test_wrapped_tool_normalizes_before_invocation():
    original = tool("search_documents")(_capture_search_documents)
    wrapped = wrap_mcp_tool(original)
    token = set_current_question("Fallback question")
    try:
        result = asyncio.run(wrapped.ainvoke({"k": 0}))
    finally:
        reset_current_question(token)

    assert result == "Fallback question:8"
