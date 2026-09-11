from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import subprocess
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from rag_enterprise_langgraph.demo_proof import redact_for_sharing
from rag_enterprise_langgraph.evidence import evaluate_expected_answer, load_rules
from rag_enterprise_langgraph.orchestrator import EnterpriseRagOrchestrator
from rag_enterprise_langgraph.prompt_registry import prompt_metadata

NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


@dataclass(frozen=True)
class EvalCase:
    question: str
    expected_answer: str
    file_name: str | None = None
    post_url: str | None = None
    # True for questions the corpus deliberately cannot answer. These pass only
    # if the system declines to answer - inventing a plausible answer is the
    # failure they exist to catch.
    expect_refusal: bool = False
    case_id: str | None = None


class EvalSetError(ValueError):
    """The checked-in evaluation set is malformed or internally contradictory."""


def _git_commit(path: Path) -> str | None:
    try:
        return subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _external_prompt_metadata(repo: Path) -> dict[str, dict[str, str]]:
    root = repo / "backend/app/llm/prompt_assets"
    registry = json.loads((root / "registry.json").read_text(encoding="utf-8"))
    output: dict[str, dict[str, str]] = {}
    for prompt_id, entry in registry.get("prompts", {}).items():
        content = (root / entry["file"]).read_text(encoding="utf-8").rstrip("\n")
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if digest != entry.get("sha256"):
            raise EvalSetError(f"STARTER prompt hash mismatch: {prompt_id}")
        output[prompt_id] = {"version": entry["version"], "sha256": digest}
    return output


def build_eval_configuration() -> dict[str, Any]:
    repo_paths = {
        name: Path(value)
        for name, value in {
            "app": os.environ.get("RAG_EVAL_APP_REPO"),
            "mcp": os.environ.get("RAG_EVAL_MCP_REPO"),
            "starter": os.environ.get("RAG_EVAL_STARTER_REPO"),
        }.items()
        if value
    }
    configuration: dict[str, Any] = {
        "repositories": {name: _git_commit(path) for name, path in repo_paths.items()},
        "llm": {
            "provider": os.environ.get("LLM_PROVIDER"),
            "model": os.environ.get("LLM_MODEL"),
        },
        "embedding": {
            "provider": os.environ.get("EMBEDDING_PROVIDER"),
            "model": os.environ.get("EMBEDDING_MODEL"),
            "dimensions": os.environ.get("EMBEDDING_DIMENSIONS"),
        },
        "retrieval": {
            "mode": os.environ.get("RETRIEVAL_MODE"),
            "rerank_enabled": os.environ.get("RERANK_ENABLED"),
        },
    }
    starter = repo_paths.get("starter")
    if starter:
        configuration["starter_prompts"] = _external_prompt_metadata(starter)
    upload_dir = os.environ.get("UPLOAD_DIR")
    manifest = Path(upload_dir, "corpus-manifest.json") if upload_dir else None
    if manifest and manifest.exists():
        configuration["corpus_manifest_sha256"] = hashlib.sha256(manifest.read_bytes()).hexdigest()
    return configuration


def _column_index(cell_ref: str) -> int:
    letters = re.sub(r"[^A-Z]", "", cell_ref.upper())
    index = 0
    for letter in letters:
        index = (index * 26) + (ord(letter) - ord("A") + 1)
    return index - 1


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    strings: list[str] = []
    for item in root.findall("main:si", NS):
        parts = [node.text or "" for node in item.findall(".//main:t", NS)]
        strings.append("".join(parts))
    return strings


