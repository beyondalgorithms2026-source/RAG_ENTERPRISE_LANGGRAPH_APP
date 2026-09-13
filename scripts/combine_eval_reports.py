"""Combine the isolated 25-case and 65-case reports into one governed suite."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


class CombinedReportError(ValueError):
    """Phase reports cannot form the declared 90-case suite."""


def combine_reports(core: dict[str, Any], manual: dict[str, Any]) -> dict[str, Any]:
    phases = (("core", core, 25), ("operations-manual", manual, 65))
    rows: list[dict[str, Any]] = []
    phase_metadata: dict[str, Any] = {}
    seen: set[str] = set()
    for phase_id, report, expected_count in phases:
        phase_rows = report.get("rows")
        if not isinstance(phase_rows, list) or len(phase_rows) != expected_count:
            raise CombinedReportError(
                f"{phase_id} phase must contain exactly {expected_count} rows"
            )
        for row in phase_rows:
            case_id = str(row.get("case_id") or "").strip() if isinstance(row, dict) else ""
            if not case_id or case_id in seen:
                raise CombinedReportError(f"missing or duplicate case_id: {case_id!r}")
            seen.add(case_id)
            rows.append({**row, "evaluation_phase": phase_id})
        phase_metadata[phase_id] = {
            "schema_version": report.get("schema_version"),
            "eval_set": report.get("eval_set"),
            "configuration": report.get("configuration"),
            "status": report.get("status"),
        }

    passed = sum(row.get("eval_status") == "pass" for row in rows)
    failed = sum(row.get("eval_status") == "fail" for row in rows)
    manual_review = sum(row.get("eval_status") == "manual_review" for row in rows)
    refusal_rows = [row for row in rows if row.get("expectation") == "refuse"]
    boundary_rows = [row for row in rows if row.get("expectation") == "safe_boundary"]
    infrastructure = sum(row.get("failure_class") == "infrastructure" for row in rows)
    configuration = dict(manual.get("configuration") or {})
    configuration["evaluation_phases"] = {
        phase_id: data["configuration"] for phase_id, data in phase_metadata.items()
    }
    return {
        "schema_version": "2.0",
        "eval_suite": "northwind-full-stack-v2",
        "eval_set": "config/eval-suite-northwind-v2.json",
        "total": len(rows),
        "passed": passed,
        "failed": failed,
        "manual_review": manual_review,
        "refusal_total": len(refusal_rows),
        "refusal_passed": sum(row.get("eval_status") == "pass" for row in refusal_rows),
        "safe_boundary_total": len(boundary_rows),
        "safe_boundary_passed": sum(row.get("eval_status") == "pass" for row in boundary_rows),
        "infrastructure_failures": infrastructure,
        "configuration": configuration,
        "phases": phase_metadata,
        "status": "pass"
        if len(rows) == 90 and failed == 0 and manual_review == 0 and infrastructure == 0
        else "fail",
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("core", type=Path)
    parser.add_argument("manual", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        combined = combine_reports(
            json.loads(args.core.read_text(encoding="utf-8")),
            json.loads(args.manual.read_text(encoding="utf-8")),
        )
    except (OSError, json.JSONDecodeError, CombinedReportError) as exc:
        print(f"error: cannot combine evaluation reports: {exc}")
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(combined, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"Combined {combined['total']} cases: {combined['passed']} pass, "
        f"{combined['failed']} fail, {combined['manual_review']} manual review"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
