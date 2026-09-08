#!/usr/bin/env bash
set -eu

python -m pip install .
mkdir -p .render
if [ -d .render/mcp-server/.git ]; then
  git -C .render/mcp-server fetch origin d0121436bde84fcd3cb6dc911c98958be08ac4af
else
  git clone --filter=blob:none https://github.com/beyondalgorithms2026-source/RAG_Langgraph_MCP_server.git .render/mcp-server
fi
git -C .render/mcp-server checkout d0121436bde84fcd3cb6dc911c98958be08ac4af