def _cell_value(cell: ET.Element, shared_strings: Sequence[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//main:t", NS))
    value = cell.find("main:v", NS)
    if value is None or value.text is None:
        return ""
    if cell_type == "s":
        index = int(value.text)
        return shared_strings[index] if 0 <= index < len(shared_strings) else ""
    return value.text


def read_eval_json(path: str | Path) -> list[EvalCase]:
    """Read an eval set from JSON.

    Preferred over .xlsx: the question set is then plain text in the repository,
    so a reader can see exactly what was asked and what was expected.
    """
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != "1.0":
        raise EvalSetError("eval set schema_version must be '1.0'")
    questions = payload.get("questions")
    if not isinstance(questions, list) or not questions:
        raise EvalSetError("eval set questions must be a non-empty list")
    if payload.get("eval_set") == "northwind-public-demo" and len(questions) != 25:
        raise EvalSetError("northwind-public-demo must contain exactly 25 questions")
    cases: list[EvalCase] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(questions, start=1):
        if not isinstance(item, dict):
            raise EvalSetError(f"question {index} must be an object")
        case_id = str(item.get("case_id") or "").strip()
        if not case_id:
            raise EvalSetError(f"question {index} is missing case_id")
        if case_id in seen_ids:
            raise EvalSetError(f"duplicate case_id: {case_id}")
        seen_ids.add(case_id)
        question = str(item.get("question") or "").strip()
        if not question:
            raise EvalSetError(f"{case_id} has an empty question")
        if not isinstance(item.get("expect_refusal"), bool):
            raise EvalSetError(f"{case_id} must declare boolean expect_refusal")
        expects_refusal = item["expect_refusal"]
        expected_document = item.get("expected_document")
        expected_fact = item.get("expected_fact")
        if expects_refusal:
            if expected_document is not None or expected_fact is not None:
                raise EvalSetError(f"{case_id} refusal must have null expectations")
        elif not str(expected_document or "").strip() or not str(expected_fact or "").strip():
            raise EvalSetError(f"{case_id} answerable case needs document and fact")
        cases.append(
            EvalCase(
                question=question,
                expected_answer=str(expected_fact or "").strip(),
                file_name=str(expected_document).strip()
                if expected_document is not None
                else None,
                expect_refusal=expects_refusal,
                case_id=case_id,
            )
        )
    if payload.get("eval_set") == "northwind-public-demo":
        refusal_count = sum(case.expect_refusal for case in cases)
        if refusal_count != 5:
            raise EvalSetError(
                "northwind-public-demo must contain 20 answerable and 5 refusal cases"
            )
    return cases


def read_eval_cases(path: str | Path) -> list[EvalCase]:
    """Dispatch on file type so both eval-set formats work."""
    return read_eval_json(path) if str(path).endswith(".json") else read_eval_xlsx(path)


def read_eval_xlsx(path: str | Path) -> list[EvalCase]:
    xlsx_path = Path(path)
    with zipfile.ZipFile(xlsx_path) as archive:
        shared_strings = _shared_strings(archive)
        worksheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))

    rows: list[list[str]] = []
    for row in worksheet.findall(".//main:row", NS):
        values: dict[int, str] = {}
        max_index = -1
        for cell in row.findall("main:c", NS):
            index = _column_index(cell.attrib.get("r", "A1"))
            values[index] = _cell_value(cell, shared_strings)
            max_index = max(max_index, index)
        rows.append([values.get(index, "") for index in range(max_index + 1)])

    if not rows:
        return []
    headers = [str(value).strip() for value in rows[0]]
    cases: list[EvalCase] = []
    for row_index, row in enumerate(rows[1:], start=1):
        record = {
            headers[index]: row[index] if index < len(row) else "" for index in range(len(headers))
        }
        question = str(record.get("question") or "").strip()
        expected = str(record.get("human_answer") or "").strip()
        if not question or not expected:
            continue
        cases.append(
            EvalCase(
                question=question,
                expected_answer=expected,
                file_name=str(record.get("file_name") or "").strip() or None,
                post_url=str(record.get("post_url") or "").strip() or None,
                case_id=f"XLSX-{row_index:03d}",
            )
        )
    return cases


# Every status in which the system declined to produce a grounded answer.
# "not_found" belongs here for the same reason "not_grounded" does: the system
# said it could not answer. Omitting it scored a correct refusal as a failure.
REFUSAL_STATUSES = {"not_grounded", "not_found", "needs_review", "no_answer", "error"}
INFRASTRUCTURE_STATUSES = {"backend_auth_failed", "backend_timeout", "tool_error"}


def _normalized_document(value: Any) -> str:
    text = str(value or "").strip().lower().replace("\\", "/").rsplit("/", 1)[-1]
    return re.sub(r"\.(md|txt|pdf|docx|html?)$", "", text)


def _expected_document_matched(run: dict[str, Any], expected_document: str | None) -> bool | None:
    if not expected_document:
        return None
    expected = _normalized_document(expected_document)
    candidates: list[Any] = []
    for key in ("citations", "evidence", "source_evidence"):
        value = run.get(key) or []
        if isinstance(value, list):
            candidates.extend(value)
    for item in candidates:
        if isinstance(item, dict):
            for key in ("file_name", "source", "document", "document_name"):
                if _normalized_document(item.get(key)) == expected:
                    return True
    return False


def _eval_status(
    run: dict[str, Any], expected_eval: dict[str, Any], case: EvalCase | None = None
) -> str:
    grounding = run.get("grounding_status")

    if case is not None and case.expect_refusal:
        # The corpus cannot answer this. Declining is correct; producing a
        # confident grounded answer is the failure.
        return "pass" if grounding in REFUSAL_STATUSES else "fail"

    if (
        grounding in {"verified", "grounded", "recovered"}
        and expected_eval.get("status") == "pass"
    ):
        return "pass"
    if grounding in {"partial", "needs_review"}:
        return "manual_review"
    return "fail"


