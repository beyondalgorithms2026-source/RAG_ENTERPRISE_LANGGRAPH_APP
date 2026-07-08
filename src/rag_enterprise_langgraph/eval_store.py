from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from rag_enterprise_langgraph.config import Settings


DEFAULT_EVAL_RUNS_DIR = "runs/eval-runs"

GROUNDED_STATUSES = {"verified", "grounded", "recovered"}


def estimated_cost_per_query(settings: Settings) -> dict[str, Any]:
    total_tokens = max(0, int(settings.default_estimated_tokens_per_query))
    input_tokens = int(total_tokens * 0.8)
    output_tokens = total_tokens - input_tokens
    cost = (
        input_tokens / 1_000_000 * settings.input_token_cost_per_1m
        + output_tokens / 1_000_000 * settings.output_token_cost_per_1m
    )
    return {
        "estimated_cost_per_query": round(cost, 6),
        "cost_basis": "estimated",
        "cost_model": {
            "input_token_cost_per_1m": settings.input_token_cost_per_1m,
            "output_token_cost_per_1m": settings.output_token_cost_per_1m,
            "default_estimated_tokens_per_query": settings.default_estimated_tokens_per_query,
            "assumed_input_tokens": input_tokens,
            "assumed_output_tokens": output_tokens,
        },
    }


def compute_metrics(report: dict[str, Any], *, settings: Settings | None = None) -> dict[str, Any]:
    runtime_settings = settings or Settings()
    rows = report.get("rows") or []
    total = int(report.get("total") or len(rows))
    passed = int(report.get("passed") or 0)
    grounded_rows = sum(1 for row in rows if str(row.get("grounding_status") or "") in GROUNDED_STATUSES)
    latencies = [row.get("latency_ms") for row in rows if isinstance(row.get("latency_ms"), (int, float))]
    return {
        "total": total,
        "passed": passed,
        "failed": int(report.get("failed") or 0),
        "manual_review": int(report.get("manual_review") or 0),
        "accuracy": round(passed / total, 4) if total else 0.0,
        "grounding_rate": round(grounded_rows / total, 4) if total else 0.0,
        "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else None,
        **estimated_cost_per_query(runtime_settings),
    }


def build_eval_run_summary(
    report: dict[str, Any],
    *,
    settings: Settings | None = None,
    eval_run_id: str | None = None,
) -> dict[str, Any]:
    run_id = eval_run_id or f"eval-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    slim_rows = [
        {
            "question": " ".join(str(row.get("question") or "").split())[:200],
            "eval_status": row.get("eval_status"),
            "grounding_status": row.get("grounding_status"),
            "latency_ms": row.get("latency_ms"),
            "tools_used": row.get("tools_used") or [],
            "failure_reason": row.get("failure_reason"),
        }
        for row in report.get("rows") or []
    ]
    return {
        "eval_run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_xlsx": Path(str(report.get("xlsx_path") or "")).name or None,
        "status": report.get("status"),
        **compute_metrics(report, settings=settings),
        "rows": slim_rows,
    }


class EvalStore:
    def __init__(self, directory: str | Path = DEFAULT_EVAL_RUNS_DIR):
        self.directory = Path(directory)

    def save(self, summary: dict[str, Any]) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{summary['eval_run_id']}.json"
        path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def get(self, eval_run_id: str) -> dict[str, Any] | None:
        path = self.directory / f"{eval_run_id}.json"
        if not path.exists() or path.parent != self.directory:
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    def list(self) -> list[dict[str, Any]]:
        if not self.directory.exists():
            return []
        summaries: list[dict[str, Any]] = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                summary = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            summaries.append({key: value for key, value in summary.items() if key != "rows"})
        summaries.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return summaries

    def latest(self) -> dict[str, Any] | None:
        listing = self.list()
        if not listing:
            return None
        return self.get(str(listing[0].get("eval_run_id")))


class EvalRunBody(BaseModel):
    xlsx_path: str
    max_recovery_steps: int = 3
    rules_path: str | None = None
    journal_path: str | None = None


def build_eval_router(store: EvalStore, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/eval", tags=["eval"])

    @router.post("/run")
    async def run_eval_endpoint(body: EvalRunBody):
        from rag_enterprise_langgraph.eval_runner import run_eval

        project_root = Path.cwd().resolve()
        xlsx = Path(body.xlsx_path).resolve()
        if project_root != xlsx and project_root not in xlsx.parents:
            raise HTTPException(status_code=400, detail="xlsx_path must be inside the project directory")
        if not xlsx.exists():
            raise HTTPException(status_code=404, detail="xlsx file not found")
        report = await run_eval(
            xlsx_path=xlsx,
            rules_path=body.rules_path,
            journal_path=body.journal_path,
            max_recovery_steps=body.max_recovery_steps,
        )
        summary = build_eval_run_summary(report, settings=settings)
        store.save(summary)
        return summary

    @router.get("/runs")
    async def list_eval_runs():
        return {"eval_runs": store.list()}

    @router.get("/latest")
    async def latest_eval_run():
        latest = store.latest()
        if latest is None:
            return {"eval_run": None, "message": "No saved eval runs yet. Run an eval with --save-eval-run or POST /eval/run."}
        return {"eval_run": latest}

    @router.get("/runs/{eval_run_id}")
    async def get_eval_run(eval_run_id: str):
        summary = store.get(eval_run_id)
        if summary is None:
            raise HTTPException(status_code=404, detail="eval_run_id not found")
        return summary

    return router
