import hashlib

from rag_enterprise_langgraph.graph import SYSTEM_PROMPT
from rag_enterprise_langgraph.prompt_registry import load_prompt, prompt_metadata
from rag_enterprise_langgraph.synthesis import SYNTHESIS_SYSTEM_PROMPT


def test_active_prompts_are_hash_verified_and_keep_legacy_constants():
    metadata = prompt_metadata()

    assert load_prompt("app_agent") == SYSTEM_PROMPT
    assert load_prompt("app_synthesis") == SYNTHESIS_SYSTEM_PROMPT
    assert set(metadata) == {"app_agent", "app_synthesis"}
    for prompt_id, prompt in (
        ("app_agent", SYSTEM_PROMPT),
        ("app_synthesis", SYNTHESIS_SYSTEM_PROMPT),
    ):
        assert metadata[prompt_id]["version"] == "1.0.0"
        assert metadata[prompt_id]["sha256"] == hashlib.sha256(prompt.encode("utf-8")).hexdigest()
