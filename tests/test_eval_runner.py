from __future__ import annotations

import asyncio
import json
import zipfile
from pathlib import Path

from rag_enterprise_langgraph.eval_judge import JudgeInfrastructureError
from rag_enterprise_langgraph.eval_runner import (
    read_eval_xlsx,
    render_eval_markdown,
    run_eval,
    write_eval_outputs,
)
from rag_enterprise_langgraph.evidence import evaluate_expected_answer
from rag_enterprise_langgraph.orchestrator import OrchestratedRunResult


def _xlsx_cell(cell: str, value: str) -> str:
    escaped = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f'<c r="{cell}" t="inlineStr"><is><t>{escaped}</t></is></c>'


def _write_eval_xlsx(path: Path) -> None:
    rows = [
        ["question", "human_answer", "file_name", "post_url"],
        [
            "Which was one of the first free email services?",
            "Juno was one of the first free email services.",
            "amazoncom",
            "https://example.com",
        ],
        [
            "What Percentage of Rent to Sales did Sam Waltons first Ben Franklin cost",
            "0.05",
            "walmart",
            "https://example.com/walmart",
        ],
    ]
    row_xml: list[str] = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for col_index, value in enumerate(row):
            col = chr(ord("A") + col_index)
            cells.append(_xlsx_cell(f"{col}{row_index}", value))
        row_xml.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    worksheet = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(row_xml)}</sheetData>"
        "</worksheet>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/worksheets/sheet1.xml", worksheet)


class _EvalOrchestrator:
    async def run(
        self,
        question: str,
        *,
        max_recovery_steps: int = 3,
        expected_answer: str | None = None,
        journal_path: str | None = None,
    ):
        if "free email" in question:
            return OrchestratedRunResult(
                question=question,
                answer="The transcript mentions Juno as one of the first free email services.",
                grounding_status="recovered",
                tools_used=["ask_grounded"],
                execution_timeline=[],
                evidence=[{"snippet": "Juno was one of the first free email services."}],
                evidence_count=1,
                portfolio_safe=True,
            )
        return OrchestratedRunResult(
            question=question,
            answer="The first Ben Franklin rent cost 5% of sales.",
            grounding_status="recovered",
            tools_used=["ask_grounded"],
            execution_timeline=[],
            evidence=[{"snippet": "rent cost 5% of sales"}],
            evidence_count=1,
            portfolio_safe=True,
        )


def test_read_eval_xlsx_reads_required_columns(tmp_path):
    path = tmp_path / "eval.xlsx"
    _write_eval_xlsx(path)

    cases = read_eval_xlsx(path)

    assert len(cases) == 2
    assert cases[0].question == "Which was one of the first free email services?"
    assert cases[0].expected_answer.startswith("Juno")


def test_run_eval_marks_expected_answers_and_writes_reports(tmp_path):
    path = tmp_path / "eval.xlsx"
    markdown = tmp_path / "report.md"
    json_path = tmp_path / "report.json"
    _write_eval_xlsx(path)

    report = asyncio.run(run_eval(xlsx_path=path, orchestrator=_EvalOrchestrator()))
    written = write_eval_outputs(report, markdown_path=markdown, json_path=json_path)
    rendered = render_eval_markdown(report)

    assert report["total"] == 2
    assert report["passed"] == 2
    assert report["status"] == "pass"
    assert "RAG Evaluation Report" in rendered
    assert written["markdown"] == str(markdown)
    assert markdown.exists()
    assert json_path.exists()


def test_expected_fact_in_evidence_does_not_hide_wrong_generated_answer():
    result = evaluate_expected_answer(
        answer="Expenditure of 20,000 EUR requires department head approval.",
        evidence=[{"snippet": "Above 15,000 EUR requires the finance director."}],
        expected_answer="the finance director",
        question="Who can approve expenditure of 20,000 EUR?",
        rules=[],
    )

    assert result["status"] == "fail"
    assert result["answer_matched_terms"] == []
    assert result["evidence_matched_terms"] == ["finance", "director"]


class _MealAllowanceOrchestrator:
    async def run(self, question: str, **_kwargs):
        return OrchestratedRunResult(
            question=question,
            answer="The daily meal allowance for international travel is 65 EUR [S1].",
            grounding_status="verified",
            tools_used=["ask_grounded"],
            execution_timeline=[],
            citations=[{"file_name": "travel-expense-policy", "snippet": "65 EUR"}],
            evidence=[
                {
                    "file_name": "travel-expense-policy",
                    "snippet": "The daily meal allowance is 45 EUR for domestic travel and 65 EUR"
                    " for international travel.",
                }
            ],
            evidence_count=1,
            portfolio_safe=True,
        )


def _meal_allowance_pack(tmp_path: Path) -> Path:
    pack = json.loads(Path("config/eval-set-northwind-candidate.json").read_text(encoding="utf-8"))
    pack["questions"] = [q for q in pack["questions"] if q["case_id"] == "NW-002"]
    path = tmp_path / "pack.json"
    path.write_text(json.dumps(pack), encoding="utf-8")
    return path


def _failing_judge(last_reason: str):
    async def judge(**_kwargs):
        error = JudgeInfrastructureError("offline judge retry budget exhausted")
        error.last_reason = last_reason
        raise error

    return judge


def test_unverifiable_judge_quotes_route_to_manual_review_not_infrastructure(tmp_path):
    report = asyncio.run(
        run_eval(
            eval_path=_meal_allowance_pack(tmp_path),
            orchestrator=_MealAllowanceOrchestrator(),
            semantic_judge=_failing_judge("invalid scoped evidence span"),
        )
    )
    row = report["rows"][0]
    assert row["eval_status"] == "manual_review"
    assert row["failure_class"] == "quality"
    assert "judge_error" not in row["expected_eval"]
    assert row["expected_eval"]["judge_unverifiable"].endswith("invalid scoped evidence span")
    concept = next(
        a for a in row["expected_eval"]["typed"]["assertions"] if a["id"] == "allowance"
    )
    assert concept["state"] == "uncertain"
    assert report["infrastructure_failures"] == 0


def test_judge_outage_remains_an_infrastructure_failure(tmp_path):
    report = asyncio.run(
        run_eval(
            eval_path=_meal_allowance_pack(tmp_path),
            orchestrator=_MealAllowanceOrchestrator(),
            semantic_judge=_failing_judge("offline judge transport failure"),
        )
    )
    row = report["rows"][0]
    assert row["eval_status"] == "fail"
    assert row["failure_class"] == "infrastructure"
    assert row["expected_eval"]["judge_error"] == "offline_judge_infrastructure_failure"
    assert report["infrastructure_failures"] == 1
