"""Generate public-safe approved-v1 and candidate-v2 evidence from artifacts."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rag_enterprise_langgraph.red_team import run_red_team

ROOT = Path(__file__).resolve().parents[1]
APPROVED_V1 = ROOT / "config" / "eval-baselines" / "northwind-openai-v1.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_status(
    report: dict[str, Any], *, source_name: str, source_sha256: str,
    approved_v1: dict[str, Any] | None = None, approved_v1_sha256: str | None = None,
) -> dict[str, Any]:
    rows = report.get("rows")
    if not isinstance(rows, list) or len(rows) != 90 or report.get("total") != 90:
        raise ValueError("candidate evidence requires exactly 90 rows")
    ids = [str(row.get("case_id") or "") for row in rows]
    if any(not case_id for case_id in ids) or len(set(ids)) != 90:
        raise ValueError("candidate evidence has missing or duplicate case IDs")
    outcomes = {key: int(report.get(key, 0)) for key in ("passed", "failed", "manual_review")}
    if sum(outcomes.values()) != 90:
        raise ValueError("candidate outcome counts must total 90")
    operations = {
        key: int(report.get(key, 0))
        for key in (
            "transport_failures",
            "grader_failures",
            "other_infrastructure_failures",
            "infrastructure_failures",
        )
    }
    if any(operations.values()):
        raise ValueError("candidate release requires zero evaluation-infrastructure failures")
    approved_v1 = approved_v1 or json.loads(APPROVED_V1.read_text(encoding="utf-8"))
    if int(approved_v1.get("total", 0)) != 25 or int(approved_v1.get("passed", 0)) != 25:
        raise ValueError("approved v1 artifact must retain its 25/25 identity")
    approved_v1_sha256 = approved_v1_sha256 or _sha256(APPROVED_V1)
    red_team = run_red_team()
    configuration = report.get("configuration") or {}
    safe_configuration = {
        key: configuration.get(key)
        for key in (
            "grader_version",
            "suite_version",
            "llm",
            "embedding",
            "chunking",
            "retrieval",
            "orchestration",
            "app_prompts",
            "starter_prompts",
            "corpus_manifest_sha256",
            "repository_revisions",
            "workflow",
        )
        if configuration.get(key) is not None
    }
    return {
        "schema_version": "2.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "evidence_status": "candidate",
        "approval_statement": "Candidate snapshot only; v2 is not an approved baseline.",
        "approved_baseline": {
            "id": "northwind-openai-v1",
            "case_count": 25,
            "passed": 25,
            "failed": int(approved_v1.get("failed", 0)),
            "manual_review": int(approved_v1.get("manual_review", 0)),
            "refusal_total": int(approved_v1.get("refusal_total", 0)),
            "refusal_passed": int(approved_v1.get("refusal_passed", 0)),
            "result": "25/25",
            "statement": "Approved v1 baseline; unchanged by the v2 candidate publication.",
            "source": {"name": APPROVED_V1.name, "sha256": approved_v1_sha256},
        },
        "source_artifact": {"name": source_name, "sha256": source_sha256},
        "quality": {
            "total": 90,
            **outcomes,
            "refusal_total": int(report.get("refusal_total", 0)),
            "refusal_passed": int(report.get("refusal_passed", 0)),
            "safe_boundary_total": int(report.get("safe_boundary_total", 0)),
            "safe_boundary_passed": int(report.get("safe_boundary_passed", 0)),
        },
        "operations": operations,
        "performance": report.get("performance") or {"status": "not_recorded"},
        "governance": {
            "deterministic_red_team": {
                key: red_team.get(key)
                for key in ("total", "defended", "failed", "requires_backend", "overall_status")
            },
            "rt06": report.get("rt06") or {"status": "not_recorded"},
            "rt16": report.get("rt16") or {"status": "not_recorded"},
        },
        "configuration": safe_configuration,
        "limitations": {
            "failed_case_ids": [r["case_id"] for r in rows if r.get("eval_status") == "fail"],
            "manual_review_case_ids": [
                r["case_id"] for r in rows if r.get("eval_status") == "manual_review"
            ],
            "statements": [
                "Synthetic public-demo corpus; no client or private data.",
                "This is one reproducible candidate snapshot, not ten-run calibration.",
                "Quality failures are retained as limitations rather than tuned away.",
            ],
        },
    }


def render(status: dict[str, Any]) -> str:
    q, o, g = status["quality"], status["operations"], status["governance"]

    def esc(value: object) -> str:
        return html.escape(str(value))

    return f"""<!-- GENERATED from status.json; do not edit counts by hand. -->
<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>B004 evaluation evidence</title>
<style>body{{font:16px/1.5 system-ui;max-width:900px;margin:3rem auto;padding:0 1rem}}table{{border-collapse:collapse}}th,td{{padding:.5rem 1rem;border-bottom:1px solid #ccc;text-align:left}}.note{{padding:1rem;background:#fff5cc}}</style>
<h1>B004 evaluation evidence</h1>
<section><h2>Approved v1 baseline</h2><p><strong>{esc(status["approved_baseline"]["result"])}</strong> cases passed. This is the only approved baseline.</p><p>Artifact SHA-256: <code>{esc(status["approved_baseline"]["source"]["sha256"])}</code></p></section>
<section><h2>v2 candidate snapshot</h2><p class="note">{esc(status["approval_statement"])}</p>
<table><tr><th>Cases</th><td>{q["total"]}</td></tr><tr><th>Pass</th><td>{q["passed"]}</td></tr><tr><th>Fail</th><td>{q["failed"]}</td></tr><tr><th>Manual review</th><td>{q["manual_review"]}</td></tr><tr><th>Refusals</th><td>{q["refusal_passed"]}/{q["refusal_total"]}</td></tr><tr><th>Transport failures</th><td>{o["transport_failures"]}</td></tr><tr><th>Grader failures</th><td>{o["grader_failures"]}</td></tr><tr><th>Other infrastructure failures</th><td>{o["other_infrastructure_failures"]}</td></tr><tr><th>RT-06</th><td>{esc(g["rt06"].get("status"))}</td></tr><tr><th>RT-16</th><td>{esc(g["rt16"].get("status"))}</td></tr></table>
<h2>Limitations</h2><p>Failed: {esc(", ".join(status["limitations"]["failed_case_ids"]) or "none")}.</p><p>Manual review: {esc(", ".join(status["limitations"]["manual_review_case_ids"]) or "none")}.</p>
<p>Candidate source SHA-256: <code>{esc(status["source_artifact"]["sha256"])}</code></p></section>"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--status-out", type=Path, required=True)
    parser.add_argument("--html-out", type=Path, required=True)
    args = parser.parse_args()
    status = build_status(
        json.loads(args.report.read_text()),
        source_name=args.report.name,
        source_sha256=_sha256(args.report),
    )
    args.status_out.parent.mkdir(parents=True, exist_ok=True)
    args.html_out.parent.mkdir(parents=True, exist_ok=True)
    args.status_out.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n")
    args.html_out.write_text(render(status))
    print(
        json.dumps({"status": "generated", "source_sha256": status["source_artifact"]["sha256"]})
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
