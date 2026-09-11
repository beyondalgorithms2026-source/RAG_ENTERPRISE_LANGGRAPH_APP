"""Verify the live APP/MCP/STARTER boundary without a model or database."""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path
from typing import Any

MODES = ["vector", "keyword", "hybrid", "graph_hybrid", "full"]
FILTER_SCHEMA = {"type": "object"}

EXPECTED_SCHEMAS: dict[str, dict[str, dict[str, Any]]] = {
    "ask_grounded": {
        "question": {"type": "string", "description": "The user question to answer."},
        "k_chunks": {"type": "integer", "minimum": 1, "maximum": 20, "default": 6},
        "mode": {"type": "string", "enum": MODES},
        "filters": FILTER_SCHEMA,
        "deep_research": {"type": "boolean", "default": False},
        "custom_query": {"type": "string"},
        "anchor_terms": {"type": "array", "items": {"type": "string"}},
        "exact_phrase_bias": {"type": "string"},
        "expand_neighbors": {"type": "boolean", "default": False},
        "dry_run": {"type": "boolean", "default": False},
        "force_rare_keyword_scan": {"type": "boolean", "default": False},
    },
    "search_documents": {
        "question": {"type": "string"},
        "k": {"type": "integer", "minimum": 1, "maximum": 50, "default": 8},
        "mode": {"type": "string", "enum": MODES},
        "filters": FILTER_SCHEMA,
        "deep_research": {"type": "boolean", "default": False},
        "custom_query": {"type": "string"},
        "anchor_terms": {"type": "array", "items": {"type": "string"}},
        "exact_phrase_bias": {"type": "string"},
        "expand_neighbors": {"type": "boolean", "default": False},
        "force_rare_keyword_scan": {"type": "boolean", "default": False},
        "debug": {"type": "boolean", "default": False},
    },
    "get_document_excerpt": {
        "question": {"type": "string"},
        "source_id": {"type": "integer"},
        "source_part_id": {"type": "integer"},
        "locator_filter": {"type": "string"},
        "metadata_filters": {"type": "object"},
        "mode": {"type": "string", "enum": MODES, "default": "keyword"},
        "max_chars": {
            "type": "integer",
            "minimum": 100,
            "maximum": 4000,
            "default": 1200,
        },
    },
}

BACKEND_REQUESTS = {
    "ask_grounded": ("AskRequest", "backend/app/core_rag/answering.py"),
    "search_documents": ("SearchRequest", "backend/app/core_rag/retrieval.py"),
    "get_document_excerpt": ("SearchRequest", "backend/app/core_rag/retrieval.py"),
}

BACKEND_RESPONSES = {
    "AskResponse": {
        "answer",
        "citations",
        "used_chunks_count",
        "latency_ms",
        "mode",
        "debug_info",
    },
    "CitationItem": {
        "citation_id",
        "source_id",
        "source_part_id",
        "chunk_id",
        "file_name",
        "source_type",
        "heading",
        "locator",
        "snippet",
        "freshness",
    },
    "SearchResponse": {"results", "latency_ms", "mode", "debug_info"},
    "SearchResultItem": {
        "chunk_id",
        "source_id",
        "source_part_id",
        "file_name",
        "source_type",
        "heading",
        "locator",
        "snippet",
        "score",
    },
}


def _classes(path: Path) -> dict[str, ast.ClassDef]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}


def _class_fields(path: Path) -> dict[str, set[str]]:
    return {
        name: {
            item.target.id
            for item in node.body
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)
        }
        for name, node in _classes(path).items()
    }


