from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from rag_enterprise_langgraph.audit import AuditLog, scrub_text


DEFAULT_APPROVALS_PATH = "runs/approvals.jsonl"

APPROVAL_NOT_REQUIRED = "approval_not_required"
PENDING_APPROVAL = "pending_approval"
APPROVED = "approved"
REJECTED = "rejected"

APPROVAL_MODES = ("off", "high-risk-only", "always")

HIGH_RISK_CATEGORIES: dict[str, tuple[str, ...]] = {
    "hr": (
        "hr",
        "human resources",
        "employee",
        "employees",
        "termination",
        "terminate",
        "hiring",
        "firing",
        "payroll",
        "salary",
        "salaries",
        "benefits",
        "disciplinary",
        "grievance",
    ),
    "legal": (
        "legal",
        "lawsuit",
        "litigation",
        "contract",
        "liability",
        "nda",
        "regulation",
        "regulatory",
        "gdpr",
    ),
    "finance": (
        "finance",
        "financial",
        "revenue",
        "budget",
        "invoice",
        "audit",
        "tax",
        "expense",
        "accounting",
    ),
    "medical": (
        "medical",
        "health",
        "diagnosis",
        "treatment",
        "medication",
        "clinical",
        "patient",
    ),
    "security": (
        "security",
        "vulnerability",
        "credential",
        "credentials",
        "breach",
        "incident",
        "vpn",
        "firewall",
        "access control",
    ),
    "compliance": (
        "compliance",
        "compliant",
        "policy",
        "policies",
        "code of conduct",
        "violation",
    ),
}


def _question_risk_categories(question: str) -> list[str]:
    lowered = f" {question.lower()} "
    matched: list[str] = []
    for category, keywords in HIGH_RISK_CATEGORIES.items():
        for keyword in keywords:
            if re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", lowered):
                matched.append(category)
                break
    return matched


def assess_risk(question: str, result: dict[str, Any] | None = None) -> list[str]:
    """Return the reasons this run is considered high-risk. Empty means low-risk."""
    reasons = [f"high_risk_category:{category}" for category in _question_risk_categories(question)]
    result = result or {}
    grounding_status = str(result.get("grounding_status") or "")
    if grounding_status in {"needs_review", "partial"}:
        reasons.append(f"grounding_status:{grounding_status}")
    validation_summary = result.get("validation_summary")
    if isinstance(validation_summary, dict) and validation_summary.get("review_recommended") is True:
        reasons.append("review_recommended")
    return reasons


def approval_required(*, mode: str, risk_reasons: list[str]) -> bool:
    if mode == "always":
        return True
    if mode == "high-risk-only":
        return bool(risk_reasons)
    return False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


PUBLIC_FIELDS = (
    "approval_id",
    "run_id",
    "status",
    "question",
    "evidence_status",
    "grounding_status",
    "risk_reasons",
    "requested_at",
    "decided_at",
    "reviewer",
    "comment",
)


def released_view(record: dict[str, Any]) -> dict[str, Any]:
    """User-facing view of an approval record.

    The answer (and its preview) is released only once approved; pending and
    rejected records stay withheld. Reviewer-facing surfaces use the raw
    records from the store instead.
    """
    view = {key: record.get(key) for key in PUBLIC_FIELDS}
    if record.get("status") == APPROVED:
        view["answer_preview"] = record.get("answer_preview")
        view["released_answer"] = record.get("full_answer")
    return view


