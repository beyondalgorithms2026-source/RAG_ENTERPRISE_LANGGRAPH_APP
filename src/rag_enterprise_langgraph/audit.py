from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from rag_enterprise_langgraph.journal import sanitize_for_journal


DEFAULT_AUDIT_LOG_PATH = "runs/audit-log.jsonl"

EVENT_TYPES = (
    "run_started",
    "question_classified",
    "tool_call_started",
    "tool_call_completed",
    "tool_call_failed",
    "answer_reviewed",
    "evidence_validated",
    "recovery_planned",
    "recovery_attempted",
    "approval_requested",
    "approval_approved",
    "approval_rejected",
    "run_completed",
)

_BEARER_PATTERN = re.compile(r"(?i)\bbearer\b[\s=:]+\S+")
_SECRET_VALUE_PATTERN = re.compile(
    r"(?i)\b(password|passwd|secret|token|api[_-]?key|authorization|cookie)\b\s*[=:]\s*\S+"
)


def scrub_text(value: str) -> str:
    cleaned = _BEARER_PATTERN.sub("bearer=[redacted]", value)
    cleaned = _SECRET_VALUE_PATTERN.sub(lambda match: f"{match.group(1)}=[redacted]", cleaned)
    cleaned = re.sub(r'File "[^"]+"', 'File "[path-redacted]"', cleaned)
    cleaned = re.sub(r"Traceback \(most recent call last\)[\s\S]*", "[traceback-redacted]", cleaned)
    return re.sub(r"/Users/[^\s\"']+", "[path-redacted]", cleaned)


def sanitize_for_audit(value: Any) -> Any:
    sanitized = sanitize_for_journal(value)

    def scrub(item: Any) -> Any:
        if isinstance(item, dict):
            return {key: scrub(inner) for key, inner in item.items()}
        if isinstance(item, list):
            return [scrub(inner) for inner in item]
        if isinstance(item, str):
            return scrub_text(item)
        return item

    return scrub(sanitized)


def _event_hash(body: dict[str, Any]) -> str:
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class AuditLog:
    """Append-only, hash-chained, sanitized JSONL audit log."""

    def __init__(self, path: str | Path = DEFAULT_AUDIT_LOG_PATH):
        self.path = Path(path)
        self._tail_hash = self._read_tail_hash()

    def _read_tail_hash(self) -> str | None:
        if not self.path.exists():
            return None
        tail: dict[str, Any] | None = None
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    tail = json.loads(line)
                except json.JSONDecodeError:
                    continue
        return tail.get("event_hash") if isinstance(tail, dict) else None

    def append(
        self,
        *,
        event_type: str,
        run_id: str | None,
        actor: str,
        summary: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body = {
            "event_id": uuid.uuid4().hex,
            "run_id": run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "actor": scrub_text(str(actor))[:120],
            "summary": scrub_text(str(summary))[:400],
            "payload": sanitize_for_audit(payload or {}),
            "previous_hash": self._tail_hash,
        }
        body["event_hash"] = _event_hash({key: value for key, value in body.items() if key != "event_hash"})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(body, sort_keys=True) + "\n")
        self._tail_hash = body["event_hash"]
        return body

    def events(self, *, run_id: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        events: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if run_id is not None and event.get("run_id") != run_id:
                    continue
                events.append(event)
        if limit is not None and limit >= 0:
            events = events[-limit:]
        return events

    def runs(self) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        for event in self.events():
            event_run_id = str(event.get("run_id") or "unknown")
            if event_run_id not in grouped:
                grouped[event_run_id] = {
                    "run_id": event_run_id,
                    "started_at": event.get("timestamp"),
                    "ended_at": event.get("timestamp"),
                    "event_count": 0,
                    "question_preview": None,
                    "final_status": None,
                    "approval_status": None,
                    "event_types": [],
                }
                order.append(event_run_id)
            summary = grouped[event_run_id]
            summary["ended_at"] = event.get("timestamp")
            summary["event_count"] += 1
            event_type = str(event.get("event_type") or "")
            if event_type not in summary["event_types"]:
                summary["event_types"].append(event_type)
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            if event_type == "run_started" and payload.get("question_preview"):
                summary["question_preview"] = payload.get("question_preview")
            if event_type == "run_completed":
                summary["final_status"] = payload.get("grounding_status")
                summary["approval_status"] = payload.get("approval_status")
            if event_type == "approval_approved":
                summary["approval_status"] = "approved"
            if event_type == "approval_rejected":
                summary["approval_status"] = "rejected"
        return [grouped[run_id] for run_id in reversed(order)]

    def verify_chain(self) -> dict[str, Any]:
        previous_hash: str | None = None
        checked = 0
        for index, event in enumerate(self.events()):
            expected = _event_hash({key: value for key, value in event.items() if key != "event_hash"})
            if event.get("event_hash") != expected or event.get("previous_hash") != previous_hash:
                return {"valid": False, "checked": checked, "first_invalid_index": index}
            previous_hash = event.get("event_hash")
            checked += 1
        return {"valid": True, "checked": checked, "first_invalid_index": None}

    def export_run(self, run_id: str) -> dict[str, Any]:
        events = self.events(run_id=run_id)
        return {
            "run_id": run_id,
            "audit_log_path": self.path.name,
            "event_count": len(events),
            "chain_verification": self.verify_chain(),
            "events": events,
        }


def build_audit_router(audit_log: AuditLog, approval_store=None) -> APIRouter:
    router = APIRouter(prefix="/audit", tags=["audit"])

    @router.get("/runs")
    async def list_runs():
        return {"runs": audit_log.runs()}

    @router.get("/runs/{run_id}")
    async def get_run(run_id: str):
        events = audit_log.events(run_id=run_id)
        if not events:
            raise HTTPException(status_code=404, detail="run_id not found in audit log")
        payload = {
            "run_id": run_id,
            "event_count": len(events),
            "run_summary": next((run for run in audit_log.runs() if run["run_id"] == run_id), None),
            "events": events,
        }
        if approval_store is not None:
            record = approval_store.by_run_id(run_id)
            if record is not None:
                from rag_enterprise_langgraph.approval import released_view

                payload["approval"] = released_view(record)
        return payload

    @router.get("/events")
    async def list_events(limit: int = 200):
        return {"events": audit_log.events(limit=limit)}

    @router.get("/export/{run_id}")
    async def export_run(run_id: str):
        export = audit_log.export_run(run_id)
        if not export["events"]:
            raise HTTPException(status_code=404, detail="run_id not found in audit log")
        return export

    return router
