from __future__ import annotations

import asyncio

import uvicorn
from fastapi import FastAPI, Query
from pydantic import BaseModel

from rag_enterprise_langgraph.agent import RagEnterpriseAgent
from rag_enterprise_langgraph.approval import ApprovalStore, build_approval_router
from rag_enterprise_langgraph.audit import AuditLog, build_audit_router
from rag_enterprise_langgraph.config import Settings
from rag_enterprise_langgraph.demo_proof import build_demo_proof, resolve_demo_questions
from rag_enterprise_langgraph.eval_store import EvalStore, build_eval_router
from rag_enterprise_langgraph.orchestrator import EnterpriseRagOrchestrator, run_before_after
from rag_enterprise_langgraph.red_team import build_red_team_router
from rag_enterprise_langgraph.ui import build_ui_router


class AskRequest(BaseModel):
    question: str


class AskOrchestratedRequest(BaseModel):
    question: str
    max_recovery_steps: int = 3
    max_attempts: int | None = None
    validation_mode: str = "balanced"
    expected_answer: str | None = None
    rules_path: str | None = None
    journal_path: str | None = None
    require_approval: bool = False
    approval_mode: str = "off"


class BeforeAfterRequest(BaseModel):
    question: str
    max_recovery_steps: int = 3
    validation_mode: str = "balanced"
    require_approval: bool = False
    approval_mode: str = "off"


def create_app(settings: Settings | None = None) -> FastAPI:
    runtime_settings = settings or Settings()
    agent = RagEnterpriseAgent(runtime_settings)
    audit_log = AuditLog(runtime_settings.audit_log_path)
    approval_store = ApprovalStore(runtime_settings.approvals_path)
    eval_store = EvalStore(runtime_settings.eval_runs_dir)
    orchestrator = EnterpriseRagOrchestrator(
        runtime_settings, audit_log=audit_log, approval_store=approval_store
    )
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
        max_attempts: int | None = None,
        validation_mode: str = "balanced",
        show_decision_trail: bool = True,
        hide_review_note: bool = False,
        rules_path: str | None = None,
        journal_path: str | None = None,
    ):
        questions = resolve_demo_questions(questions=question)
        runtime_orchestrator = (
            EnterpriseRagOrchestrator(
                runtime_settings,
                rules_path=rules_path,
                journal_path=journal_path,
                audit_log=audit_log,
                approval_store=approval_store,
            )
            if rules_path or journal_path
            else orchestrator
        )
        return await build_demo_proof(
            orchestrator=runtime_orchestrator,
            questions=questions,
            include_debug=include_debug,
            max_recovery_steps=max_recovery_steps,
            max_attempts=max_attempts,
            validation_mode=validation_mode,
            show_decision_trail=show_decision_trail,
            show_review_note=not hide_review_note,
            rules_path=rules_path,
            journal_path=journal_path,
        )

    @app.post("/ask-orchestrated")
    async def ask_orchestrated(request: AskOrchestratedRequest):
        runtime_orchestrator = (
            EnterpriseRagOrchestrator(
                runtime_settings,
                rules_path=request.rules_path,
                journal_path=request.journal_path,
                audit_log=audit_log,
                approval_store=approval_store,
            )
            if request.rules_path or request.journal_path
            else orchestrator
        )
        result = await runtime_orchestrator.run(
            request.question,
            max_recovery_steps=request.max_recovery_steps,
            max_attempts=request.max_attempts,
            validation_mode=request.validation_mode,
            expected_answer=request.expected_answer,
            journal_path=request.journal_path,
            require_approval=request.require_approval,
            approval_mode=request.approval_mode,
        )
        return result.to_dict()

    @app.post("/demo/before-after")
    async def demo_before_after(request: BeforeAfterRequest):
        return await run_before_after(
            orchestrator,
            request.question,
            max_recovery_steps=request.max_recovery_steps,
            validation_mode=request.validation_mode,
            require_approval=request.require_approval,
            approval_mode=request.approval_mode,
        )

    app.include_router(build_approval_router(approval_store, audit_log))
    app.include_router(build_audit_router(audit_log))
    app.include_router(build_eval_router(eval_store, runtime_settings))
    app.include_router(
        build_red_team_router(
            findings_path=runtime_settings.red_team_findings_path,
            latest_path=runtime_settings.red_team_latest_path,
        )
    )
    app.include_router(build_ui_router())

    return app


def main() -> int:
    settings = Settings()
    app = create_app(settings)
    config = uvicorn.Config(app=app, host=settings.api_host, port=settings.api_port)
    server = uvicorn.Server(config)
    return 0 if asyncio.run(server.serve()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
