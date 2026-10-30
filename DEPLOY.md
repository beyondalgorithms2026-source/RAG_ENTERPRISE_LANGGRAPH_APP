# Deploying the governed RAG app (LangGraph) on Coolify

Branch `deploy/coolify` (made from `main`). The container runs the FastAPI app on port 8080. It starts the separate MCP server
repository (`RAG_Langgraph_MCP_server`) as a child process, so the Dockerfile fetches that repository at build time, pinned to the
same commit as `scripts/render_build.sh`. That build step needs outbound internet access to GitHub.
Deploy the Starter API (`ragapi.spanfold.com`) first: this app calls it.

## Coolify fields

| Field | Value |
|---|---|
| Build pack | Dockerfile |
| Base directory | `/` |
| Dockerfile location | `/Dockerfile` |
| Ports Exposes | 8080 |
| Domain | https://governance.spanfold.com |
| Health check path | `/healthz` (HTTP 200, `{"status":"ok"}`; no backend or model call) |
| Persistent storage | Volume, destination path `/data` |
| Memory limit | 512 MB (raise to 768 MB if Coolify reports the container being killed) |
| Replicas | 1 |

DNS: add an A record `governance` pointing at the server.

## Environment variables to type in

Names match `.env.example` (deploy section at the bottom).

- **Secrets (mark "Is secret"):** `ANTHROPIC_API_KEY`. Add `RAG_BACKEND_BEARER_TOKEN` only if the Starter API stops allowing anonymous public access.
- **Address of the data layer (new env var, default `https://ragapi.spanfold.com`):** `RAG_BACKEND_BASE_URL` (used by the MCP child) and `RAG_AGENT_PUBLIC_BACKEND_URL` (shown to the browser UI). Both are baked into the image with that default; change them in Coolify if the Starter API moves. Before, these were typed into `render.yaml` as the Render address.
- **Browser access:** `ALLOWED_ORIGINS=https://spanfold.com,https://www.spanfold.com` (default if unset)
- **Spend caps (defaults shown):** `DAILY_SPEND_CAP_USD=0.50`, `MONTHLY_SPEND_CAP_USD=5`, `EST_COST_PER_CALL_USD=0.01`
- **Already baked into the image (same values as `render.yaml`):** `RAG_AGENT_PUBLIC_DEMO=true`, `RAG_AGENT_ENABLE_SYNTHESIS=true`, `RAG_AGENT_MODEL_PROVIDER`, `RAG_AGENT_MODEL_NAME`, `RAG_AGENT_MODEL_TEMPERATURE=0`, `RAG_BACKEND_TIMEOUT_SECONDS=300`, `RAG_AGENT_MCP_SERVER_REPO=/opt/mcp-server`, the evidence, audit-log and recorded-comparison paths, and `SPEND_DB_PATH=/data/spend.sqlite`. Approvals, eval runs and run results are written to `/data/runs`.

## Spend caps and 429

This app is not given token counts by the model layer, so each answered question (`POST /ask`, `/ask-orchestrated`, `/demo/before-after`) is counted at `EST_COST_PER_CALL_USD` (default 0.01, because one governed question makes several model calls). Adjust it after you see real bills. Over the daily or monthly cap those requests answer HTTP 429: "This demo has reached its daily limit. Please try again tomorrow." Evidence pages, the UI and `/healthz` keep working. In the public demo, operator-only actions stay disabled as before.

## Memory estimate

About 300-500 MB (LangChain and LangGraph, no local model) plus about 50 MB for the MCP child process. The Starter API's own spend is counted separately in its own ledger.

## Known limits

- The audit log (`config/demo/audit-log.jsonl`, a committed demo file) is read from the image and new entries are lost on each redeploy, as on Render. To keep new entries, set `RAG_AGENT_AUDIT_LOG_PATH=/data/runs/audit-log.jsonl` (the demo entries would then not be shown).
- The Starter API's allow-list (`ALLOWED_ORIGINS` there) must include `https://governance.spanfold.com` if the browser calls it directly.
- The MCP repository is cloned from GitHub when the image is built. If that repository is private or GitHub is unreachable, the build fails.

## Before you build

The Docker engine was not running when this was prepared, so the image has not been built. The first Coolify build is its first real test.
Tests: 367 passed, offline and fake-driven. They do not prove live retrieval or full-stack answers.
