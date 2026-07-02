from __future__ import annotations

from rag_enterprise_langgraph.config import Settings


def test_build_mcp_server_env_includes_backend_and_server_values(monkeypatch):
    monkeypatch.setenv("RAG_BACKEND_BASE_URL", "http://127.0.0.1:8000")
    monkeypatch.setenv("RAG_BACKEND_BEARER_TOKEN", "secret")
    monkeypatch.setenv("EXTRA_ONE", "value-1")
    monkeypatch.setenv("PYTHONPATH", "/tmp/existing")

    settings = Settings(
        mcp_server_name="rag-enterprise-mcp",
        mcp_server_version="0.2.0",
        mcp_env_passthrough="EXTRA_ONE, EXTRA_TWO",
    )

    env = settings.build_mcp_server_env()

    assert env["RAG_BACKEND_BASE_URL"] == "http://127.0.0.1:8000"
    assert env["RAG_BACKEND_BEARER_TOKEN"] == "secret"
    assert env["EXTRA_ONE"] == "value-1"
    assert env["PYTHONPATH"].startswith("/Users/Work/Projects/repos/RAG_ENTERPRISE_MCP_SERVER/src")
    assert env["PYTHONPATH"].endswith("/tmp/existing")
    assert env["MCP_SERVER_NAME"] == "rag-enterprise-mcp"
    assert env["MCP_SERVER_VERSION"] == "0.2.0"
    assert "EXTRA_TWO" not in env


def test_build_mcp_server_env_reads_backend_values_from_dotenv(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("RAG_BACKEND_BASE_URL", raising=False)
    monkeypatch.delenv("RAG_BACKEND_DEV_LOGIN_EMAIL", raising=False)
    monkeypatch.delenv("RAG_BACKEND_DEV_LOGIN_PASSWORD", raising=False)
    monkeypatch.delenv("PYTHONPATH", raising=False)
    tmp_path.joinpath(".env").write_text(
        "\n".join(
            [
                "RAG_BACKEND_BASE_URL=http://127.0.0.1:8000",
                "RAG_BACKEND_DEV_LOGIN_EMAIL=test-user@ragenterprise.local",
                "RAG_BACKEND_DEV_LOGIN_PASSWORD=password123",
            ]
        )
    )

    env = Settings().build_mcp_server_env()

    assert env["RAG_BACKEND_BASE_URL"] == "http://127.0.0.1:8000"
    assert env["RAG_BACKEND_DEV_LOGIN_EMAIL"] == "test-user@ragenterprise.local"
    assert env["RAG_BACKEND_DEV_LOGIN_PASSWORD"] == "password123"


def test_diagnostic_summary_redacts_backend_secrets(monkeypatch):
    monkeypatch.setenv("RAG_BACKEND_BEARER_TOKEN", "secret")
    monkeypatch.setenv("RAG_BACKEND_DEV_LOGIN_PASSWORD", "password123")

    summary = Settings().diagnostic_summary()

    assert summary["backend_bearer_token_present"] is True
    assert summary["backend_dev_login_password_present"] is True
    assert "secret" not in str(summary)
    assert "password123" not in str(summary)


def test_mcp_server_args_are_explicit():
    settings = Settings(mcp_server_module="rag_enterprise_mcp.server")
    assert settings.mcp_server_args() == ["-m", "rag_enterprise_mcp.server"]
