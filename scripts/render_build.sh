#!/usr/bin/env bash
set -eu

python -m pip install .
mkdir -p .render
if [ -d .render/mcp-server/.git ]; then
  git -C .render/mcp-server fetch origin f8e891d3063772094f21cfa7e8754997ff42f8d2
else
  git clone --filter=blob:none https://github.com/beyondalgorithms2026-source/RAG_Langgraph_MCP_server.git .render/mcp-server
fi
git -C .render/mcp-server checkout f8e891d3063772094f21cfa7e8754997ff42f8d2
