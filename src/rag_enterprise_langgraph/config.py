from __future__ import annotations

import os
import sys
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import dotenv_values


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or points somewhere unusable.

    Carries a message naming the environment variable and what it should be set
    to, so the failure is actionable without reading this file.
    """


# The MCP server lives in its own repository, so its location cannot be guessed
# and has no default: see resolved_mcp_server_repo(). The interpreter, by
# contrast, defaults to the one already running, which is correct whenever the
# MCP server is installed into the same environment as this app.
def _default_mcp_python() -> Path:
    return Path(sys.executable)


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

    # Local by default: the whole system is designed to run on your own hardware
    # with no data leaving it. Set RAG_AGENT_MODEL_PROVIDER=openai (or any other
    # provider supported by init_chat_model) to use a hosted model instead.
    model_provider: str = "ollama"
    model_name: str = "gemma3:4b-it-qat"
    model_temperature: float = 0.0

    mcp_server_name: str = "rag-enterprise-mcp"
    mcp_server_python: Path = Field(default_factory=_default_mcp_python)
    mcp_server_repo: Path | None = Field(default=None)
    mcp_server_module: str = "rag_enterprise_mcp.server"
    mcp_server_version: str = "0.1.0"
    mcp_server_encoding: str = "utf-8"
    mcp_env_passthrough: str = ""

    api_host: str = "127.0.0.1"
    api_port: int = 8080

    audit_log_path: str = "runs/audit-log.jsonl"
    approvals_path: str = "runs/approvals.jsonl"
    eval_runs_dir: str = "runs/eval-runs"
    run_results_dir: str = "runs/run-results"
    red_team_findings_path: str = "config/red-team-findings.json"
    red_team_latest_path: str = "runs/red-team/latest.json"

    input_token_cost_per_1m: float = 3.0
    output_token_cost_per_1m: float = 15.0
    default_estimated_tokens_per_query: int = 2500

    # Grounded synthesis (Tier 2): when enabled, the recovery path composes a
    # readable answer from the retrieved verbatim evidence and only shows it if
    # it passes verification against the source. Default off keeps the layer
    # non-generative and the answer purely extractive.
    enable_synthesis: bool = False

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
        # Absolute but NOT symlink-resolved: a virtualenv's bin/python is a
        # symlink to the base interpreter, and resolving it would spawn the MCP
        # server outside the environment the app was installed into.
        return os.path.abspath(os.path.expanduser(str(self.mcp_server_python)))

    def resolved_mcp_server_repo(self) -> str:
        if self.mcp_server_repo is None:
            raise ConfigError(
                "RAG_AGENT_MCP_SERVER_REPO is not set and has no default. Set it to your "
                "local clone of the RAG_ENTERPRISE_MCP_SERVER repository, for example:\n"
                "  RAG_AGENT_MCP_SERVER_REPO=/path/to/RAG_ENTERPRISE_MCP_SERVER\n"
                "The MCP server is a separate repository because the agent layer has no "
                "direct data access. See .env.example and the README."
            )
        return str(self.mcp_server_repo.expanduser().resolve())

    def validate_paths(self) -> None:
        """Check the configured paths before anything tries to spawn a subprocess.

        Called at start-up so a misconfigured checkout fails with an explanation
        rather than an opaque error from the child process.
        """
        repo = Path(self.resolved_mcp_server_repo())
        if not repo.is_dir():
            raise ConfigError(
                f"RAG_AGENT_MCP_SERVER_REPO points at '{repo}', which does not exist. "
                "Set it to your local clone of the RAG_ENTERPRISE_MCP_SERVER repository."
            )
        if not (repo / "src" / "rag_enterprise_mcp").is_dir():
            raise ConfigError(
                f"RAG_AGENT_MCP_SERVER_REPO points at '{repo}', which does not look like "
                "the MCP server repository: expected to find src/rag_enterprise_mcp/ "
                "inside it."
            )
        python = Path(self.resolved_mcp_server_python())
        if not python.exists():
            raise ConfigError(
                f"RAG_AGENT_MCP_SERVER_PYTHON points at '{python}', which does not exist. "
                "Leave it unset to use the interpreter running this app."
            )

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
        repo_src = str(Path(self.resolved_mcp_server_repo()) / "src")
        env["PYTHONPATH"] = repo_src if not existing_pythonpath else f"{repo_src}{os.pathsep}{existing_pythonpath}"
        env["MCP_SERVER_NAME"] = self.mcp_server_name
        env["MCP_SERVER_VERSION"] = self.mcp_server_version
        return env

    def diagnostic_summary(self) -> dict[str, object]:
        # A diagnostic must describe a broken configuration rather than fail on it.
        try:
            mcp_server_repo = self.resolved_mcp_server_repo()
        except ConfigError:
            mcp_server_repo = "<not set: RAG_AGENT_MCP_SERVER_REPO>"
        return {
            "app_name": self.app_name,
            "debug": self.debug,
            "model_provider": self.model_provider,
            "model_name": self.model_name,
            "mcp_server_name": self.mcp_server_name,
            "mcp_server_python": self.resolved_mcp_server_python(),
            "mcp_server_repo": mcp_server_repo,
            "mcp_server_module": self.mcp_server_module,
            "backend_base_url": self.backend_env_value("RAG_BACKEND_BASE_URL"),
            "backend_timeout_seconds": self.backend_env_value("RAG_BACKEND_TIMEOUT_SECONDS"),
            "backend_bearer_token_present": bool(self.backend_env_value("RAG_BACKEND_BEARER_TOKEN")),
            "backend_dev_login_email_present": bool(self.backend_env_value("RAG_BACKEND_DEV_LOGIN_EMAIL")),
            "backend_dev_login_password_present": bool(self.backend_env_value("RAG_BACKEND_DEV_LOGIN_PASSWORD")),
        }
