# Upwork Proof Artifacts

Use these proof points after the backend and Ollama are running locally.

## Screenshot checklist

1. Test proof: terminal showing `.venv312/bin/pytest` with all tests passing.
2. MCP discovery proof: CLI output showing `tools/list` with `ask_grounded`, `search_documents`, and `get_document_excerpt`.
3. Successful CLI proof: final answer plus visible `tool_outputs`.
4. Backend proof: `RAG_ENTERPRISE_STARTER` backend terminal showing `POST /ask HTTP/1.1 200 OK`.
5. API proof: `curl http://127.0.0.1:8080/ask` returning JSON.
6. Code proof: `mcp_client.py` showing `MultiServerMCPClient` stdio config.
7. Code proof: `graph.py` showing the LangGraph agent and system prompt.
8. Security proof: the architecture diagram below rendered as PNG/SVG.

Do not include secrets, bearer tokens, raw `.env` content, or private document text.

## Architecture and security diagram

```mermaid
flowchart LR
    U["User / API Client"] --> LG["LangGraph Agent<br/>Tool orchestration only"]
    LG -->|stdio MCP| MCP["RAG Enterprise MCP Server<br/>ask_grounded<br/>search_documents<br/>get_document_excerpt"]
    MCP -->|HTTP + auth cookie/token| BE["Enterprise RAG Backend<br/>FastAPI"]
    BE --> AUTH["Auth + ACL Layer<br/>dev/OIDC auth<br/>SQL-level access trimming"]
    BE --> RET["Retrieval Layer<br/>hybrid/vector/keyword/graph modes"]
    BE --> LLM["Backend Answer Model<br/>grounded JSON answer<br/>citations"]
    RET --> DB["Postgres + pgvector<br/>documents, chunks, ACLs"]
    LLM --> BE
    AUTH --> RET
    BE -->|grounded answer + citations| MCP
    MCP -->|structured tool output| LG
    LG -->|final answer + visible tool output| U

    subgraph Security Boundaries
      S1["LangGraph does not access DB"]
      S2["MCP has read-only RAG tools"]
      S3["Backend enforces auth + ACL"]
      S4["Retrieved text treated as untrusted evidence"]
      S5["Tool args validated and normalized"]
    end
```
