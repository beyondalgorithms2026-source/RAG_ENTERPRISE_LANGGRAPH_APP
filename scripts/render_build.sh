#!/usr/bin/env bash
set -eu

python -m pip install .
mkdir -p .render
if [ -d .render/mcp-server/.git ]; then
  git -C .render/mcp-server fetch origin 5d814f171af142085707b6421a373fe5360c0081
else
  git clone --filter=blob:none https://github.com/beyondalgorithms2026-source/RAG_Langgraph_MCP_server.git .render/mcp-server
fi
git -C .render/mcp-server checkout 5d814f171af142085707b6421a373fe5360c0081
