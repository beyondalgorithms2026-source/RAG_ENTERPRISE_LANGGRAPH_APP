# Render public governance demo

This Blueprint deploys the FastAPI app UI at `/app` and connects it, through the
pinned MCP server commit, to the separate public starter backend. No database or
model-provider secret belongs in this service.

## Owner deployment steps

1. Open Render, choose **New + → Blueprint**, and connect this GitHub repository.
2. Select the repository's `render.yaml` and apply the proposed Free Singapore web service.
3. Wait until the deploy is live and `/healthz` returns `{"status":"ok"}`.
4. Send the public service URL to the implementation thread for incognito, mobile,
   four-preset, full-source-link, and security smoke checks.

The first request can be slow because both Free Render services may be asleep. Before a
retrieval or answer POST, the pinned MCP client checks the backend's read-only `/health`
endpoint and waits through Render wake pages or transient 502/503/504 responses with
bounded backoff. It sends the potentially paid POST only after health reports `ok`, so
wake recovery cannot duplicate a model request. The 120-second backend timeout bounds
that readiness wait and accommodates the measured backend cold start.

## Public-demo boundaries

- Visitors can run the governed `/ask-orchestrated` path.
- Approval requests may be created internally by high-risk routing, but public
  visitors cannot create, approve, or reject them through the approval API.
- Pending answers are withheld from public approval reads.
- Direct model chat, before/after double-runs, eval execution, and red-team
  execution are disabled. Saved eval/red-team findings remain viewable.
- Run, audit, and approval files use Render's ephemeral filesystem and can reset
  after a restart or deploy. This is a portfolio demo, not durable production storage.
