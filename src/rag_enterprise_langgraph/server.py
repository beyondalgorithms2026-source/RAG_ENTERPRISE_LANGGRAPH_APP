from __future__ import annotations

import asyncio

import uvicorn
from fastapi import FastAPI, Query
from pydantic import BaseModel

from rag_enterprise_langgraph.agent import RagEnterpriseAgent
from rag_enterprise_langgraph.config import Settings
from rag_enterprise_langgraph.demo_proof import build_demo_proof, resolve_demo_questions
from rag_enterprise_langgraph.orchestrator import EnterpriseRagOrchestrator


class AskRequest(BaseModel):
    question: str


class AskOrchestratedRequest(BaseModel):
    question: str
    max_recovery_steps: int = 3


def create_app(settings: Settings | None = None) -> FastAPI:
    runtime_settings = settings or Settings()
    agent = RagEnterpriseAgent(runtime_settings)
    orchestrator = EnterpriseRagOrchestrator(runtime_settings)
    app = FastAPI(title=runtime_settings.app_name)

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok"}

    @app.post("/ask")
    async def ask(request: AskRequest):
        result = await agent.run(request.question)
        return result.to_dict()

    @app.get("/demo-proof")
    async def demo_proof(
        question: list[str] | None = Query(default=None),
        include_debug: bool = False,
        max_recovery_steps: int = 3,
    ):
        questions = resolve_demo_questions(questions=question)
        return await build_demo_proof(
            orchestrator=orchestrator,
            questions=questions,
            include_debug=include_debug,
            max_recovery_steps=max_recovery_steps,
        )

    @app.post("/ask-orchestrated")
    async def ask_orchestrated(request: AskOrchestratedRequest):
        result = await orchestrator.run(request.question, max_recovery_steps=request.max_recovery_steps)
        return result.to_dict()

    return app


def main() -> int:
    settings = Settings()
    app = create_app(settings)
    config = uvicorn.Config(app=app, host=settings.api_host, port=settings.api_port)
    server = uvicorn.Server(config)
    return 0 if asyncio.run(server.serve()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
