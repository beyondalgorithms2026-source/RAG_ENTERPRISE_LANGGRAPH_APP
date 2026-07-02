from __future__ import annotations

from rag_enterprise_langgraph.config import Settings
from rag_enterprise_langgraph.mcp_client import build_mcp_client, build_stdio_connection


def test_build_stdio_connection_uses_absolute_paths():
    settings = Settings(
        mcp_server_python="/Users/Work/.local/bin/python3.12",
        mcp_server_repo="/Users/Work/Projects/repos/RAG_ENTERPRISE_MCP_SERVER",
    )

    connection = build_stdio_connection(settings)

    assert connection["transport"] == "stdio"
    assert connection["command"].endswith("python3.12")
    assert connection["args"] == ["-m", "rag_enterprise_mcp.server"]
    assert connection["cwd"] == "/Users/Work/Projects/repos/RAG_ENTERPRISE_MCP_SERVER"


def test_build_mcp_client_registers_single_server():
    settings = Settings(mcp_server_name="rag-enterprise-mcp")
    client = build_mcp_client(settings)
    assert list(client.connections.keys()) == ["rag-enterprise-mcp"]

