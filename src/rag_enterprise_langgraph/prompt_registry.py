from __future__ import annotations

import hashlib
import json
from importlib.resources import files
from typing import Any

_ROOT = files("rag_enterprise_langgraph").joinpath("prompt_assets")


def _registry() -> dict[str, Any]:
    payload = json.loads(_ROOT.joinpath("registry.json").read_text(encoding="utf-8"))
    if payload.get("schema_version") != "1.0":
        raise RuntimeError("Unsupported APP prompt registry schema.")
    return payload


def load_prompt(prompt_id: str) -> str:
    entry = _registry().get("prompts", {}).get(prompt_id)
    if not isinstance(entry, dict):
        raise RuntimeError(f"Unknown APP prompt id: {prompt_id}")
    content = _ROOT.joinpath(str(entry["file"])).read_text(encoding="utf-8").rstrip("\n")
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    if digest != entry.get("sha256"):
        raise RuntimeError(f"APP prompt hash mismatch: {prompt_id}")
    return content


def prompt_metadata() -> dict[str, dict[str, str]]:
    registry = _registry()
    output: dict[str, dict[str, str]] = {}
    for prompt_id, entry in registry.get("prompts", {}).items():
        load_prompt(prompt_id)
        output[prompt_id] = {
            "version": str(entry["version"]),
            "sha256": str(entry["sha256"]),
        }
    return output