async def run_eval(
    *,
    xlsx_path: str | Path | None = None,
    eval_path: str | Path | None = None,
    orchestrator: EnterpriseRagOrchestrator | None = None,
    rules_path: str | Path | None = None,
    journal_path: str | Path | None = None,
    max_recovery_steps: int = 3,
    configuration: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_path = eval_path or xlsx_path
    if source_path is None:
        raise EvalSetError("eval_path is required")
    rules = load_rules(rules_path)
    cases = read_eval_cases(source_path)
    runtime_orchestrator = orchestrator or EnterpriseRagOrchestrator(
        rules_path=str(rules_path) if rules_path else None,
        journal_path=str(journal_path) if journal_path else None,
    )
    rows: list[dict[str, Any]] = []
    for case in cases:
        result = await runtime_orchestrator.run(
            case.question,
            max_recovery_steps=max_recovery_steps,
            expected_answer=case.expected_answer,
            journal_path=str(journal_path) if journal_path else None,
        )
        run = result.to_dict()
        expected_eval = evaluate_expected_answer(
            answer=str(run.get("answer") or ""),
            evidence=run.get("evidence") or [],
            expected_answer=case.expected_answer,
            question=case.question,
            rules=rules,
        )
        expected_document_matched = _expected_document_matched(run, case.file_name)
        eval_status = _eval_status(run, expected_eval, case)
        failure_class = (
            "infrastructure"
            if run.get("grounding_status") in INFRASTRUCTURE_STATUSES
            else ("quality" if eval_status != "pass" else None)
        )
        rows.append(
            {
                "case_id": case.case_id,
                "question": case.question,
                "expected_answer": case.expected_answer,
                "generated_answer": run.get("answer"),
                "grounding_status": run.get("grounding_status"),
                "evidence_verdict": run.get("evidence_verdict"),
                "tools_used": run.get("tools_used") or [],
                "eval_status": eval_status,
                "expect_refusal": case.expect_refusal,
                "refusal_passed": eval_status == "pass" if case.expect_refusal else None,
                "expected_document_matched": expected_document_matched,
                "expected_eval": expected_eval,
                "failure_class": failure_class,
                "failure_reason": run.get("failure_reason"),
                "error": run.get("error"),
                "file_name": case.file_name,
                "post_url": case.post_url,
                "latency_ms": run.get("latency_ms"),
                "run_id": run.get("run_id"),
            }
        )
    passed = sum(1 for row in rows if row["eval_status"] == "pass")
    failed = sum(1 for row in rows if row["eval_status"] == "fail")
    manual = sum(1 for row in rows if row["eval_status"] == "manual_review")
    refusal_total = sum(1 for row in rows if row["expect_refusal"])
    refusal_passed = sum(1 for row in rows if row["refusal_passed"] is True)
    infrastructure_failures = sum(1 for row in rows if row["failure_class"] == "infrastructure")
    return {
        "schema_version": "1.0",
        "eval_set": str(source_path),
        "total": len(rows),
        "passed": passed,
        "failed": failed,
        "manual_review": manual,
        "refusal_total": refusal_total,
        "refusal_passed": refusal_passed,
        "infrastructure_failures": infrastructure_failures,
        "configuration": {
            "app_prompts": prompt_metadata(),
            **(configuration or {}),
        },
        "status": "pass" if rows and failed == 0 and manual == 0 else "fail",
        "rows": rows,
    }


def render_eval_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# RAG Evaluation Report",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Total | {report.get('total', 0)} |",
        f"| Passed | {report.get('passed', 0)} |",
        f"| Failed | {report.get('failed', 0)} |",
        f"| Manual review | {report.get('manual_review', 0)} |",
        "",
        "## Results",
        "",
        "| # | Status | Question | Expected | Generated | Grounding | Tools | Evidence Verdict |",
        "| ---: | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for index, row in enumerate(report.get("rows", []), start=1):
        verdict = row.get("evidence_verdict") or {}
        tools = ", ".join(f"`{tool}`" for tool in row.get("tools_used") or []) or "-"
        values = [
            str(index),
            str(row.get("eval_status") or "-"),
            _table_text(row.get("question")),
            _table_text(row.get("expected_answer"), 180),
            _table_text(row.get("generated_answer"), 220),
            _table_text(row.get("grounding_status")),
            tools,
            _table_text(
                verdict.get("reason") or row.get("failure_reason") or row.get("error") or "-"
            ),
        ]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines).rstrip() + "\n"


def _table_text(value: Any, limit: int = 140) -> str:
    text = " ".join(str(value or "-").replace("|", "\\|").split())
    if len(text) > limit:
        return text[: limit - 3].rstrip() + "..."
    return text


def write_eval_outputs(
    report: dict[str, Any],
    *,
    markdown_path: str | Path | None = None,
    json_path: str | Path | None = None,
) -> dict[str, str]:
    safe_report = redact_for_sharing(report)
    written: dict[str, str] = {}
    if markdown_path:
        path = Path(markdown_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_eval_markdown(safe_report), encoding="utf-8")
        written["markdown"] = str(path)
    if json_path:
        path = Path(json_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(safe_report, indent=2, sort_keys=True), encoding="utf-8")
        written["json"] = str(path)
    return written


def run_eval_sync(**kwargs: Any) -> dict[str, Any]:
    return asyncio.run(run_eval(**kwargs))
