"""Verify the live APP/MCP/STARTER tool boundary without model or database access."""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

EXPECTED = {
    "ask_grounded": {
        "request": "AskRequest",
        "properties": {
            "question",
            "k_chunks",
            "mode",
            "filters",
            "deep_research",
            "custom_query",
            "anchor_terms",
            "exact_phrase_bias",
            "expand_neighbors",
            "dry_run",
            "force_rare_keyword_scan",
        },
        "response": "AskResponse",
        "response_fields": {
            "answer",
            "citations",
            "used_chunks_count",
            "latency_ms",
            "mode",
            "debug_info",
        },
    },
    "search_documents": {
        "request": "SearchRequest",
        "properties": {
            "question",
            "k",
            "mode",
            "filters",
            "deep_research",
            "custom_query",
            "anchor_terms",
            "exact_phrase_bias",
            "expand_neighbors",
            "force_rare_keyword_scan",
            "debug",
        },
        "response": "SearchResponse",
        "response_fields": {"results", "latency_ms", "mode", "debug_info"},
    },
    "get_document_excerpt": {
        "request": "SearchRequest",
        "properties": {
            "question",
            "source_id",
            "source_part_id",
            "locator_filter",
            "metadata_filters",
            "mode",
            "max_chars",
        },
        "response": "SearchResponse",
        "response_fields": {"results", "latency_ms", "mode", "debug_info"},
    },
}


def _class_fields(path: Path) -> dict[str, set[str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    output: dict[str, set[str]] = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            output[node.name] = {
                item.target.id
                for item in node.body
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)
            }
    return output


def _string_collection_assignment(path: Path, name: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            value = ast.literal_eval(node.value)
            return {str(item) for item in value}
    raise SystemExit(f"Unable to locate {name} in {path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--mcp", type=Path, required=True)
    parser.add_argument("--starter", type=Path, required=True)
    args = parser.parse_args()

    sys.path.insert(0, str(args.mcp / "src"))
    from rag_enterprise_mcp.tools import TOOLS

    tools = {tool["name"]: tool for tool in TOOLS}
    if set(tools) != set(EXPECTED):
        raise SystemExit(f"MCP tool names drifted: {sorted(tools)}")

    required_tools = _string_collection_assignment(
        args.app / "src/rag_enterprise_langgraph/demo_proof.py", "REQUIRED_MCP_TOOLS"
    )
    if required_tools != set(EXPECTED):
        raise SystemExit(f"APP required tool names drifted: {sorted(required_tools)}")

    request_fields = {}
    request_fields.update(_class_fields(args.starter / "backend/app/core_rag/answering.py"))
    request_fields.update(_class_fields(args.starter / "backend/app/core_rag/retrieval.py"))
    for name, contract in EXPECTED.items():
        schema = tools[name]["inputSchema"]
        properties = set(schema.get("properties", {}))
        if properties != contract["properties"]:
            raise SystemExit(f"{name} MCP properties drifted: {sorted(properties)}")
        if schema.get("required") != ["question"]:
            raise SystemExit(f"{name} must require question")
        backend_request_fields = request_fields.get(contract["request"], set())
        forwarded = properties
        if name == "get_document_excerpt":
            forwarded = {
                "question",
                "k",
                "mode",
                "filters",
                "debug",
                "deep_research",
                "anchor_terms",
                "expand_neighbors",
                "force_rare_keyword_scan",
            }
        if not forwarded <= backend_request_fields:
            raise SystemExit(
                f"{name} sends unsupported backend fields: {sorted(forwarded - backend_request_fields)}"
            )
        backend_response_fields = request_fields.get(contract["response"], set())
        if not contract["response_fields"] <= backend_response_fields:
            raise SystemExit(f"{name} backend response is missing consumed fields")

    print("Cross-repository APP/MCP/STARTER contracts are compatible.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
