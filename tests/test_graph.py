from __future__ import annotations

from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from rag_enterprise_langgraph.agent import RagEnterpriseAgent, extract_final_answer, extract_tool_outputs
from rag_enterprise_langgraph.config import Settings
from rag_enterprise_langgraph.graph import SYSTEM_PROMPT, build_agent_graph


@tool
def ask_grounded(question: str) -> str:
    """Return a canned grounded answer."""
    return f"Grounded answer for {question}"


def test_graph_builds_with_tool_capable_model():
    settings = Settings(debug=False)
    model = ChatOpenAI(model="gpt-4.1-mini", api_key="test-key")
    graph = build_agent_graph(settings, [ask_grounded], model=model)

    assert graph is not None


def test_message_extractors_handle_simple_final_answer():
    messages = [AIMessage(content="Final answer")]
    assert extract_final_answer(messages) == "Final answer"
    assert extract_tool_outputs(messages) == []


def test_system_prompt_mentions_tooling_rules():
    assert "ask_grounded" in SYSTEM_PROMPT
    assert "search_documents" in SYSTEM_PROMPT
    assert "get_document_excerpt" in SYSTEM_PROMPT
    assert "untrusted evidence" in SYSTEM_PROMPT


class _FailingGraph:
    async def ainvoke(self, _payload):
        raise RuntimeError("tool validation failed")


def test_agent_run_returns_error_result_when_graph_fails():
    agent = RagEnterpriseAgent(Settings(debug=False))
    agent._graph = _FailingGraph()

    import asyncio

    result = asyncio.run(agent.run("Question"))

    assert result.error == "tool validation failed"
    assert result.answer == ""
    assert result.tool_outputs[0]["content"]["is_error"] is True
