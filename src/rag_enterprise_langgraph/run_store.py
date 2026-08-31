from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from rag_enterprise_langgraph.approval import APPROVED, PENDING_APPROVAL, REJECTED
from rag_enterprise_langgraph.audit import sanitize_for_audit


DEFAULT_RUN_RESULTS_DIR = "runs/run-results"

# Fields persisted per run so a past run can be re-rendered exactly like a fresh one.
STORED_FIELDS = (
    "run_id",
    "question",
    "answer",
    "grounding_status",
    "citations",
    "evidence",
    "source_evidence",
    "synthesized_answer",
    "verbatim_answer",
    "synthesis_verified",
    "citation_count",
    "evidence_count",
    "decision_trail",
    "execution_timeline",
    "validation_summary",
    "recovery_attempted",
    "recovery_successful",
    "latency_ms",
    "mode",
    "failure_reason",
    "error",
    "review_guidance",
    "review_note",
    "approval_status",
    "approval_id",
    "risk_reasons",
    "audit_event_count",
)


class RunStore:
    """Persists the sanitized full result of each orchestrated run, keyed by run_id.

    The stored record keeps the run's real answer; the release policy is applied
    at serve time by ``public_view`` using the live approval record.
    """

    def __init__(self, directory: str | Path = DEFAULT_RUN_RESULTS_DIR):
        self.directory = Path(directory)

    def save(self, result: dict[str, Any], *, real_answer: str | None = None) -> Path | None:
        run_id = result.get("run_id")
        if not run_id:
            return None
        record = {key: result.get(key) for key in STORED_FIELDS}
        if real_answer is not None:
            record["answer"] = real_answer
        record["created_at"] = datetime.now(timezone.utc).isoformat()
        record = sanitize_for_audit(record)
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{run_id}.json"
        path.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def get(self, run_id: str) -> dict[str, Any] | None:
        path = self.directory / f"{run_id}.json"
        if not path.exists() or path.parent != self.directory:
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    def list(self) -> list[dict[str, Any]]:
        if not self.directory.exists():
            return []
        records: list[dict[str, Any]] = []
        for path in self.directory.glob("*.json"):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            records.append(
                {
                    "run_id": record.get("run_id"),
                    "question": " ".join(str(record.get("question") or "").split())[:200],
                    "grounding_status": record.get("grounding_status"),
                    "approval_status": record.get("approval_status"),
                    "approval_id": record.get("approval_id"),
                    "citation_count": record.get("citation_count"),
                    "evidence_count": record.get("evidence_count"),
                    "recovery_attempted": record.get("recovery_attempted"),
                    "created_at": record.get("created_at"),
                }
            )
        records.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return records


def public_view(record: dict[str, Any], approval_record: dict[str, Any] | None = None) -> dict[str, Any]:
    """Apply the answer-release policy to a stored run result.

    Approved (or never gated) runs return the real answer; pending and rejected
    runs return it withheld. Citations, decision trail, and timeline are always
    visible — only the answer text is gated, matching the live-run behavior.
    """
    view = dict(record)
    status = (approval_record or {}).get("status") or record.get("approval_status") or "approval_not_required"
    view["approval_status"] = status

    def _withhold_source() -> None:
        # Any field carrying the retrieved snippet text reveals the answer
        # content, so all of them are withheld until the run is approved.
        view["source_evidence"] = []
        view["synthesized_answer"] = None
        view["verbatim_answer"] = None
        view["evidence"] = []
        view["citations"] = []
        view["rejected_evidence"] = []

    if status == PENDING_APPROVAL:
        view["answer"] = (
            f"Answer withheld pending human approval (approval_id={record.get('approval_id')}). "
            "A reviewer must approve or reject this run before the answer is released."
        )
        view["answer_released"] = False
        _withhold_source()
    elif status == REJECTED:
        reviewer = (approval_record or {}).get("reviewer") or "a reviewer"
        comment = (approval_record or {}).get("comment")
        view["answer"] = f"Answer not released: rejected by {reviewer}." + (f" Comment: {comment}" if comment else "")
        view["answer_released"] = False
        view["decided_by"] = (approval_record or {}).get("reviewer")
        view["decided_at"] = (approval_record or {}).get("decided_at")
        view["approval_comment"] = comment
        _withhold_source()
    elif status == APPROVED:
        view["answer_released"] = True
        view["approved_by"] = (approval_record or {}).get("reviewer")
        view["approved_at"] = (approval_record or {}).get("decided_at")
        view["approval_comment"] = (approval_record or {}).get("comment")
    else:
        view["answer_released"] = True
    return view


def build_runs_router(run_store: RunStore, approval_store=None) -> APIRouter:
    router = APIRouter(prefix="/runs", tags=["runs"])

    def _approval_for(record: dict[str, Any]) -> dict[str, Any] | None:
        approval_id = record.get("approval_id")
        if approval_store is None or not approval_id:
            return None
        return approval_store.get(approval_id)

    @router.get("")
    async def list_runs():
        runs = run_store.list()
        for item in runs:
            approval = _approval_for(item)
            if approval:
                item["approval_status"] = approval.get("status")
        return {"runs": runs}

    @router.get("/{run_id}")
    async def get_run(run_id: str):
        record = run_store.get(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail="run_id not found in run store")
        return public_view(record, _approval_for(record))

    return router
