from __future__ import annotations

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model

from rag_enterprise_langgraph.config import Settings
from rag_enterprise_langgraph.prompt_registry import load_prompt

SYSTEM_PROMPT = load_prompt("app_agent")


def build_chat_model(settings: Settings):
    return init_chat_model(
        settings.model_name,
        model_provider=settings.model_provider,
        temperature=settings.model_temperature,
    )


def build_agent_graph(settings: Settings, tools, model=None):
    return create_agent(
        model=model or build_chat_model(settings),
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
        debug=settings.debug,
        name=settings.app_name,
    )
