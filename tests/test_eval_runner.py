from __future__ import annotations

import asyncio
import zipfile
from pathlib import Path

from rag_enterprise_langgraph.eval_runner import read_eval_xlsx, render_eval_markdown, run_eval, write_eval_outputs
from rag_enterprise_langgraph.orchestrator import OrchestratedRunResult


def _xlsx_cell(cell: str, value: str) -> str:
    escaped = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f'<c r="{cell}" t="inlineStr"><is><t>{escaped}</t></is></c>'


def _write_eval_xlsx(path: Path) -> None:
    rows = [
        ["question", "human_answer", "file_name", "post_url"],
        ["Which was one of the first free email services?", "Juno was one of the first free email services.", "amazoncom", "https://example.com"],
        ["What Percentage of Rent to Sales did Sam Waltons first Ben Franklin cost", "0.05", "walmart", "https://example.com/walmart"],
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
        f'<sheetData>{"".join(row_xml)}</sheetData>'
        "</worksheet>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/worksheets/sheet1.xml", worksheet)


class _EvalOrchestrator:
    async def run(self, question: str, *, max_recovery_steps: int = 3, expected_answer: str | None = None, journal_path: str | None = None):  # noqa: ARG002
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
    assert "Acquired RAG Evaluation Report" in rendered
    assert written["markdown"] == str(markdown)
    assert markdown.exists()
    assert json_path.exists()
