from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
import subprocess
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


@contextmanager
def suppress_mcp_stdio_stderr(enabled: bool = True):
    """Silence child MCP server stderr during portfolio proof runs.

    The MCP SDK routes stdio server stderr to the parent terminal by default.
    That is useful while debugging, but it makes proof screenshots noisy and can
    leak local paths in tracebacks. This local monkeypatch is scoped to the
    caller and avoids changing the MCP server repo.
    """
    if not enabled:
        yield
        return

    try:
        import langchain_mcp_adapters.sessions as adapter_sessions
        import mcp.client.stdio as mcp_stdio
    except Exception:
        yield
        return

    original_adapter_stdio_client = adapter_sessions.stdio_client
    original_mcp_stdio_client = mcp_stdio.stdio_client

    @asynccontextmanager
    async def quiet_stdio_client(server, errlog=None):  # noqa: ANN001
        async with original_mcp_stdio_client(server, errlog=subprocess.DEVNULL) as streams:
            yield streams

    adapter_sessions.stdio_client = quiet_stdio_client
    mcp_stdio.stdio_client = quiet_stdio_client
    try:
        yield
    finally:
        adapter_sessions.stdio_client = original_adapter_stdio_client
        mcp_stdio.stdio_client = original_mcp_stdio_client
