#!/usr/bin/env bash
set -eu

python -m pip install .
mkdir -p .render
if [ -d .render/mcp-server/.git ]; then
  git -C .render/mcp-server fetch origin 986de635e93cae0c31b3f64bf0eef7bc77af9b90
else
  git clone --filter=blob:none https://github.com/beyondalgorithms2026-source/RAG_Langgraph_MCP_server.git .render/mcp-server
fi
git -C .render/mcp-server checkout 986de635e93cae0c31b3f64bf0eef7bc77af9b90