def _field_details(path: Path, class_name: str) -> dict[str, dict[str, Any]]:
    node = _classes(path).get(class_name)
    if node is None:
        raise SystemExit(f"Missing backend model {class_name} in {path}")
    details: dict[str, dict[str, Any]] = {}
    for item in node.body:
        if not isinstance(item, ast.AnnAssign) or not isinstance(item.target, ast.Name):
            continue
        detail: dict[str, Any] = {"annotation": ast.unparse(item.annotation)}
        if item.value is None:
            detail["required"] = True
        elif isinstance(item.value, ast.Call) and isinstance(item.value.func, ast.Name):
            if item.value.func.id == "Field":
                for keyword in item.value.keywords:
                    if keyword.arg in {"default", "le", "ge"}:
                        detail[keyword.arg] = ast.literal_eval(keyword.value)
                    elif keyword.arg == "default_factory":
                        detail["default_factory"] = ast.unparse(keyword.value)
        else:
            detail["default"] = ast.literal_eval(item.value)
        details[item.target.id] = detail
    return details


def _string_collection_assignment(path: Path, name: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            return {str(item) for item in ast.literal_eval(node.value)}
    raise SystemExit(f"Unable to locate {name} in {path}")


def _literal_alias_values(path: Path, name: str) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            continue
        if isinstance(node.value, ast.Subscript) and isinstance(node.value.slice, ast.Tuple):
            return [str(ast.literal_eval(item)) for item in node.value.slice.elts]
    raise SystemExit(f"Unable to locate Literal alias {name} in {path}")


def _assert_backend_field_contract(
    tool_name: str, schema: dict[str, Any], backend: dict[str, dict[str, Any]]
) -> None:
    transformed = {
        "source_id": "filters",
        "source_part_id": "filters",
        "locator_filter": "filters",
        "metadata_filters": "filters",
        "max_chars": None,
    }
    for field, property_schema in schema.items():
        target = transformed.get(field, field)
        if target is None:
            continue
        if target not in backend:
            raise SystemExit(f"{tool_name}.{field} is not accepted by the STARTER request")
        if target == "filters" and field != "filters":
            continue
        detail = backend[target]
        if field == "question" and detail.get("required") is not True:
            raise SystemExit(f"{tool_name}.question must remain required by STARTER")
        if field != "question" and detail.get("required") is True:
            raise SystemExit(f"{tool_name}.{field} became required by STARTER")
        maximum = property_schema.get("maximum")
        if maximum is not None and detail.get("le") is not None and maximum > detail["le"]:
            raise SystemExit(f"{tool_name}.{field} exceeds STARTER maximum")
        expected_type = property_schema.get("type")
        annotation = detail.get("annotation", "")
        type_markers = {
            "string": ("str", "SearchMode"),
            "integer": ("int",),
            "boolean": ("bool",),
            "array": ("list",),
            "object": ("SearchFilters", "dict"),
        }
        if not any(marker in annotation for marker in type_markers[expected_type]):
            raise SystemExit(
                f"{tool_name}.{field} type {expected_type} is incompatible with {annotation}"
            )


def _assert_runtime_mapping(starter: Path, tools: dict[str, dict[str, Any]]) -> None:
    from rag_enterprise_mcp.schemas.backend import (
        AskGroundedInput,
        GetDocumentExcerptInput,
        SearchDocumentsInput,
    )
    from rag_enterprise_mcp.server import StdioJsonRpcServer

    mappings = {
        "ask_grounded": AskGroundedInput.from_input({"question": "Q"}).to_backend(),
        "search_documents": SearchDocumentsInput.from_input({"question": "Q"}).to_backend(),
        "get_document_excerpt": GetDocumentExcerptInput.from_input(
            {"question": "Q", "source_id": 7}
        ).to_search_backend(),
    }
    for tool_name, payload in mappings.items():
        model, relative_path = BACKEND_REQUESTS[tool_name]
        backend = _field_details(starter / relative_path, model)
        unsupported = set(payload) - set(backend)
        if unsupported:
            raise SystemExit(f"{tool_name} runtime payload drifted: {sorted(unsupported)}")
    for tool_name in ("ask_grounded", "search_documents"):
        properties = tools[tool_name]["inputSchema"]["properties"]
        for field, property_schema in properties.items():
            if "default" not in property_schema or field not in mappings[tool_name]:
                continue
            if mappings[tool_name][field] != property_schema["default"]:
                raise SystemExit(f"{tool_name}.{field} runtime/schema default drifted")
    excerpt = GetDocumentExcerptInput.from_input({"question": "Q", "source_id": 7})
    excerpt_schema = tools["get_document_excerpt"]["inputSchema"]["properties"]
    if excerpt.max_chars != excerpt_schema["max_chars"]["default"]:
        raise SystemExit("get_document_excerpt.max_chars runtime/schema default drifted")
    if excerpt.mode != excerpt_schema["mode"]["default"]:
        raise SystemExit("get_document_excerpt.mode runtime/schema default drifted")
    error = StdioJsonRpcServer._tool_error(1, "invalid", code=-32602)
    if set(error) != {"jsonrpc", "id", "error"} or set(error["error"]) != {"code", "message"}:
        raise SystemExit("MCP JSON-RPC error envelope drifted")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--mcp", type=Path, required=True)
    parser.add_argument("--starter", type=Path, required=True)
    args = parser.parse_args()

    sys.path.insert(0, str(args.mcp / "src"))
    from rag_enterprise_mcp.tools import TOOLS

    tools = {tool["name"]: tool for tool in TOOLS}
    if set(tools) != set(EXPECTED_SCHEMAS):
        raise SystemExit(f"MCP tool names drifted: {sorted(tools)}")
    required_tools = _string_collection_assignment(
        args.app / "src/rag_enterprise_langgraph/demo_proof.py", "REQUIRED_MCP_TOOLS"
    )
    if required_tools != set(EXPECTED_SCHEMAS):
        raise SystemExit(f"APP required tool names drifted: {sorted(required_tools)}")

    for name, expected_properties in EXPECTED_SCHEMAS.items():
        schema = tools[name]["inputSchema"]
        if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
            raise SystemExit(f"{name} must remain a closed object schema")
        if schema.get("required") != ["question"]:
            raise SystemExit(f"{name} must require question")
        if schema.get("properties") != expected_properties:
            raise SystemExit(f"{name} type/default/range/enum schema drifted")
        model_name, relative_path = BACKEND_REQUESTS[name]
        backend = _field_details(args.starter / relative_path, model_name)
        _assert_backend_field_contract(name, expected_properties, backend)

    model_fields = {}
    model_fields.update(_class_fields(args.starter / "backend/app/core_rag/answering.py"))
    model_fields.update(_class_fields(args.starter / "backend/app/core_rag/retrieval.py"))
    for model, expected_fields in BACKEND_RESPONSES.items():
        if not expected_fields <= model_fields.get(model, set()):
            raise SystemExit(f"STARTER {model} response shape drifted")
    expected_filter_fields = {
        "source_type",
        "source_id",
        "source_part_id",
        "locator_filter",
        "metadata_filters",
    }
    if not expected_filter_fields <= model_fields.get("SearchFilters", set()):
        raise SystemExit("STARTER SearchFilters shape drifted")
    retrieval_path = args.starter / "backend/app/core_rag/retrieval.py"
    if _literal_alias_values(retrieval_path, "SearchMode") != MODES:
        raise SystemExit("MCP and STARTER retrieval mode enums drifted")
    _assert_runtime_mapping(args.starter, tools)

    app_source = (args.app / "src/rag_enterprise_langgraph/orchestrator.py").read_text(
        encoding="utf-8"
    )
    for required_key in (
        'content.get("citations")',
        'content.get("results")',
        'content.get("matched")',
        'parsed.get("status_code")',
    ):
        if required_key not in app_source:
            raise SystemExit(f"APP response/error consumer drifted: {required_key}")

    print("Cross-repository APP/MCP/STARTER contracts are compatible.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
