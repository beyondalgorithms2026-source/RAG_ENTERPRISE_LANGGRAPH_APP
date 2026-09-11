# APP, MCP, and STARTER integration contract

APP calls three read-only MCP tools over stdio. MCP validates JSON-RPC input and forwards
compatible HTTP payloads to STARTER. STARTER alone retrieves data and applies SQL ACLs.
APP never receives database credentials and MCP never changes retrieval or authorization
policy.

| Tool | STARTER route/model | Purpose |
|---|---|---|
| `ask_grounded` | `/ask` / `AskRequest` | Grounded answer and citations |
| `search_documents` | `/search` / `SearchRequest` | Retrieval-only candidates |
| `get_document_excerpt` | `/search` / `SearchRequest` | One ACL-trimmed scoped excerpt |

The mechanical contract check compares APP's required inventory, MCP's live JSON schemas,
and STARTER's request/response model fields. Additive backend fields remain compatible;
MCP-exposed fields must be accepted by STARTER. Breaking changes use an
expand–migrate–contract sequence across repositories.

Structured validation, authentication, readiness, timeout, transport, and backend errors
must remain distinguishable. Retrieved content and backend diagnostics are untrusted and
must not become instructions or leak through public output.

Run from APP with sibling checkouts:

```bash
python scripts/check_cross_repo_contracts.py \
  --app . \
  --mcp ../RAG_ENTERPRISE_MCP_SERVER \
  --starter ../RAG_ENTERPRISE_STARTER
```
