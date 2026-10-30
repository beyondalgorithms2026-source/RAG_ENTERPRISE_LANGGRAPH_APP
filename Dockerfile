# Governed RAG app (FastAPI + LangGraph) - port 8080. Built for Coolify (build pack: Dockerfile).
# The app starts the separate MCP server repository as a child process, so that repository is fetched at build time
# at the same pinned commit scripts/render_build.sh uses.

FROM python:3.12-slim AS mcp
ARG MCP_COMMIT=f8e891d3063772094f21cfa7e8754997ff42f8d2
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --filter=blob:none https://github.com/beyondalgorithms2026-source/RAG_Langgraph_MCP_server.git /mcp-server \
    && git -C /mcp-server checkout "$MCP_COMMIT" \
    && rm -rf /mcp-server/.git

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    SPEND_DB_PATH=/data/spend.sqlite \
    RAG_AGENT_MCP_SERVER_REPO=/opt/mcp-server \
    RAG_AGENT_PUBLIC_DEMO=true \
    RAG_AGENT_ENABLE_SYNTHESIS=true \
    RAG_AGENT_MODEL_PROVIDER=anthropic \
    RAG_AGENT_MODEL_NAME=claude-haiku-5-5 \
    RAG_AGENT_MODEL_TEMPERATURE=0 \
    RAG_BACKEND_BASE_URL=https://ragapi.spanfold.com \
    RAG_AGENT_PUBLIC_BACKEND_URL=https://ragapi.spanfold.com \
    RAG_BACKEND_TIMEOUT_SECONDS=300 \
    RAG_AGENT_EVIDENCE_STATUS_PATH=docs/evaluation/status.json \
    RAG_AGENT_RED_TEAM_LATEST_PATH=docs/evaluation/red-team-release.json \
    RAG_AGENT_AUDIT_LOG_PATH=config/demo/audit-log.jsonl \
    RAG_AGENT_RECORDED_COMPARISONS_PATH=config/demo/before-after-recorded.json \
    RAG_AGENT_APPROVALS_PATH=/data/runs/approvals.jsonl \
    RAG_AGENT_EVAL_RUNS_DIR=/data/runs/eval-runs \
    RAG_AGENT_RUN_RESULTS_DIR=/data/runs/run-results

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/
RUN pip install --no-cache-dir .

# Runtime files the app reads by relative path (same ones Render serves).
COPY config/ ./config/
COPY docs/evaluation/ ./docs/evaluation/
COPY --from=mcp /mcp-server /opt/mcp-server

# Non-root user. /data is where the volume is mounted: spend ledger and run records.
RUN useradd --system --uid 10001 --no-create-home app \
    && mkdir -p /data/runs \
    && chown -R app:app /data /app
USER app

EXPOSE 8080

# Slim images have no curl, so the check uses Python. /healthz calls no model and no backend.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "rag_enterprise_langgraph.server:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
