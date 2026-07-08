from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import dotenv_values


DEFAULT_MCP_REPO = Path("/Users/Work/Projects/repos/RAG_ENTERPRISE_MCP_SERVER")
DEFAULT_MCP_PYTHON = Path("/Users/Work/.local/bin/python3.12")
DEFAULT_BACKEND_ENV_KEYS = (
    "RAG_BACKEND_BASE_URL",
    "RAG_BACKEND_TIMEOUT_SECONDS",
    "RAG_BACKEND_BEARER_TOKEN",
    "RAG_BACKEND_DEV_LOGIN_EMAIL",
    "RAG_BACKEND_DEV_LOGIN_PASSWORD",
)
BACKEND_ENV_DEFAULTS = {
    "RAG_BACKEND_BASE_URL": "http://127.0.0.1:8000",
    "RAG_BACKEND_TIMEOUT_SECONDS": "30",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RAG_AGENT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "rag-enterprise-agent"
    debug: bool = False

    model_provider: str = "openai"
    model_name: str = "gpt-4.1-mini"
    model_temperature: float = 0.0

    mcp_server_name: str = "rag-enterprise-mcp"
    mcp_server_python: Path = Field(default=DEFAULT_MCP_PYTHON)
    mcp_server_repo: Path = Field(default=DEFAULT_MCP_REPO)
    mcp_server_module: str = "rag_enterprise_mcp.server"
    mcp_server_version: str = "0.1.0"
    mcp_server_encoding: str = "utf-8"
    mcp_env_passthrough: str = ""

    api_host: str = "127.0.0.1"
    api_port: int = 8080

    audit_log_path: str = "runs/audit-log.jsonl"
    approvals_path: str = "runs/approvals.jsonl"
    eval_runs_dir: str = "runs/eval-runs"
    red_team_findings_path: str = "config/red-team-findings.json"
    red_team_latest_path: str = "runs/red-team/latest.json"

    input_token_cost_per_1m: float = 3.0
    output_token_cost_per_1m: float = 15.0
    default_estimated_tokens_per_query: int = 2500

    def _dotenv_values(self) -> dict[str, str]:
        values = dotenv_values(".env")
        return {key: str(value).strip() for key, value in values.items() if value is not None}

    def backend_env_value(self, key: str) -> str:
        value = os.environ.get(key)
        if value is not None and value.strip():
            return value.strip()
        dotenv_value = self._dotenv_values().get(key)
        if dotenv_value:
            return dotenv_value
        return BACKEND_ENV_DEFAULTS.get(key, "")

    def resolved_mcp_server_python(self) -> str:
        return str(self.mcp_server_python.expanduser().resolve())

    def resolved_mcp_server_repo(self) -> str:
        return str(self.mcp_server_repo.expanduser().resolve())

    def mcp_server_args(self) -> list[str]:
        return ["-m", self.mcp_server_module]

    def extra_passthrough_env_keys(self) -> list[str]:
        raw_keys = [item.strip() for item in self.mcp_env_passthrough.split(",")]
        return [item for item in raw_keys if item]

    def build_mcp_server_env(self) -> dict[str, str]:
        env: dict[str, str] = {}
        for key in DEFAULT_BACKEND_ENV_KEYS + tuple(self.extra_passthrough_env_keys()):
            value = self.backend_env_value(key)
            if value:
                env[key] = value
        existing_pythonpath = os.environ.get("PYTHONPATH", "").strip()
        repo_src = str((self.mcp_server_repo.expanduser().resolve() / "src"))
        env["PYTHONPATH"] = repo_src if not existing_pythonpath else f"{repo_src}{os.pathsep}{existing_pythonpath}"
        env["MCP_SERVER_NAME"] = self.mcp_server_name
        env["MCP_SERVER_VERSION"] = self.mcp_server_version
        return env

    def diagnostic_summary(self) -> dict[str, object]:
        return {
            "app_name": self.app_name,
            "debug": self.debug,
            "model_provider": self.model_provider,
            "model_name": self.model_name,
            "mcp_server_name": self.mcp_server_name,
            "mcp_server_python": self.resolved_mcp_server_python(),
            "mcp_server_repo": self.resolved_mcp_server_repo(),
            "mcp_server_module": self.mcp_server_module,
            "backend_base_url": self.backend_env_value("RAG_BACKEND_BASE_URL"),
            "backend_timeout_seconds": self.backend_env_value("RAG_BACKEND_TIMEOUT_SECONDS"),
            "backend_bearer_token_present": bool(self.backend_env_value("RAG_BACKEND_BEARER_TOKEN")),
            "backend_dev_login_email_present": bool(self.backend_env_value("RAG_BACKEND_DEV_LOGIN_EMAIL")),
            "backend_dev_login_password_present": bool(self.backend_env_value("RAG_BACKEND_DEV_LOGIN_PASSWORD")),
        }