class ApprovalStore:
    """Append-only JSONL approval records; the latest record per approval_id wins."""

    def __init__(self, path: str | Path = DEFAULT_APPROVALS_PATH):
        self.path = Path(path)

    def _append(self, record: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    def _records(self) -> dict[str, dict[str, Any]]:
        records: dict[str, dict[str, Any]] = {}
        if not self.path.exists():
            return records
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                approval_id = record.get("approval_id")
                if approval_id:
                    records[approval_id] = record
        return records

    def create(
        self,
        *,
        question: str,
        answer: str,
        run_id: str | None = None,
        evidence_status: str | None = None,
        grounding_status: str | None = None,
        risk_reasons: list[str] | None = None,
    ) -> dict[str, Any]:
        record = {
            "approval_id": uuid.uuid4().hex,
            "run_id": run_id,
            "status": PENDING_APPROVAL,
            "question": scrub_text(question)[:600],
            "answer_preview": scrub_text(" ".join(str(answer or "").split()))[:320],
            "full_answer": scrub_text(str(answer or ""))[:4000],
            "evidence_status": evidence_status,
            "grounding_status": grounding_status,
            "risk_reasons": list(risk_reasons or []),
            "requested_at": _now(),
            "decided_at": None,
            "reviewer": None,
            "comment": None,
        }
        self._append(record)
        return record

    def get(self, approval_id: str) -> dict[str, Any] | None:
        return self._records().get(approval_id)

    def all(self) -> list[dict[str, Any]]:
        return sorted(self._records().values(), key=lambda item: str(item.get("requested_at") or ""), reverse=True)

    def pending(self) -> list[dict[str, Any]]:
        return [record for record in self.all() if record.get("status") == PENDING_APPROVAL]

    def by_run_id(self, run_id: str) -> dict[str, Any] | None:
        return next((record for record in self.all() if record.get("run_id") == run_id), None)

    def _decide(self, approval_id: str, status: str, reviewer: str, comment: str | None) -> dict[str, Any]:
        record = self.get(approval_id)
        if record is None:
            raise KeyError(f"approval_id not found: {approval_id}")
        if record.get("status") != PENDING_APPROVAL:
            raise ValueError(f"approval {approval_id} is already {record.get('status')}")
        if not str(reviewer or "").strip():
            raise ValueError("reviewer name is required")
        updated = {
            **record,
            "status": status,
            "decided_at": _now(),
            "reviewer": scrub_text(reviewer.strip())[:120],
            "comment": scrub_text(str(comment or "").strip())[:600] or None,
        }
        self._append(updated)
        return updated

    def approve(self, approval_id: str, *, reviewer: str, comment: str | None = None) -> dict[str, Any]:
        return self._decide(approval_id, APPROVED, reviewer, comment)

    def reject(self, approval_id: str, *, reviewer: str, comment: str | None = None) -> dict[str, Any]:
        return self._decide(approval_id, REJECTED, reviewer, comment)


class ApprovalRequestBody(BaseModel):
    question: str
    answer: str
    run_id: str | None = None
    evidence_status: str | None = None
    grounding_status: str | None = None
    risk_reasons: list[str] = []


class ApprovalDecisionBody(BaseModel):
    reviewer: str
    comment: str | None = None


def _record_audit_decision(audit_log: AuditLog | None, record: dict[str, Any], event_type: str) -> None:
    if audit_log is None:
        return
    audit_log.append(
        event_type=event_type,
        run_id=record.get("run_id"),
        actor=f"reviewer:{record.get('reviewer')}",
        summary=f"Approval {record.get('approval_id')} {record.get('status')} by {record.get('reviewer')}",
        payload={
            "approval_id": record.get("approval_id"),
            "status": record.get("status"),
            "comment": record.get("comment"),
            "grounding_status": record.get("grounding_status"),
        },
    )


def build_approval_router(store: ApprovalStore, audit_log: AuditLog | None = None) -> APIRouter:
    router = APIRouter(prefix="/approval", tags=["approval"])

    @router.post("/request")
    async def request_approval(body: ApprovalRequestBody):
        record = store.create(
            question=body.question,
            answer=body.answer,
            run_id=body.run_id,
            evidence_status=body.evidence_status,
            grounding_status=body.grounding_status,
            risk_reasons=body.risk_reasons,
        )
        if audit_log is not None:
            audit_log.append(
                event_type="approval_requested",
                run_id=record.get("run_id"),
                actor="api",
                summary=f"Approval requested: {record['approval_id']}",
                payload={"approval_id": record["approval_id"], "risk_reasons": record["risk_reasons"]},
            )
        return record

    @router.get("")
    async def list_approvals(status: str | None = None):
        records = store.all()
        if status:
            records = [record for record in records if record.get("status") == status]
        return {"approvals": [released_view(record) for record in records]}

    @router.get("/pending")
    async def pending_approvals():
        return {"pending": store.pending()}

    @router.get("/{approval_id}")
    async def get_approval(approval_id: str):
        record = store.get(approval_id)
        if record is None:
            raise HTTPException(status_code=404, detail="approval_id not found")
        return record

    @router.post("/{approval_id}/approve")
    async def approve(approval_id: str, body: ApprovalDecisionBody):
        try:
            record = store.approve(approval_id, reviewer=body.reviewer, comment=body.comment)
        except KeyError:
            raise HTTPException(status_code=404, detail="approval_id not found")
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        _record_audit_decision(audit_log, record, "approval_approved")
        return record

    @router.post("/{approval_id}/reject")
    async def reject(approval_id: str, body: ApprovalDecisionBody):
        try:
            record = store.reject(approval_id, reviewer=body.reviewer, comment=body.comment)
        except KeyError:
            raise HTTPException(status_code=404, detail="approval_id not found")
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        _record_audit_decision(audit_log, record, "approval_rejected")
        return record

    return router
