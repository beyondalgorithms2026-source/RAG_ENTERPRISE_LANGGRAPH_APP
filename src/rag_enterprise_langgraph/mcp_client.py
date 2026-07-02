from __future__ import annotations

from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient

from rag_enterprise_langgraph.config import Settings
from rag_enterprise_langgraph.tool_guard import wrap_mcp_tools


def build_stdio_connection(settings: Settings) -> dict[str, Any]:
    return {
        "transport": "stdio",
        "command": settings.resolved_mcp_server_python(),
        "args": settings.mcp_server_args(),
        "cwd": settings.resolved_mcp_server_repo(),
        "env": settings.build_mcp_server_env(),
        "encoding": settings.mcp_server_encoding,
    }


def build_mcp_client(settings: Settings) -> MultiServerMCPClient:
    return MultiServerMCPClient(
        connections={
            settings.mcp_server_name: build_stdio_connection(settings),
        }
    )


async def load_mcp_tools(settings: Settings):
    client = build_mcp_client(settings)
    tools = await client.get_tools(server_name=settings.mcp_server_name)
    return wrap_mcp_tools(tools)
