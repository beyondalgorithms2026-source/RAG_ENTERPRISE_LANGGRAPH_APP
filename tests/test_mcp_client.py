from __future__ import annotations

from rag_enterprise_langgraph.config import Settings
from rag_enterprise_langgraph.mcp_client import build_mcp_client, build_stdio_connection


def test_build_stdio_connection_uses_absolute_paths(tmp_path):
    repo = tmp_path / "RAG_ENTERPRISE_MCP_SERVER"
    python = tmp_path / "bin" / "python3.12"
    settings = Settings(mcp_server_python=python, mcp_server_repo=repo)

    connection = build_stdio_connection(settings)

    assert connection["transport"] == "stdio"
    assert connection["command"] == str(python)
    assert connection["args"] == ["-m", "rag_enterprise_mcp.server"]
    assert connection["cwd"] == str(repo.resolve())


def test_build_mcp_client_registers_single_server(tmp_path):
    settings = Settings(mcp_server_name="rag-enterprise-mcp", mcp_server_repo=tmp_path)
    client = build_mcp_client(settings)
    assert list(client.connections.keys()) == ["rag-enterprise-mcp"]

