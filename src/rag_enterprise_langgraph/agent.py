from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

from rag_enterprise_langgraph.config import Settings
from rag_enterprise_langgraph.graph import build_agent_graph
from rag_enterprise_langgraph.mcp_client import load_mcp_tools
from rag_enterprise_langgraph.tool_guard import reset_current_question, set_current_question


@dataclass
class AgentRunResult:
    question: str
    answer: str
    tool_outputs: list[dict[str, Any]]
    message_count: int
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "answer": self.answer,
            "tool_outputs": self.tool_outputs,
            "message_count": self.message_count,
            "error": self.error,
        }


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
                else:
                    parts.append(json.dumps(item, indent=2, sort_keys=True))
                continue
            parts.append(str(item))
        return "\n".join(part for part in parts if part.strip())
    return str(content)


def _maybe_parse_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def extract_tool_outputs(messages: list[BaseMessage]) -> list[dict[str, Any]]:
    outputs: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        raw_text = _content_to_text(message.content)
        outputs.append(
            {
                "tool_name": message.name,
                "tool_call_id": message.tool_call_id,
                "content": _maybe_parse_json(raw_text),
            }
        )
    return outputs


def extract_final_answer(messages: list[BaseMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage) and not message.tool_calls:
            text = _content_to_text(message.content).strip()
            if text:
                return text
    return ""


class RagEnterpriseAgent:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()
        self._tools = None
        self._graph = None

    async def _get_graph(self):
        if self._graph is None:
            self._tools = await load_mcp_tools(self.settings)
            self._graph = build_agent_graph(self.settings, self._tools)
        return self._graph

    async def check_configuration(self) -> dict[str, Any]:
        tools = await load_mcp_tools(self.settings)
        return {
            **self.settings.diagnostic_summary(),
            "mcp_tool_names": [tool.name for tool in tools],
        }

    async def run(self, question: str) -> AgentRunResult:
        graph = await self._get_graph()
        token = set_current_question(question)
        try:
            state = await graph.ainvoke({"messages": [{"role": "user", "content": question}]})
            messages = state["messages"]
            return AgentRunResult(
                question=question,
                answer=extract_final_answer(messages),
                tool_outputs=extract_tool_outputs(messages),
                message_count=len(messages),
            )
        except Exception as exc:
            return AgentRunResult(
                question=question,
                answer="",
                tool_outputs=[
                    {
                        "tool_name": "agent",
                        "tool_call_id": None,
                        "content": {"is_error": True, "error": str(exc)},
                    }
                ],
                message_count=0,
                error=str(exc),
            )
        finally:
            reset_current_question(token)
