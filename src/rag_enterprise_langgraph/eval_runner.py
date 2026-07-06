from __future__ import annotations

import asyncio
import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence
from xml.etree import ElementTree as ET

from rag_enterprise_langgraph.evidence import evaluate_expected_answer, load_rules
from rag_enterprise_langgraph.orchestrator import EnterpriseRagOrchestrator


NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


@dataclass(frozen=True)
class EvalCase:
    question: str
    expected_answer: str
    file_name: str | None = None
    post_url: str | None = None


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
    for row in rows[1:]:
        record = {headers[index]: row[index] if index < len(row) else "" for index in range(len(headers))}
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
            )
        )
    return cases


def _eval_status(run: dict[str, Any], expected_eval: dict[str, Any]) -> str:
    if run.get("grounding_status") in {"verified", "grounded", "recovered"} and expected_eval.get("status") == "pass":
        return "pass"
    if run.get("grounding_status") in {"partial", "needs_review"}:
        return "manual_review"
    return "fail"


async def run_eval(
    *,
    xlsx_path: str | Path,
    orchestrator: EnterpriseRagOrchestrator | None = None,
    rules_path: str | Path | None = None,
    journal_path: str | Path | None = None,
    max_recovery_steps: int = 3,
) -> dict[str, Any]:
    rules = load_rules(rules_path)
    cases = read_eval_xlsx(xlsx_path)
    runtime_orchestrator = orchestrator or EnterpriseRagOrchestrator(rules_path=str(rules_path) if rules_path else None, journal_path=str(journal_path) if journal_path else None)
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
        rows.append(
            {
                "question": case.question,
                "expected_answer": case.expected_answer,
                "generated_answer": run.get("answer"),
                "grounding_status": run.get("grounding_status"),
                "evidence_verdict": run.get("evidence_verdict"),
                "tools_used": run.get("tools_used") or [],
                "eval_status": _eval_status(run, expected_eval),
                "expected_eval": expected_eval,
                "failure_reason": run.get("failure_reason"),
                "error": run.get("error"),
                "file_name": case.file_name,
                "post_url": case.post_url,
            }
        )
    passed = sum(1 for row in rows if row["eval_status"] == "pass")
    failed = sum(1 for row in rows if row["eval_status"] == "fail")
    manual = sum(1 for row in rows if row["eval_status"] == "manual_review")
    return {
        "xlsx_path": str(xlsx_path),
        "total": len(rows),
        "passed": passed,
        "failed": failed,
        "manual_review": manual,
        "status": "pass" if rows and failed == 0 and manual == 0 else "fail",
        "rows": rows,
    }


def render_eval_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Acquired RAG Evaluation Report",
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
            _table_text(verdict.get("reason") or row.get("failure_reason") or row.get("error") or "-"),
        ]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines).rstrip() + "\n"


def _table_text(value: Any, limit: int = 140) -> str:
    text = " ".join(str(value or "-").replace("|", "\\|").split())
    if len(text) > limit:
        return text[: limit - 3].rstrip() + "..."
    return text


def write_eval_outputs(report: dict[str, Any], *, markdown_path: str | Path | None = None, json_path: str | Path | None = None) -> dict[str, str]:
    written: dict[str, str] = {}
    if markdown_path:
        path = Path(markdown_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_eval_markdown(report), encoding="utf-8")
        written["markdown"] = str(path)
    if json_path:
        path = Path(json_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        written["json"] = str(path)
    return written


def run_eval_sync(**kwargs: Any) -> dict[str, Any]:
    return asyncio.run(run_eval(**kwargs))
