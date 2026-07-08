from __future__ import annotations

import asyncio
import json

from rag_enterprise_langgraph.audit import AuditLog, sanitize_for_audit, scrub_text
from rag_enterprise_langgraph.orchestrator import EnterpriseRagOrchestrator


def test_audit_event_has_required_fields_and_null_first_previous_hash(tmp_path):
    audit = AuditLog(tmp_path / "audit.jsonl")
    event = audit.append(
        event_type="run_started",
        run_id="run-1",
        actor="orchestrator",
        summary="Run started",
        payload={"question_preview": "What is X?"},
    )
    for key in ("event_id", "run_id", "timestamp", "event_type", "actor", "summary", "payload", "previous_hash", "event_hash"):
        assert key in event
    assert event["previous_hash"] is None
    assert event["event_hash"]


def test_audit_hash_chain_survives_process_restart(tmp_path):
    path = tmp_path / "audit.jsonl"
    first_log = AuditLog(path)
    first = first_log.append(event_type="run_started", run_id="run-1", actor="orchestrator", summary="start")

    # Simulate a restart by creating a fresh instance over the same file.
    second_log = AuditLog(path)
    second = second_log.append(event_type="run_completed", run_id="run-1", actor="orchestrator", summary="done")

    assert second["previous_hash"] == first["event_hash"]
    verification = second_log.verify_chain()
    assert verification["valid"] is True
    assert verification["checked"] == 2


def test_audit_chain_detects_tampering(tmp_path):
    path = tmp_path / "audit.jsonl"
    audit = AuditLog(path)
    audit.append(event_type="run_started", run_id="run-1", actor="orchestrator", summary="start")
    audit.append(event_type="run_completed", run_id="run-1", actor="orchestrator", summary="done")

    lines = path.read_text(encoding="utf-8").splitlines()
    tampered = json.loads(lines[0])
    tampered["summary"] = "tampered summary"
    lines[0] = json.dumps(tampered, sort_keys=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    verification = AuditLog(path).verify_chain()
    assert verification["valid"] is False
    assert verification["first_invalid_index"] == 0


def test_audit_sanitization_removes_secrets_paths_and_tracebacks(tmp_path):
    audit = AuditLog(tmp_path / "audit.jsonl")
    event = audit.append(
        event_type="tool_call_failed",
        run_id="run-1",
        actor="orchestrator",
        summary='failed with Authorization: Bearer abc123secret at /Users/Work/private/file.py',
        payload={
            "password": "hunter2",
            "api_key": "sk-live-123",
            "cookie": "session=abc",
            "detail": "token=xyz789 raised Traceback (most recent call last): boom",
            "nested": {"authorization": "Bearer zzz", "safe": "keep-me"},
        },
    )
    text = json.dumps(event)
    assert "hunter2" not in text
    assert "sk-live-123" not in text
    assert "abc123secret" not in text
    assert "xyz789" not in text
    assert "session=abc" not in text
    assert "/Users/Work/private" not in text
    assert "most recent call last" not in text
    assert event["payload"]["nested"]["safe"] == "keep-me"


def test_scrub_text_and_sanitize_for_audit_helpers():
    assert "secret-value" not in scrub_text("bearer secret-value")
    assert "[path-redacted]" in scrub_text("/Users/Work/some/file.txt")
    sanitized = sanitize_for_audit({"prompt": "raw prompt text", "answer": "ok"})
    assert "prompt" not in sanitized
    assert sanitized["answer"] == "ok"


def test_audit_runs_grouping_and_export(tmp_path):
    audit = AuditLog(tmp_path / "audit.jsonl")
    audit.append(event_type="run_started", run_id="run-a", actor="orchestrator", summary="start", payload={"question_preview": "Q-A?"})
    audit.append(event_type="run_completed", run_id="run-a", actor="orchestrator", summary="done", payload={"grounding_status": "verified", "approval_status": "approval_not_required"})
    audit.append(event_type="run_started", run_id="run-b", actor="orchestrator", summary="start", payload={"question_preview": "Q-B?"})

    runs = audit.runs()
    assert [run["run_id"] for run in runs] == ["run-b", "run-a"]
    run_a = next(run for run in runs if run["run_id"] == "run-a")
    assert run_a["event_count"] == 2
    assert run_a["question_preview"] == "Q-A?"
    assert run_a["final_status"] == "verified"

    export = audit.export_run("run-a")
    assert export["event_count"] == 2
    assert export["chain_verification"]["valid"] is True


def test_orchestrator_emits_run_id_and_audit_events(tmp_path):
    audit = AuditLog(tmp_path / "audit.jsonl")
    orchestrator = EnterpriseRagOrchestrator(quiet_mcp=False, audit_log=audit)

    async def stub_call_tool(name, arguments):  # noqa: ANN001, ARG001
        content = {"answer": "Not found in provided sources.", "citations": []} if name == "ask_grounded" else {"results": []}
        return content, {"tool_name": name, "tool_call_id": None, "content": content}

    orchestrator._call_tool = stub_call_tool  # type: ignore[method-assign]

    result = asyncio.run(orchestrator.run("What color is the sky in the story?"))

    assert result.run_id
    assert result.audit_event_count > 0
    assert result.audit_log_path == str(audit.path)
    events = audit.events(run_id=result.run_id)
    assert len(events) == result.audit_event_count
    event_types = [event["event_type"] for event in events]
    assert event_types[0] == "run_started"
    assert "question_classified" in event_types
    assert "tool_call_started" in event_types
    assert "tool_call_completed" in event_types
    assert event_types[-1] == "run_completed"
    assert audit.verify_chain()["valid"] is True


def test_orchestrator_run_without_audit_still_has_run_id():
    orchestrator = EnterpriseRagOrchestrator(quiet_mcp=False)

    async def fail_tool_call(name, arguments):  # noqa: ANN001, ARG001
        raise OSError("backend unavailable")

    orchestrator._call_tool = fail_tool_call  # type: ignore[method-assign]

    result = asyncio.run(orchestrator.run("What did the source say?"))

    assert result.run_id
    assert result.audit_event_count == 0
    assert result.audit_log_path is None
    assert result.to_dict()["run_id"] == result.run_id
